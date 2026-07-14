# Agent-Driven Onboarding

Use this flow when the user asks their AI agent to install Ithaca instead of
running the installer themselves.

## Command

Ask the agent to run:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --agent-init
```

If the user already gave a concrete goal, pass it into the post-auth smoke:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --agent-init --init-goal "research AAPL momentum"
```

Target one client when needed:

```bash
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --agent-init --client codex
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --agent-init --client claude-code
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --agent-init --client cursor
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --agent-init --client openclaw
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --agent-init --client hermes
```

## Flow

1. The agent runs the command.
2. The installer prints a Ithaca approval URL.
3. The agent sends that URL to the user.
4. The user signs in or creates an account and approves the MCP key.
5. The installer receives the key on localhost, writes local config, and registers Ithaca MCP.
6. `--agent-init` verifies the hosted MCP server with a real MCP `initialize` handshake.
7. The installer calls:

```text
ithaca.ithaca_init(goal="<user goal>")
```

The init tool returns the first-call workflow, the session id, and the operating boundaries.
It also opens the visible research session.

8. The installer writes `~/.config/ithaca/TOOLS.md` from the live MCP tool list, toolkit
catalog, and skill catalog.
9. The agent reloads MCP config, reads `~/.config/ithaca/TOOLS.md` when it needs current
tool guidance, then continues inside the initialized session or calls `ithaca_init` again
with the user's exact prompt after reload.

## User-Facing Agent Reply

When the installer prints the URL, the agent should answer with only the approval link and a
short instruction:

```text
Open this Ithaca link, sign in or create an account, then approve MCP access:
<url>
```

After approval, the agent should confirm:

```text
Ithaca MCP is installed and initialized. Restarting or reloading the agent may be required
before the new MCP server appears. Current tools guide: ~/.config/ithaca/TOOLS.md.
```

## Boundaries

The installer mints a scoped key for research, backtests, approvals reads, artifacts, and
paper-trading research. It does not mint live-deploy scope.

`ithaca_init` and the generated tools guide tell the agent to start with:

- `search_skills`
- `describe_skill`
- `run_skill`
- `market_get_ohlcv`
- `propose_strategy`

Claude Code config uses `Authorization: Bearer ${ITHACA_MCP_API_KEY}` and Codex uses
`--bearer-token-env-var ITHACA_MCP_API_KEY`; neither path should store a hardcoded
bearer token in repository files.
