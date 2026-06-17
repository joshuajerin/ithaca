---
name: API Server boot smoke check
description: The boot smoke check (run command + why it is NOT a registered validation in this multi-artifact repo), the yfinance MAX_PATH agent-bash quirk, and the TERMINAL_SKIP_WORKER hook.
---

`scripts/smoke-api.sh` boots the API Server against the live `.pythonlibs` env, waits
for `/api/healthz`, and asserts `POST /api/orchestrate` returns 200. It exists to catch
the class of "server can't boot" failures (missing/declared-but-uninstalled Python deps
→ ModuleNotFoundError, import errors, broken startup) before they ship. It is exposed as
the root pnpm script `pnpm smoke:api`.

## Why it is a pnpm script, NOT a registered validation (platform limitation)
**Do not register this via the validation skill (`setValidationCommand`) in this repo.**
`setValidationCommand` ALWAYS injects an explicit `[[workflows.workflow]] name="Project"`
block into `.replit` (mode=parallel → `workflow.run <validation>`) plus `runButton="Project"`.
In a multi-artifact repo the `Project` run button is normally *synthesized* from each
`artifact.toml` to run all artifacts; the injected explicit `Project` block OVERRIDES that
synthesis, so the Run button then runs only the validation and the app no longer starts.
**No tool can remove ONLY that block:** `.replit` edits are blocked (edit tool AND bash),
`removeWorkflow("Project")` → "not found" (Project is not a tracked workflow),
`verifyAndReplaceArtifactToml` does not touch `[workflows]`, `configureWorkflow` only makes
single-command workflows (can't express a parallel run-all-artifacts Project), there is no
run-button tool, and `clearValidationCommand` wipes the whole `[workflows]` stanza.
**How to apply:** keep boot/smoke checks as runnable scripts (`pnpm smoke:api`) here. If you
must register a real validation, expect the Run button to break and budget for escalating
the `setValidationCommand` multi-artifact bug — there is currently no clean in-repo fix.

## Environment quirk: yfinance subprocess spawn fails in the agent's bash tool
**Symptom:** running anything that triggers `yf.Ticker(sym).info` (worker fundamentals
loop, or orchestrate's on-demand data refresh) inside the **agent's bash/code_execution
tool** dies with:
```
run process: run_parent
  ... get_target_path ... path exceeds MAX_PATH
```
**Why:** the agent's bash sandbox intercepts process exec via a run-wrapper whose
target-path computation overflows; yfinance spawns a child process that trips it.
The real **workflow** and a normal repl shell run like normal app processes and do NOT
hit this — orchestrate returns 200 there (verified via the workflow on localhost:8080).
**How to apply:** you cannot fully exercise orchestrate's data path from the agent's
own bash tool — verify it via the running workflow (curl localhost:$PORT). `pnpm smoke:api`
works for the user in a normal repl shell but may trip MAX_PATH if you run it directly in
the agent's bash tool.

## TERMINAL_SKIP_WORKER hook
`worker.start()` early-returns when `TERMINAL_SKIP_WORKER=1`. The boot smoke check sets
this so the server boots fast without launching the continuous live-ingestion loops
(hundreds of network calls). Default/unset = normal behavior (worker runs). This is a
test-only hook; do not rely on it in production paths.
