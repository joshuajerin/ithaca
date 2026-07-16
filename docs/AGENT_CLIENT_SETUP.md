# Ithaca MCP client setup

Use this guide to connect an AI agent to Ithaca’s hosted MCP server and keep the
connection usable across new agent sessions.

## End state

A correct installation has all of these properties:

- the client is named `ithaca`;
- the remote URL is exactly `https://mcp.tradeithaca.com/mcp`;
- OAuth-capable clients store refreshable OAuth credentials locally;
- the OAuth request includes `openid` and `offline_access`;
- the user opens `app.tradeithaca.com` before Clerk’s accounts domain appears;
- opening a new Codex, Claude Code, or Hermes session does not require another login;
- the old `doomberg` MCP entry is removed;
- the client can call `ithaca_init` and list Ithaca tools.

OAuth credentials can refresh for at least 30 days unless the user revokes
access, deletes the client’s local credential store, or the client fails to
save the refresh token. Compatibility API keys are different: they remain valid
until revoked and should only be used by clients that cannot complete MCP OAuth.

## The only production endpoints

```text
App:  https://app.tradeithaca.com
MCP:  https://mcp.tradeithaca.com/mcp
Docs: https://docs.tradeithaca.com
```

Do not use `mcp.doomberg.me`, `app.doomberg.me`, or an `ITHACA_MCP_API_KEY`
environment variable for normal interactive setup.

## Preflight

Run the live doctor before changing client configuration:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --doctor
```

Expected output:

```text
doctor: verified — Ithaca app, Clerk browser config, and MCP OAuth metadata
```

The doctor verifies:

1. the app bundle is branded Ithaca;
2. the app bundle contains Clerk browser configuration;
3. MCP OAuth discovery points at the canonical HTTPS MCP URL;
4. the server advertises both `openid` and `offline_access`.

If the doctor fails, stop. Do not edit local environment variables to work
around it. The failure is on the deployed Ithaca service.

## Choose the authentication path

Use this decision order:

1. If the client supports remote HTTP MCP with OAuth, use OAuth.
2. If the client supports remote HTTP MCP but not OAuth, use a scoped
   compatibility key.
3. If the client has no MCP client capability, install its MCP plugin or bridge.
4. If no MCP plugin or bridge exists, that client cannot connect directly.

Never copy an API key into a client that supports native MCP OAuth.

## Codex

### Install and log in

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client codex --login
```

Equivalent manual commands:

```bash
codex mcp add ithaca --url https://mcp.tradeithaca.com/mcp
codex mcp login ithaca --scopes openid,offline_access
```

The installer preserves an existing correct `ithaca` registration. It only
recreates the registration if the URL is wrong. It also removes a legacy
`doomberg` registration when that registration points at
`https://mcp.doomberg.me/mcp`.

### Verify

```bash
codex mcp get ithaca
```

Confirm that the output contains:

```text
https://mcp.tradeithaca.com/mcp
```

Then close Codex completely, start a new session, and ask it to:

```text
Use the Ithaca MCP server. Call ithaca_init for a simple market-research goal,
then list the available Ithaca tools.
```

The new session must not show “MCP server is not logged in.”

### Recover

If the registration exists but authentication is missing:

```bash
codex mcp login ithaca --scopes openid,offline_access
```

Do not remove and re-add a correct registration as a first step. Re-login is
enough when only the local OAuth credential is missing or expired.

## Claude Code

### Install and log in

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client claude-code --login
```

Equivalent manual commands:

```bash
claude mcp add --transport http --scope user ithaca \
  https://mcp.tradeithaca.com/mcp
claude mcp login ithaca
```

Use user scope. Project-scoped configuration can disappear when the user opens a
different repository, which looks like a logout even when the OAuth token still
exists.

### Remote or headless host

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client claude-code --login --headless
```

The installer runs:

```bash
claude mcp login ithaca --no-browser
```

Open the printed URL on a machine with a browser, approve access, then return to
the terminal as instructed by Claude Code.

### Verify

```bash
claude mcp get ithaca
```

Start Claude Code in a different repository and verify that Ithaca is still
available. Then call `ithaca_init`. A correct user-scoped installation survives
repository changes and new sessions.

### Recover

```bash
claude mcp login ithaca
```

If `claude mcp get ithaca` shows the wrong URL, rerun the installer. If it shows
the correct URL, do not delete the registration; only repeat login.

## Hermes Agent

Hermes supports native OAuth for remote HTTP MCP servers. Ithaca must not send
Hermes through the `/agent-link?...auth=api-key` compatibility page.

### Install and log in

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client hermes --login
```

Equivalent official Hermes commands:

```bash
hermes mcp add ithaca \
  --url https://mcp.tradeithaca.com/mcp \
  --auth oauth
hermes mcp login ithaca
```

Hermes writes the server to `~/.hermes/config.yaml` under `mcp_servers`:

```yaml
mcp_servers:
  ithaca:
    url: "https://mcp.tradeithaca.com/mcp"
    auth: oauth
```

Hermes stores OAuth tokens in:

```text
~/.hermes/mcp-tokens/ithaca.json
```

Hermes protects the token file with mode `0600` and reuses it on later runs.

### Remote or headless host

Run the same login command:

```bash
hermes mcp login ithaca
```

Hermes supports paste-back login. Open the authorization URL on your local
browser, approve it, copy the final redirect URL, and paste it into the remote
terminal. A browser connection error on the final loopback redirect is expected
in paste-back mode.

### Verify

```bash
hermes mcp list
hermes mcp test ithaca
```

Inside a running Hermes conversation, reload MCP after a configuration change:

```text
/reload-mcp
```

Then ask Hermes to call `ithaca_init`. Restart Hermes and repeat the call. The
second run must reuse the saved OAuth tokens without opening another browser.

### Recover

```bash
hermes mcp login ithaca
hermes mcp test ithaca
```

If a URL contains both `client=hermes` and `auth=api-key`, an old Ithaca
installer is being used. Close that page and rerun the current installer. Do not
approve the compatibility key.

The obsolete file `~/.hermes/mcp.json` is not Hermes’s current native OAuth
configuration. The Ithaca installer removes the legacy `doomberg` entry from
that file, but the active OAuth server belongs in `~/.hermes/config.yaml`.

## OpenClaw and clients without MCP OAuth

Use this path only when the installed client or its MCP plugin accepts remote
HTTP MCP but cannot complete OAuth.

For OpenClaw installations using `~/.openclaw/mcp.json`:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client openclaw --auth api-key
```

The browser approval creates a scoped compatibility key and writes:

```json
{
  "mcpServers": {
    "ithaca": {
      "type": "http",
      "url": "https://mcp.tradeithaca.com/mcp",
      "headers": {
        "Authorization": "Bearer <stored-key>"
      }
    }
  }
}
```

The installer preserves every unrelated server and removes only the legacy
`doomberg` entry that points at `https://mcp.doomberg.me/mcp`.

Restart the OpenClaw gateway or agent process after the file changes. Verify from
a fresh session that Ithaca tools are discovered and `ithaca_init` succeeds.
Revoke the compatibility key from Ithaca Settings when the client is retired.

## Any other MCP agent

### Native OAuth

If the client accepts standard `mcpServers` JSON and implements MCP OAuth:

```json
{
  "mcpServers": {
    "ithaca": {
      "type": "http",
      "url": "https://mcp.tradeithaca.com/mcp"
    }
  }
}
```

Or let the installer merge that object into the client’s JSON file:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client generic \
  --config /absolute/path/to/the/client/mcp.json
```

Then use that client’s Connect, Login, or Authorize action.

### Compatibility key

If the client supports HTTP headers but not MCP OAuth:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client generic \
  --config /absolute/path/to/the/client/mcp.json \
  --auth api-key
```

Do not guess a configuration path. First inspect the client’s official
documentation or its existing MCP settings. The installer creates a timestamped
backup, preserves other MCP servers, writes the file with mode `0600`, and never
prints the credential after approval.

### Non-JSON clients

Use the client’s native CLI or configuration format with the same protocol
contract:

```text
transport: remote HTTP
url: https://mcp.tradeithaca.com/mcp
auth: OAuth when supported
fallback header: Authorization: Bearer <compatibility-key>
```

The endpoint is generic. The file format is client-specific.

## Required browser sequence

The user-visible sequence should be:

1. the installer opens `https://app.tradeithaca.com/settings#connect-agent`;
2. the native client begins OAuth;
3. Clerk may use `accounts.tradeithaca.com` for sign-in and approve/deny UI;
4. the client receives and stores OAuth credentials;
5. a new client session reuses those credentials.

Opening `accounts.tradeithaca.com` during Clerk approval is normal. Opening it
as the first Ithaca page is not the intended installer experience.

## Full verification checklist

Run all applicable checks:

```text
[ ] installer doctor passes
[ ] only the canonical Ithaca MCP URL is configured
[ ] no legacy doomberg server remains
[ ] OAuth client requested offline_access
[ ] login completed
[ ] ithaca_init succeeds
[ ] tools are visible
[ ] client was fully closed
[ ] a new client session works without login
[ ] a different repository/session still works
[ ] local credential file has user-only permissions
```

Do not report setup as complete after registration alone. Registration proves
only that the URL was saved. Completion requires an authenticated tool call from
a fresh session.

## Troubleshooting

### “Authentication is not configured” or “Set VITE_CLERK_PUBLISHABLE_KEY”

This is a broken Ithaca web deployment. It is not a Hermes, Codex, Claude Code,
OpenClaw, or local shell configuration problem.

Run:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --doctor
```

Do not set `VITE_CLERK_PUBLISHABLE_KEY` locally. Record the time, client name,
and approval URL without its one-time `state` value, then report the deployment
failure.

### “MCP server is not logged in”

The server registration exists but the client has no usable OAuth token.

Run the client-specific login command:

```bash
codex mcp login ithaca --scopes openid,offline_access
claude mcp login ithaca
hermes mcp login ithaca
```

Then close and reopen the client.

### Login works once, then a new session logs out

Check these in order:

1. the client registration is user/global scope, not project scope;
2. `offline_access` was requested;
3. the client’s credential file persists across sessions;
4. the credential file is writable by the current user;
5. a cleanup script or ephemeral container is not deleting the client home;
6. the user has not revoked access in Ithaca or Clerk.

### OAuth discovery fails

Verify:

```bash
curl -fsS \
  https://mcp.tradeithaca.com/.well-known/oauth-protected-resource/mcp
```

The document must advertise:

```text
resource: https://mcp.tradeithaca.com/mcp
scopes_supported: openid and offline_access
authorization_servers: HTTPS Clerk authorization server
```

### Compatibility callback fails

Compatibility approval URLs contain a one-time state value and callback URL.
Do not reuse or share them. Restart the installer to generate a new URL.

For Hermes, do not use compatibility callbacks at all. Use native OAuth.

## Related

- [Agent-driven onboarding](AGENT_DRIVEN_ONBOARDING.md)
- [Always-on operations](AGENT_OPERATIONS.md)
- [Production deploy runbook](../deploy/RUNBOOK.md)
