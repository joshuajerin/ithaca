---
name: Generated-panel production runtime test
description: How the AI-generated panel production loading path is tested under vitest, and the registry-glob design that makes it possible outside a real build.
---

# Testing the generated-panel production runtime path

The production path for AI-generated panels (fetch TSX from `GET /api/generated-panels`
→ transpile with sucrase → eval → render, generic fallback on failure) lives in
`registry.ts` + `DynamicPanel.tsx`. It cannot be exercised by the dev server (dev uses
Vite HMR / `import.meta.glob`). The test for it lives in
`artifacts/terminal/src/components/terminal/panels/generated/__tests__/production-runtime.test.tsx`.

## Runner: vitest (jsdom per-file)
The terminal uses **vitest** (`vitest.config.ts`, `pnpm --filter @workspace/terminal test`).
The global vitest env is `node`; this React-rendering test opts into jsdom with a
`// @vitest-environment jsdom` docblock on line 1. The config `include` covers both
`*.test.ts` and `*.test.tsx`, and `plugins: [react()]` so app components transform the
same way they do in the real build.
**History:** an earlier attempt used Node's built-in runner because `vitest` was
firewall-blocked (HTTP 403 on the tarball). That block was later lifted upstream — vitest
is the committed standard now; do not reintroduce a parallel `node:test` runner.

## Why the runtime path is still exercised under vitest
Under vitest (which runs through Vite), `import.meta.glob('./*.tsx',{eager:true})` in
`registry.ts` DOES resolve (unlike a bare Node runtime, where the try/catch falls back to
an empty registry). The test panel type is written to disk in `beforeAll` — AFTER the test
module (and the registry it imports) has been evaluated — so it is never in the static glob
registry. `getGeneratedComponent` returns undefined for it, forcing `loadGeneratedComponent`
(fetch + sucrase + eval). This mirrors a production runtime loading a post-build panel.
**Do not** refactor the glob into a variable first — Vite only transforms the literal
`import.meta.glob(...)` call expression; the try/catch is what lets it import outside Vite.

## What the test does
Real `vite build` in `beforeAll` (needs `PORT` + `BASE_PATH` env; ~180s hook timeout) →
write a fresh panel `.tsx` into the generated dir AFTER the build → assert its marker is
absent from `dist` (proves it can only load via the runtime path) → mock `globalThis.fetch`
to return that source and render `<DynamicPanel>`, asserting the compiled component renders;
separate cases assert the generic fallback for disallowed-import / no-default-export /
broken-syntax sources. Test cleans up the temp file in `afterAll`. Test files are excluded
from the production tsconfig (run via vitest only). Registered as the `panel-runtime-test`
validation workflow in `.replit`.
