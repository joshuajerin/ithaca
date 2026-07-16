# Agent-driven Ithaca onboarding

This is the instruction contract for an AI agent that is asked to install and
verify Ithaca MCP on a user’s machine.

## Goal

Finish with an authenticated Ithaca MCP connection that still works after the
client is closed and reopened. Do not stop at “configuration written.”

## Rules for the installing agent

1. Never ask the user to paste an Ithaca API key when the client supports OAuth.
2. Never create or export `ITHACA_MCP_API_KEY` for interactive use.
3. Never use `mcp.doomberg.me`.
4. Never claim success until a fresh client session makes an authenticated
   Ithaca tool call.
5. Never print OAuth tokens, compatibility keys, passwords, or one-time callback
   state values.
6. Preserve all unrelated MCP servers.
7. Remove the legacy `doomberg` entry only when it points at
   `https://mcp.doomberg.me/mcp`.
8. Treat `VITE_CLERK_PUBLISHABLE_KEY` errors as a server deployment incident,
   not as a local setup task.

## Procedure

### 1. Identify the client

Detect the active client from its executable or configuration:

```bash
command -v codex
command -v claude
command -v hermes
```

If none match, locate the client’s official MCP documentation and configuration
path. Determine whether it supports:

- remote HTTP MCP;
- MCP OAuth;
- custom HTTP headers;
- user/global configuration;
- an MCP reload or restart command.

### 2. Run the Ithaca doctor

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --doctor
```

Stop if it fails. Report the exact doctor error without exposing credentials or
one-time state.

### 3. Run the correct installer

Codex:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client codex --login
```

Claude Code:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client claude-code --login
```

Claude Code on a remote/headless host:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client claude-code --login --headless
```

Hermes:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client hermes --login
```

Generic OAuth JSON client:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client generic --config /absolute/path/to/mcp.json
```

OpenClaw or another JSON client without OAuth:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - \
  --client openclaw --auth api-key
```

Use compatibility mode only after confirming that native MCP OAuth is
unavailable.

### 4. Complete browser approval

The installer should open the Ithaca app first. Clerk may then open
`accounts.tradeithaca.com` for sign-in and approval.

If Hermes is sent to an Ithaca `/agent-link` URL with `auth=api-key`, stop. That
is the old flow. Rerun the current Hermes OAuth installer.

### 5. Reload the client

Use the client’s supported reload:

- Codex: close the session and start a new one;
- Claude Code: close the process and start a new one;
- Hermes: run `/reload-mcp` or restart Hermes;
- gateway-based agents: restart or reload the gateway after configuration.

### 6. Verify the registration

```bash
codex mcp get ithaca
claude mcp get ithaca
hermes mcp list
hermes mcp test ithaca
```

Confirm the canonical URL:

```text
https://mcp.tradeithaca.com/mcp
```

Confirm that no active `doomberg` registration remains.

### 7. Verify authenticated tools

Ask the fresh agent session:

```text
Use the Ithaca MCP server. Call ithaca_init with the user’s actual research
goal. Then call search_skills and report the available capabilities.
```

If the agent reports that Ithaca is not logged in, run only the client’s login
command and repeat the fresh-session test.

### 8. Verify persistence

Close the client completely. Open it again in a new session, and for Codex or
Claude Code use a different repository. Repeat `ithaca_init`.

Success requires:

```text
registration present
authentication reused
tools discovered
ithaca_init succeeded
no browser login repeated
```

## Completion report

Return:

```text
Client:
Config scope/path:
MCP URL:
Authentication: OAuth or compatibility key
Legacy Doomberg entry removed: yes/no/not present
Fresh-session ithaca_init: passed/failed
30-day refresh-capable OAuth: yes/no/not applicable
Anything requiring user action:
```

Do not include credentials, token-file contents, passwords, or callback state.

See [Ithaca MCP client setup](AGENT_CLIENT_SETUP.md) for recovery commands and
client-specific details.
