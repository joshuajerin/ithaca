---
name: API security hardening
description: Where the api-server's institutional security controls live and the non-obvious constraints around them.
---

# API security hardening (api-server)

Central module: `app/security.py` — `allowed_origins()` (CORS allow-list from
REPLIT_DOMAINS/REPLIT_DEV_DOMAIN, **never `*`** so `allow_credentials=True` is
safe), `SecurityHeadersMiddleware`, `BodySizeLimitMiddleware` (16MB→413),
sliding-window `rate_limit(bucket,limit,window)` dependency. Wired in `main.py`.
Per-firm AI code-execution kill-switch: `app/firm_settings.py` (DB table +
in-mem fallback, default on). Threat model: `artifacts/api-server/SECURITY.md`.

**Rate limiter auto-disables under tests** via `PYTEST_CURRENT_TEST` or
`TERMINAL_RATELIMIT_DISABLED=1` — a combined pytest session hammers auth from one
synthetic IP and would otherwise 429. Standalone single-file runs stay under
limits. Unit-test the core through `security._check` (bypasses the disable),
integration through the dependency.

**Code-execution containment is structural, not heuristic.** `code_guard.py`
AST allow-list excludes `os`, networking, `subprocess`, `app.*`, DB drivers, and
all dynamic-exec — so generated code *cannot* read env secrets or reach the DB /
other firms. Endpoints (`/feature-request`, `DELETE /features/{type}`) gate on
`require_codegen_enabled` → `require_role("admin")` + firm toggle. Validated
features run **in-process** (no restart), so the guard + isolated validation
subprocess are the boundary.

## SAST/semgrep nosemgrep gotchas (the part that bit me)
- `runSastScan` reads the **working tree** (line numbers move with your edits),
  but `# nosemgrep` is only honored **on the same line as the match** — a comment
  on the preceding line does NOT suppress.
- `# nosemgrep: <text>` parses everything after the colon as a **comma-separated
  list of rule-ids**; free-text justification there silently fails to suppress.
  Use **bare `# nosemgrep`** (suppresses all rules on that line) and put the
  reason in a normal comment nearby.
- Confirmed false positives in this repo: gitleaks `generic-api-key` fires on
  plain numeric constants like `DEFAULT_CAPITAL = 1_000_000.0` (underscore
  grouping looks high-entropy). All real secrets come from `os.environ`.

## XML XXE
External XML (SEC EDGAR Form 4/13F in `app/sources/{edgar,thirteenf}.py`) is
parsed with **`defusedxml.ElementTree`**, not stdlib `xml.etree` (semgrep
`use-defused-xml` HIGH). `defusedxml` is a declared dependency.

**Why:** Task #345 institutional security pass. Scans must come back 0
critical/0 high; remaining MEDIUMs are non-crypto MD5/SHA1 cache keys, accepted
in SECURITY.md.
