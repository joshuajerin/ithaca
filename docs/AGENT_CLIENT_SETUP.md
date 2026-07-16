# Ithaca agent setup

Ithaca’s MCP endpoint is:

```text
https://mcp.tradeithaca.com/mcp
```

Codex, Claude Code, and Cursor use Clerk OAuth. Add the bare URL, complete the browser
login, and let the client retain its short-lived OAuth credentials. No API key, shell startup
file, or `ITHACA_MCP_API_KEY` environment variable is required.

```bash
codex mcp add ithaca --url https://mcp.tradeithaca.com/mcp
codex mcp login ithaca --scopes openid offline_access
```

For Cursor, add this to `~/.cursor/mcp.json` and select Connect/Login in the app:

```json
{"mcpServers":{"ithaca":{"type":"http","url":"https://mcp.tradeithaca.com/mcp"}}}
```

The dependency-free installer performs metadata discovery before changing any configuration:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3
```

Its status is deliberately precise: `configured`, `authentication_required`, `authenticated`,
`verified`, or `failed`. `--auth api-key` is only for CI, custom clients, OpenClaw, Hermes,
and other clients unable to use MCP OAuth; those keys are scoped, stored only in the client’s
protected configuration, and can be revoked in Settings.

If discovery fails, confirm that `/.well-known/oauth-protected-resource/mcp` is reachable on
the MCP host and advertises `https://mcp.tradeithaca.com/mcp` with `openid`.
