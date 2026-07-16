# Always-on Ithaca agent operations

Ithaca’s MCP server is hosted. Codex, Claude Code, Hermes, and other clients do
not need a local Ithaca daemon. They connect to
`https://mcp.tradeithaca.com/mcp` when a session starts.

“Always on” therefore has two separate meanings:

1. Ithaca’s hosted app, OAuth metadata, MCP gateway, workers, and health checks
   stay available;
2. a gateway-based agent such as Hermes or OpenClaw keeps its own process
   running and preserves its local MCP credentials.

## Service checks

Run:

```bash
curl -fsS https://app.tradeithaca.com/livez
curl -fsS https://app.tradeithaca.com/healthz
curl -fsS https://app.tradeithaca.com/readyz
curl -fsS \
  https://mcp.tradeithaca.com/.well-known/oauth-protected-resource/mcp
curl -fsSL https://app.tradeithaca.com/install.py | python3 - --doctor
```

The doctor is the auth-specific canary. It catches the exact failure where the
app container is healthy but its JavaScript bundle was built without Clerk’s
publishable configuration.

## Client credential persistence

OAuth clients should retain:

- the MCP registration;
- the access token;
- the refresh token obtained through `offline_access`;
- user-only file permissions;
- a persistent home directory.

Do not run agent clients with an ephemeral home directory unless the credential
directory is mounted on persistent storage.

Client-specific persistence:

| Client | Registration | OAuth credential behavior |
|---|---|---|
| Codex | user Codex MCP config | reused by new Codex sessions |
| Claude Code | user-scope MCP config | reused across repositories |
| Hermes | `~/.hermes/config.yaml` | `~/.hermes/mcp-tokens/ithaca.json`, mode `0600` |
| Compatibility clients | client MCP config | bearer key persists until revoked |

## Hermes gateway

After completing `hermes mcp login ithaca`, install and run Hermes’s managed
gateway service:

```bash
hermes gateway install --start-now --start-on-login
hermes gateway status --deep
```

After changing MCP configuration:

```bash
hermes mcp test ithaca
hermes gateway restart
```

If the installed Hermes version does not expose `restart`, stop and start the
gateway with that version’s supported commands.

The gateway must run under the same user and `HERMES_HOME` that owns
`~/.hermes/config.yaml` and `~/.hermes/mcp-tokens`.

## OpenClaw and other gateways

Keep the gateway process under its native service manager. Restart it after the
MCP configuration changes. The gateway user must be able to read the client
configuration, but no other user should be able to read stored bearer keys.

Verify from a new conversation, not only from the gateway’s config screen.

## Monitoring policy

Recommended checks:

| Frequency | Check | Failure means |
|---|---|---|
| every minute | `/livez` | app process unavailable |
| every minute | `/readyz` | app cannot safely serve traffic |
| every five minutes | OAuth protected-resource metadata | MCP auth discovery broken |
| after every deploy | installer `--doctor` | Clerk bundle or public branding broken |
| daily | fresh-session `ithaca_init` with E2E account | real client login/tool path broken |

Alert on the first failed post-deploy doctor. Do not wait for a user to report
the `VITE_CLERK_PUBLISHABLE_KEY` page.

## Build and deploy invariant

Every production image must be built with a Clerk publishable key supplied as
`CLERK_PUBLISHABLE_VALUE` or `VITE_CLERK_PUBLISHABLE_KEY`.

The Dockerfile and local build script reject:

- a missing value;
- a value without the `pk_test_` or `pk_live_` prefix;
- a built bundle that does not contain the supplied value;
- a built public bundle that contains `Doomberg`.

Do not bypass these checks for a manual hotfix. Use the same immutable SHA image
path as GitHub Actions.

## E2E test account

The production Clerk E2E account is stored locally in macOS Keychain, not in the
repository:

```text
service: com.tradeithaca.test.oauth-e2e
accounts: email, password, clerk_user_id
```

Never print the password in CI logs or shell history. Retrieve one value at a
time only inside the test process.

The daily client matrix is:

1. run installer doctor;
2. authenticate Codex with the E2E account;
3. call `ithaca_init`;
4. close and reopen Codex, then call it again;
5. repeat for Claude Code;
6. repeat for Hermes using native OAuth;
7. confirm the second run for each client does not open a login page;
8. revoke credentials created only for disposable compatibility tests.

Use a disposable home directory for the target agent’s state, while mounting
only the E2E credential retrieval mechanism required for the test. Never reuse a
developer’s normal MCP configuration for destructive onboarding tests.

## Incident response

### App doctor fails

1. Stop onboarding traffic.
2. Inspect the deployed image tag.
3. Confirm the image came from the expected Git SHA.
4. Inspect the built `web/dist` bundle for the Clerk publishable prefix.
5. Roll forward with a correctly built immutable image.
6. Run doctor again.
7. Run one full fresh-session E2E login.

### Client repeatedly logs out

1. Confirm the registration is user/global scope.
2. Confirm `offline_access` is advertised and requested.
3. Confirm the token file exists after login.
4. Confirm file ownership and mode.
5. Confirm the client home is persistent.
6. Confirm no startup script removes or rewrites the MCP entry.
7. Revoke the broken authorization, log in once, and repeat the two-session test.

### “MCP server is not logged in”

Run the client-specific login command. Do not recreate the server registration
unless its URL is wrong.

## Related

- [Ithaca MCP client setup](AGENT_CLIENT_SETUP.md)
- [Agent-driven onboarding](AGENT_DRIVEN_ONBOARDING.md)
- [Production deploy runbook](../deploy/RUNBOOK.md)
