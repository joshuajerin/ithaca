---
name: Running Python scripts interactively (MAX_PATH wrapper error)
description: Why ad-hoc `python3 foo.py` fails in this repl and how to actually run a Python snippet against the api-server app.
---

Running Python interactively from bash (e.g. `python3 script.py`, `uv run python …`)
often fails immediately with a Replit run-wrapper error, BEFORE any of your code runs:

```
run process: run_parent
Caused by:
  0: handle_syscall ...
  1: get_target_path
  2: path exceeds MAX_PATH
```

This is NOT your code — the uvicorn workflow runs Python fine. The cause is an
over-long environment variable tripping the syscall interceptor's path check.

**Fix:** invoke the real interpreter with a minimal env, preserving only what's needed:

```
env -i PATH=/usr/bin:/bin HOME=/home/runner \
  UV_PROJECT_ENVIRONMENT=/home/runner/workspace/.pythonlibs \
  .pythonlibs/bin/python3.11 /tmp/script.py
```

To import the api-server package, add its dir to sys.path (the dir name has a hyphen
so it can't be imported as a module): `sys.path.insert(0, "artifacts/api-server")`
then `from app import agent, ai`.

**How to apply:** for HTTP-level checks just curl `https://$REPLIT_DEV_DOMAIN/api/...`
(the proxy needs https). For unit-level checks of agent logic (e.g. forcing
`ai.ai_available = lambda: False` to test fallbacks), use the `env -i` interpreter call.
