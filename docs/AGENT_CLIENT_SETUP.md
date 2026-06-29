# Agent Client Setup

Doomberg exposes one hosted streamable-HTTP MCP endpoint:

```text
https://mcp.doomberg.me/mcp
```

Users should connect through the installer instead of hand-editing config files:

```bash
curl -fsSL https://app.doomberg.me/install.py | python3
```

The installer opens the Doomberg app, waits for the signed-in user to approve a scoped MCP key, stores the key in `~/.config/doomberg/mcp.env`, configures local clients as `doomberg`, verifies the hosted MCP server, calls `doomberg_init`, and writes a generated tool guide to `~/.config/doomberg/TOOLS.md`.

## Default Setup

By default, the installer configures all first-class clients:

```bash
curl -fsSL https://app.doomberg.me/install.py | python3
```

Clients:

| Client | Setup behavior |
| --- | --- |
| Cursor | Merges `doomberg` into `~/.cursor/mcp.json` without removing existing `mcpServers`. |
| Claude Code | Uses `claude mcp add --transport http --scope user` when the CLI exists; otherwise writes `~/.claude/mcp.json`. The Claude config uses `Authorization: Bearer ${DOOMBERG_MCP_API_KEY}` so the token stays in the Doomberg env file instead of being hardcoded into Claude config. |
| Codex | Uses `codex mcp add doomberg --url ... --bearer-token-env-var DOOMBERG_MCP_API_KEY`. |
| OpenClaw | Writes `~/.openclaw/mcp.json`. |
| Hermes | Writes `~/.hermes/mcp.json`. |

After client registration, the installer runs a real MCP `initialize` exchange, calls:

```text
doomberg.doomberg_init(goal="<install smoke goal>")
```

and generates `~/.config/doomberg/TOOLS.md` from the server's live `tools/list`, `doomberg://toolkits/catalog`, and `doomberg://skills/catalog` responses. Agents should read that file after reload when they need the current toolkits and first-call workflow without spending context on the full catalog.

## Target One Client

Use `--client` when setting up a single client:

```bash
curl -fsSL https://app.doomberg.me/install.py | python3 - --client cursor
curl -fsSL https://app.doomberg.me/install.py | python3 - --client claude-code
curl -fsSL https://app.doomberg.me/install.py | python3 - --client codex
curl -fsSL https://app.doomberg.me/install.py | python3 - --client openclaw
curl -fsSL https://app.doomberg.me/install.py | python3 - --client hermes
```

Accepted aliases include `claude`, `claude code`, `claudecode`, and `all`.

## Security Model

The local agent receives a tenant-scoped Doomberg API key. The key is sent as:

```text
Authorization: Bearer dmbg_...
```

Installer rules:

- The API key is written only to local user config, not the repository.
- Claude Code and Codex configs reference `DOOMBERG_MCP_API_KEY`; they do not embed a bearer token directly.
- JSON config merges preserve existing MCP servers.
- Existing malformed JSON is moved aside to a timestamped backup before writing a fresh config.
- `deploy:live` is not issued to the agent setup flow.

## Local Verification

Run focused checks after installer changes:

```bash
python3 -m py_compile scripts/install_agent_mcp.py
uv run --package doomberg-rest-gateway pytest -q services/rest-gateway/tests/test_installer.py
```
