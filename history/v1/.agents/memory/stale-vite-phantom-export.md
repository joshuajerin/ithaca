---
name: Stale Vite dev server → phantom "no export named X"
description: When the browser reports a missing export that clearly exists in source, suspect an orphaned dev server / stale Vite graph, not a code bug.
---

A browser SyntaxError like `The requested module '.../api-client-react/src/index.ts' does not provide an export named 'ApiError'` can be a false alarm: the export exists in the current source.

**Why:** Workflows can fail to release their ports between runs ("address already in use ('0.0.0.0', 8080)", "Port 25245 already in use"). The freshly-started workflow can't bind, so the browser keeps talking to the *old* dev server, whose Vite module graph predates a workspace-linked package change (e.g. an orval regen from an auth merge). The stale graph is missing the new export. The `?t=<ts>` cache-buster in the error is the old server re-transforming its own stale modules, which makes it look "fresh."

**How to apply:** Before editing code, verify the export actually exists (rg the source) and check the workflow logs for port-bind failures. If source is correct and ports are stuck, the fix is a clean `restart_workflow` of every affected artifact (SIGKILL clears orphans, rebinds ports, rebuilds the Vite graph) — not a code change. Confirm with a clean browser console (only `[vite] connected`) and a screenshot.
