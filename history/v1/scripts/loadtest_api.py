#!/usr/bin/env python3
"""Concurrency / load driver for the API Server.

Establishes a latency baseline for the hot paths under realistic simultaneous
users across *multiple firms*, and asserts that the now-externalized session
state is durable and firm-isolated under concurrency:

  - Signs up N independent firms (separate tenants).
  - Fires R rounds x C concurrent requests per firm against the hot paths
    (dashboard load, lists) plus a write+read-back of firm-scoped session state
    (saving and listing a DCF model).
  - Verifies each firm only ever reads back *its own* saved model (no cross-firm
    bleed) and that the write it just made is visible on the next read (durable,
    shared store — not process-local memory).
  - Reports p50/p95/p99/max latency per endpoint and overall error count.

Pure stdlib (urllib) so it has no extra dependencies. It assumes the server is
already running; point it at one with BASE (e.g. http://127.0.0.1:8137). The
shell wrapper ``scripts/loadtest-api.sh`` boots a server first, then runs this.

Exit status is non-zero on any request error or any cross-firm isolation /
durability breach. Latency is reported as a baseline and flagged (warning only)
when p95 on a hot path exceeds LATENCY_BUDGET_MS — absolute latency depends on
where this runs (local loopback vs. the public TLS proxy) and how many instances
are serving, so it is not a hard gate.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import quantiles
from typing import Dict, List, Optional, Tuple

BASE = os.environ.get("BASE", "http://127.0.0.1:8137").rstrip("/")
FIRMS = int(os.environ.get("LOAD_FIRMS", "8"))
ROUNDS = int(os.environ.get("LOAD_ROUNDS", "10"))
CONCURRENCY = int(os.environ.get("LOAD_CONCURRENCY", "24"))
TIMEOUT = float(os.environ.get("LOAD_TIMEOUT", "30"))

# Per-endpoint p95 latency budgets (ms). These are calibrated against a *loopback*
# baseline (BASE pointing at 127.0.0.1, not the public TLS proxy) at the default
# fan-out (8 firms x 10 rounds, 24 concurrent) with the default-dashboard cache
# warm. Observed loopback p95 sits comfortably under 1s for every hot path once
# /api/dashboard/default is served from its short-TTL cache, so the budgets below
# carry ~1.5-2x headroom to absorb a cold cache build and scheduling jitter while
# still catching a real regression (i.e. a path slipping back into multi-second
# territory). The default fallback applies to any endpoint without an explicit
# entry. Override any value with LOAD_BUDGET_<LABEL>_MS, e.g.
# LOAD_BUDGET_DASHBOARD_DEFAULT_MS=2500, or the fallback with LOAD_LATENCY_BUDGET_MS.
DEFAULT_LATENCY_BUDGET_MS = float(os.environ.get("LOAD_LATENCY_BUDGET_MS", "1500"))
ENDPOINT_BUDGET_MS: Dict[str, float] = {
    # Heaviest hot path: 6 panels + (on a cache miss) several live upstream
    # fetches and a ~240KB payload. Cached, so steady-state p95 is small; the
    # extra headroom absorbs the periodic cold rebuild when the TTL lapses.
    "dashboard_default": 2000.0,
    "watchlist": 1500.0,
    "skills": 1500.0,
    "dashboards_list": 1500.0,
    "dcf_save": 1500.0,
    "dcf_list": 1500.0,
}

# When LOAD_GATE_LATENCY is truthy, a p95 over budget FAILS the run (a real
# regression gate). Otherwise it is reported as a warning only — absolute latency
# depends on where the driver runs (loopback vs. public TLS proxy) and on the
# instance count, so a blanket hard gate would be flaky in those environments.
GATE_LATENCY = os.environ.get("LOAD_GATE_LATENCY", "0").strip().lower() in (
    "1", "true", "yes", "on",
)


def budget_for(label: str) -> float:
    override = os.environ.get(f"LOAD_BUDGET_{label.upper()}_MS")
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    return ENDPOINT_BUDGET_MS.get(label, DEFAULT_LATENCY_BUDGET_MS)


def _req(method: str, path: str, token: Optional[str] = None,
         body: Optional[dict] = None) -> Tuple[int, dict, float, Optional[dict]]:
    """Make one request; returns (status, headers, elapsed_ms, json_body_or_None)."""
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            elapsed = (time.perf_counter() - t0) * 1000.0
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = None
            return resp.status, hdrs, elapsed, parsed
    except urllib.error.HTTPError as e:
        elapsed = (time.perf_counter() - t0) * 1000.0
        return e.code, {}, elapsed, None
    except Exception:  # noqa: BLE001  (connection refused, timeout, etc.)
        elapsed = (time.perf_counter() - t0) * 1000.0
        return 0, {}, elapsed, None


def _signup(i: int) -> Optional[str]:
    suffix = f"{os.getpid()}_{int(time.time())}_{i}"
    body = {
        "firmName": f"Load Firm {suffix}",
        "name": "Load Admin",
        "email": f"load_{suffix}@example.com",
        "password": "load-pass-1234",
    }
    status, hdrs, _, _ = _req("POST", "/api/auth/signup", body=body)
    if status != 200:
        return None
    cookie = hdrs.get("set-cookie", "")
    # set-cookie: at_session=<token>; ...
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("at_session="):
            return part[len("at_session="):]
    return None


def main() -> int:
    print(f"Load test -> {BASE}  firms={FIRMS} rounds={ROUNDS} concurrency={CONCURRENCY}")

    # 1) Wait for readiness.
    for _ in range(60):
        status, _, _, body = _req("GET", "/api/readyz")
        if status == 200:
            print(f"readyz OK: {body}")
            break
        time.sleep(1)
    else:
        print("ERROR: /api/readyz never became ready")
        return 1

    # 2) Sign up the firms (tenants).
    tokens: List[str] = []
    for i in range(FIRMS):
        tok = _signup(i)
        if not tok:
            print(f"ERROR: signup failed for firm {i}")
            return 1
        tokens.append(tok)
    print(f"Signed up {len(tokens)} firms.")

    # Each firm saves a uniquely-named DCF model so we can assert isolation.
    model_name_for = {i: f"load-model-{i}" for i in range(FIRMS)}

    lat: Dict[str, List[float]] = {}
    errors: List[str] = []
    breaches: List[str] = []

    def record(label: str, ms: float) -> None:
        lat.setdefault(label, []).append(ms)

    def one_unit(firm_idx: int, rnd: int) -> None:
        tok = tokens[firm_idx]
        name = model_name_for[firm_idx]

        # Hot read paths.
        for label, path in (
            ("dashboard_default", "/api/dashboard/default"),
            ("watchlist", "/api/watchlist"),
            ("skills", "/api/skills"),
            ("dashboards_list", "/api/dashboards"),
        ):
            st, _, ms, _ = _req("GET", path, token=tok)
            record(label, ms)
            if st != 200:
                errors.append(f"firm{firm_idx} {path} -> {st}")

        # Firm-scoped session-state write (durable, externalized).
        sid = f"load-sess-{firm_idx}"
        save_body = {
            "sessionId": sid, "name": name, "symbol": "NVDA",
            "assumptions": {
                "revenueGrowth": 0.1, "ebitdaMargin": 0.4, "wacc": 0.09,
                "exitMultiple": 15, "taxRate": 0.21, "capexPct": 0.05,
            },
        }
        st, _, ms, _ = _req("POST", "/api/dcf-models", token=tok, body=save_body)
        record("dcf_save", ms)
        if st != 200:
            errors.append(f"firm{firm_idx} POST dcf-models -> {st}")

        # Read back: must see our own model and ONLY firm-local names.
        st, _, ms, parsed = _req(
            "GET", f"/api/dcf-models?sessionId={sid}&symbol=NVDA", token=tok)
        record("dcf_list", ms)
        if st != 200:
            errors.append(f"firm{firm_idx} GET dcf-models -> {st}")
        elif parsed is not None:
            names = {m.get("name") for m in parsed.get("models", [])}
            if name not in names:
                breaches.append(f"firm{firm_idx} could not read back its own model (durability)")
            foreign = names - {model_name_for[i] for i in (firm_idx,)}
            if foreign:
                breaches.append(f"firm{firm_idx} saw foreign models {foreign} (isolation)")

    # 3) Fire the load: FIRMS x ROUNDS units, CONCURRENCY at a time.
    units = [(f, r) for r in range(ROUNDS) for f in range(FIRMS)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(one_unit, f, r) for (f, r) in units]
        for fut in as_completed(futures):
            fut.result()
    wall = time.perf_counter() - t0

    # 4) Report.
    def pct(vals: List[float], p: float) -> float:
        if not vals:
            return 0.0
        if len(vals) == 1:
            return vals[0]
        # quantiles with n=100 -> index by percentile.
        qs = quantiles(sorted(vals), n=100)
        return qs[min(int(p) - 1, len(qs) - 1)]

    total_reqs = sum(len(v) for v in lat.values())
    print("\n--- latency by endpoint (ms) ---")
    print(f"{'endpoint':<20}{'n':>6}{'p50':>10}{'p95':>10}{'p99':>10}{'max':>10}{'budget':>10}")
    over_budget = []
    for label in sorted(lat):
        vals = lat[label]
        p50, p95, p99, mx = pct(vals, 50), pct(vals, 95), pct(vals, 99), max(vals)
        budget = budget_for(label)
        flag = "  OVER" if p95 > budget else ""
        print(
            f"{label:<20}{len(vals):>6}{p50:>10.1f}{p95:>10.1f}{p99:>10.1f}"
            f"{mx:>10.1f}{budget:>10.0f}{flag}"
        )
        if p95 > budget:
            over_budget.append(f"{label} p95={p95:.0f}ms > budget {budget:.0f}ms")

    print(
        f"\n{total_reqs} requests across {FIRMS} firms in {wall:.2f}s "
        f"(~{total_reqs / wall:.0f} req/s), errors={len(errors)}, "
        f"isolation_breaches={len(breaches)}"
    )

    ok = True
    if errors:
        ok = False
        print("\nERRORS (first 10):")
        for e in errors[:10]:
            print(f"  - {e}")
    if breaches:
        ok = False
        print("\nISOLATION/DURABILITY BREACHES (first 10):")
        for b in breaches[:10]:
            print(f"  - {b}")
    if over_budget:
        gate_note = "FAILING (LOAD_GATE_LATENCY)" if GATE_LATENCY else "warning only"
        print(f"\nLATENCY OVER PER-ENDPOINT BUDGET (p95) — {gate_note}:")
        for o in over_budget:
            print(f"  - {o}")
        if GATE_LATENCY:
            # Opt-in regression gate. Off by default because absolute latency
            # depends on where this runs (loopback vs. public TLS proxy) and on
            # the instance count, so a blanket hard gate would be flaky there.
            ok = False
        else:
            print(
                "  (set LOAD_GATE_LATENCY=1 to make this a hard gate; only do so "
                "when driving over loopback, not the public proxy)"
            )

    # Correctness under concurrency (no request errors, no cross-firm isolation /
    # durability breaches) always gates. Latency gates only when LOAD_GATE_LATENCY
    # is set.
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
