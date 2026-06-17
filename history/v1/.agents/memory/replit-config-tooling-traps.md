---
name: Replit config tooling traps (.replit runButton, package firewall)
description: Two non-obvious environment traps — validation tooling clobbers the Project run button, and the package firewall blocks installing a JS test runner.
---

# Validation tooling clobbers `.replit` runButton="Project"

`setValidationCommand` materializes a concrete `[[workflows.workflow]] name="Project" mode="parallel"`
whose only task runs the validation command. In a multi-artifact workspace the Run button ("Project")
is normally **synthesized by the platform** from the artifact workflows (there are NO `[[workflows.workflow]]`
blocks in `.replit`; just `[workflows]` + `runButton = "Project"`). Materializing a concrete Project block
**hijacks** the Run button to run only the validation, not the app.

`clearValidationCommand` then **over-removes**: it deletes the Project block AND the `runButton = "Project"`
line (which it did not add), leaving `[workflows]` empty.

**The bare `runButton = "Project"` line cannot be restored via available tooling:**
- Direct edits to `.replit` are blocked ("owned by a different tool").
- `verifyAndReplaceArtifactToml` (artifact re-sync) does NOT rewrite it.
- `restartWorkflow` on an artifact does NOT rewrite it.
- `configureWorkflow` has no runButton param; setting a validation again only re-adds the hijack block.
- Only platform reconciliation on merge (or a manual `.replit` edit) restores it.

**Why:** the run button for multi-artifact repls is platform-synthesized; the validation system assumes a
single-app layout and rewrites the Project workflow.
**How to apply:** avoid `setValidationCommand`/`clearValidationCommand` in multi-artifact repls. To gate code
quality, run tests directly (e.g. `python tests/test_x.py`) rather than registering a validation workflow.

# Package firewall blocks installing `vitest`

`pnpm --filter <pkg> add -D vitest` fails with `ERR_PNPM_FETCH_403` from `package-firewall.replit.local`
("No authorization header"). Per the package-management skill, a 403 from the firewall is a security block —
**do not retry**. Notably `jsdom` and `@testing-library/*` install fine; only `vitest`'s tarball is blocked.

**Consequence:** a committed JS/React test runner cannot be added here. The terminal artifact's components
also rely on Vite-only features (`import.meta.glob`, the `@/` alias, runtime TSX), so a non-vitest runner
(node:test + tsx) is impractical. Frontend end-to-end verification must go through the sanctioned `runTest`
tool (Playwright-based, against the running dev server) rather than a committed spec.
**How to apply:** for frontend flow verification, lean on committed **backend** harness tests for the
deterministic pipeline + `runTest` for the live UI. Don't burn time trying to install vitest/playwright.
