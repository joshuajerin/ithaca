"""Test harness for ithaca-runtime.

Provides:
- A deterministic, network-free synthetic price fetch (replicated from the core's
  conftest pattern — NOT imported, per instructions).
- A ``Core`` wired to that fetch (no network).
- An in-memory ``Platform`` double with ``.runs`` (mini RunStore) and ``.trace``
  (mini TraceStore that VALIDATES each event against the real TraceEvent contract,
  proving the workers emit contract-shaped events and assigning a gap-free seq).
- A valid ``StrategySpec`` dict and helpers to seed a queued run.
"""

from __future__ import annotations

import datetime as dt
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest

# --- make ithaca_core + ithaca_contracts importable in isolated runs ---------
_ROOT = Path(__file__).resolve().parents[3]
_TEST_ROOT = Path(__file__).resolve().parent
for p in (
    _TEST_ROOT,
    _ROOT / "ithaca-core" / "src",
    _ROOT / "packages" / "contracts" / "py",
    _ROOT / "services" / "platform" / "src",
):
    sp = str(p)
    if p.exists() and sp not in sys.path:
        sys.path.insert(0, sp)

from ithaca_contracts import TraceEvent  # noqa: E402
from ithaca_core import Core, DataGateway  # noqa: E402
from ithaca_platform import Platform as DurablePlatform  # noqa: E402


class _LocalServer:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("content-length") or "0")
                body = self.rfile.read(length) if length else b""
                owner.requests.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        "headers": dict(self.headers),
                        "body": body,
                    }
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, *args):  # noqa: D401
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_port}/hook"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> "_LocalServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


@pytest.fixture
def local_server():
    server = _LocalServer().start()
    try:
        yield server
    finally:
        server.stop()


# --- synthetic, deterministic price source (replicated pattern) ------------------


def _trading_days(n: int, start: str = "2024-01-01") -> list[str]:
    y, m, d = (int(x) for x in start.split("-"))
    day = dt.date(y, m, d)
    out: list[str] = []
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def _make_series(
    n: int, drift: float, vol: float, seed: int, start_price: float = 100.0
) -> list[float]:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, size=n)
    return list(np.maximum(start_price * np.cumprod(1.0 + rets), 1e-6))


def make_fetch(series_by_symbol: dict[str, list[float]], dates: list[str]):
    """fetch_price_history-compatible callable backed by in-memory series."""

    def _fetch(symbol: str, range_: str = "1y", interval: str = "1d") -> dict:
        su = symbol.upper()
        if su not in series_by_symbol:
            raise ValueError(f"no data for {su}")
        closes = series_by_symbol[su]
        points = [
            {
                "d": dates[i],
                "o": closes[i],
                "h": closes[i],
                "l": closes[i],
                "c": closes[i],
                "v": 1_000_000.0,
            }
            for i in range(len(dates))
        ]
        return {
            "points": points,
            "quote": {"symbol": su, "price": closes[-1], "asOf": dates[-1] + "T20:00:00Z"},
        }

    return _fetch


# The last bar is "today" so the paper-tick staleness gate passes under real wall clock.
def _recent_dates(n: int) -> list[str]:
    """n trading days ending today (UTC)."""
    out: list[str] = []
    day = dt.datetime.now(dt.timezone.utc).date()
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day -= dt.timedelta(days=1)
    return sorted(out)


@pytest.fixture
def synthetic_panel():
    dates = _recent_dates(260)
    series = {
        "AAA": _make_series(len(dates), drift=0.0012, vol=0.012, seed=1),  # strong up
        "BBB": _make_series(len(dates), drift=0.0002, vol=0.015, seed=2),  # mild up
        "CCC": _make_series(len(dates), drift=-0.0008, vol=0.018, seed=3),  # down
    }
    return dates, series


@pytest.fixture
def core(synthetic_panel) -> Core:
    dates, series = synthetic_panel
    return Core(gateway=DataGateway(fetch_history=make_fetch(series, dates)))


@pytest.fixture
def spec() -> dict:
    return {
        "spec_version": "1.0",
        "name": "test-rank",
        "universe": {"symbols": ["AAA", "BBB", "CCC"], "source": "prices"},
        # rank_returns always selects the top-N (regardless of sign) so a paper tick on
        # any window yields a deterministic, non-empty target book to delta against.
        "strategy": {"id": "rank_returns", "params": {"lookback": 60, "top": 2}},
        "construction": {"scheme": "equal_weight", "long_only": True, "gross": 1.0},
        "risk": {"max_gross": 1.0, "max_net": 1.0, "max_name_pct": 0.6},
        "execution": {"cost_bps": 5.0, "algo": "market", "rebalance": "monthly@close"},
        "seed": 42,
    }


# --- in-memory platform double ---------------------------------------------------


class _MiniTraceStore:
    """Validates every event against the real TraceEvent contract; gap-free seq per run."""

    def __init__(self) -> None:
        self.events_by_run: dict[str, list[dict]] = {}

    def append(self, event: dict) -> int:
        run_id = str(event["run_id"])
        seq = len(self.events_by_run.get(run_id, []))
        event = dict(event)
        event["seq"] = seq
        # Validate against the closed contract (raises on a bad/extra field).
        TraceEvent.model_validate(event)
        self.events_by_run.setdefault(run_id, []).append(event)
        return seq

    def events(self, tenant_id: str, run_id: str, after_seq: int = -1) -> list[dict]:
        rows = self.events_by_run.get(str(run_id), [])
        return [e for e in rows if str(e["tenant_id"]) == str(tenant_id) and e["seq"] > after_seq]

    def types(self, run_id: str) -> list[str]:
        return [e["type"] for e in self.events_by_run.get(str(run_id), [])]


_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"queued"},
    "queued": {"running"},
    "running": {"succeeded", "failed", "timeout", "promoted"},
    "succeeded": {"promoted"},
    "failed": set(),
    "timeout": set(),
    "promoted": {"live", "retired"},
    "live": {"paused", "retired"},
    "paused": {"live", "retired"},
    "retired": set(),
}


class TransitionConflict(RuntimeError):
    pass


class TransitionError(ValueError):
    pass


class _MiniRunStore:
    """Tenant-scoped run rows with the same transition rules + optimistic guard."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}

    def create(self, tenant_id: str, kind: str, strategy_id, spec) -> str:
        run_id = str(uuid.uuid4())
        self.rows[(str(tenant_id), run_id)] = {
            "tenant_id": str(tenant_id),
            "run_id": run_id,
            "kind": kind,
            "strategy_id": strategy_id,
            "state": "draft",
            "version": 0,
            "spec": spec,
            "result": None,
        }
        return run_id

    def get(self, tenant_id: str, run_id: str):
        row = self.rows.get((str(tenant_id), str(run_id)))
        return dict(row) if row else None

    def list(self, tenant_id: str, kind=None):
        return [
            dict(r)
            for (t, _), r in self.rows.items()
            if t == str(tenant_id) and (kind is None or r["kind"] == kind)
        ]

    def create_research(self, tenant_id: str) -> str:
        run_id = str(uuid.uuid4())
        self.rows[(str(tenant_id), run_id)] = {
            "tenant_id": str(tenant_id),
            "run_id": run_id,
            "kind": "research",
            "strategy_id": None,
            "state": "running",
            "version": 0,
            "spec": None,
            "result": None,
        }
        return run_id

    def transition(self, tenant_id: str, run_id: str, to_state: str, *, expect=None):
        key = (str(tenant_id), str(run_id))
        row = self.rows.get(key)
        if row is None:
            raise KeyError(run_id)
        if expect is not None and expect != row["version"]:
            raise TransitionConflict(f"expected {expect}, found {row['version']}")
        if to_state not in _TRANSITIONS.get(row["state"], set()):
            raise TransitionError(f"illegal {row['state']} -> {to_state}")
        row["state"] = to_state
        row["version"] += 1
        return dict(row)

    def set_result(self, tenant_id: str, run_id: str, result: dict) -> None:
        key = (str(tenant_id), str(run_id))
        if key not in self.rows:
            raise KeyError(run_id)
        self.rows[key]["result"] = result

    # conductor-only cross-tenant reads (mirror the real RunStore)
    def claim_queued(self, kinds=("backtest",), limit=16):
        out = [dict(r) for r in self.rows.values() if r["state"] == "queued" and r["kind"] in kinds]
        return out[:limit]

    def list_by_state(self, state, kind=None, limit=256):
        return [
            dict(r)
            for r in self.rows.values()
            if r["state"] == state and (kind is None or r["kind"] == kind)
        ][:limit]


class _MiniBookStore:
    """Tenant-scoped paper book with an optimistic version guard (matches BookStore)."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}

    def get(self, tenant_id: str, run_id: str):
        row = self.rows.get((str(tenant_id), str(run_id)))
        return dict(row) if row else None

    def ensure(self, tenant_id: str, run_id: str, *, capital: float = 100_000.0):
        key = (str(tenant_id), str(run_id))
        if key not in self.rows:
            self.rows[key] = {
                "tenant_id": str(tenant_id),
                "run_id": str(run_id),
                "capital": float(capital),
                "weights": {},
                "marks": {},
                "version": 0,
            }
        return dict(self.rows[key])

    def apply(self, tenant_id: str, run_id: str, *, target_weights, marks=None, expect=None):
        key = (str(tenant_id), str(run_id))
        row = self.rows.get(key)
        if row is None:
            raise KeyError(run_id)
        if expect is not None and expect != row["version"]:
            raise RuntimeError(f"book version mismatch: expected {expect}, found {row['version']}")
        row["weights"] = {
            str(s).upper(): round(float(w), 6)
            for s, w in target_weights.items()
            if abs(float(w)) > 1e-9
        }
        row["marks"] = {str(s).upper(): float(m) for s, m in (marks or {}).items()}
        row["version"] += 1
        return dict(row)


class Platform:
    def __init__(self) -> None:
        self.runs = _MiniRunStore()
        self.trace = _MiniTraceStore()
        self.books = _MiniBookStore()


@pytest.fixture
def platform() -> Platform:
    return Platform()


@pytest.fixture
def durable_platform() -> DurablePlatform:
    return DurablePlatform(":memory:")


@pytest.fixture
def tenant_id() -> str:
    return str(uuid.uuid4())


def seed_queued_run(platform: Platform, tenant_id: str, spec: dict, kind: str = "backtest") -> str:
    """Create a run and advance draft -> queued (the control plane's pre-worker state)."""
    run_id = platform.runs.create(tenant_id, kind, str(uuid.uuid4()), spec)
    platform.runs.transition(tenant_id, run_id, "queued", expect=0)
    return run_id
