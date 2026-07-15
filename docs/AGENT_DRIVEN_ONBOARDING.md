# Ithaca agent-driven onboarding

Run the installer with `--agent-init` for supported native OAuth clients. It registers the
bare Ithaca MCP URL and completes the client login when the CLI supports it:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --agent-init
```

After the client reloads its MCP configuration, call:

```text
ithaca.ithaca_init(goal="<user goal>")
```

OAuth is the normal path. API-key compatibility mode is explicit (`--auth api-key`) and is
intended for automation-only clients; do not use it for Codex, Claude Code, or Cursor unless
OAuth is unavailable.
