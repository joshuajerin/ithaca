# Agent-Driven Onboarding

Use this flow when the user asks their AI agent to install Doomberg instead of
running the installer themselves.

## Command

Ask the agent to run:

```bash
curl -fsSL https://app.doomberg.me/install.py | python3 - --agent-init
```

Target one client when needed:

```bash
curl -fsSL https://app.doomberg.me/install.py | python3 - --agent-init --client codex
curl -fsSL https://app.doomberg.me/install.py | python3 - --agent-init --client claude-code
curl -fsSL https://app.doomberg.me/install.py | python3 - --agent-init --client cursor
curl -fsSL https://app.doomberg.me/install.py | python3 - --agent-init --client openclaw
curl -fsSL https://app.doomberg.me/install.py | python3 - --agent-init --client hermes
```

## Flow

1. The agent runs the command.
2. The installer prints a Doomberg approval URL.
3. The agent sends that URL to the user.
4. The user signs in or creates an account and approves the MCP key.
5. The installer receives the key on localhost, writes local config, and registers Doomberg MCP.
6. `--agent-init` verifies the hosted MCP server with a real MCP `initialize` handshake.
7. The agent reloads MCP config, then calls:

```text
doomberg.doomberg_init(goal="<user goal>")
```

The init tool returns the first-call workflow, the session id, and the operating boundaries.

## User-Facing Agent Reply

When the installer prints the URL, the agent should answer with only the approval link and a
short instruction:

```text
Open this Doomberg link, sign in or create an account, then approve MCP access:
<url>
```

After approval, the agent should confirm:

```text
Doomberg MCP is installed and initialized. Restarting or reloading the agent may be required
before the new MCP server appears. First call: doomberg_init.
```

## Boundaries

The installer mints a scoped key for research, backtests, approvals reads, artifacts, and
paper-trading research. It does not mint live-deploy scope.

`doomberg_init` tells the agent to start with:

- `search_skills`
- `describe_skill`
- `run_skill`
- `market_get_ohlcv`
- `propose_strategy`
