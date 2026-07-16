# Ithaca agent setup

Ithaca’s MCP endpoint is:

```text
https://mcp.tradeithaca.com/mcp
```

Codex, Claude Code, and any standards-compatible MCP agent use Clerk OAuth. The server
advertises `openid` and `offline_access`, allowing the client to refresh its connection for
at least 30 days unless the user revokes access or clears local credentials. No API key,
shell startup file, or `ITHACA_MCP_API_KEY` environment variable is required.

```bash
codex mcp add ithaca --url https://mcp.tradeithaca.com/mcp
codex mcp login ithaca --scopes openid,offline_access

claude mcp add --transport http --scope user ithaca https://mcp.tradeithaca.com/mcp
claude mcp login ithaca
```

For any other MCP agent, add the following standard remote-server configuration at the
client’s MCP JSON path, then use its Connect/Login action:

```json
{"mcpServers":{"ithaca":{"type":"http","url":"https://mcp.tradeithaca.com/mcp"}}}
```

The dependency-free installer performs metadata discovery, opens `app.tradeithaca.com`
first, preserves existing valid Codex and Claude Code registrations, and then opens Clerk’s
approve/deny flow:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --login

# Any MCP agent with a JSON configuration file:
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client generic --config /path/to/mcp.json
```

Its status is deliberately precise: `configured`, `authentication_required`, `authenticated`,
`verified`, or `failed`. `--auth api-key` is only for CI and clients unable to use MCP OAuth;
those keys are scoped, stored only in the client’s protected configuration, and can be
revoked in Settings.

If discovery fails, confirm that `/.well-known/oauth-protected-resource/mcp` is reachable on
the MCP host and advertises `https://mcp.tradeithaca.com/mcp` with both `openid` and
`offline_access`.
