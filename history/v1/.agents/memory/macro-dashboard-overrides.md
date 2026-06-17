---
name: Macro dashboard asset customization
description: Non-obvious contracts when adding pin/add/remove customization to the macro_dashboard panel and its refine flow.
---

# Macro dashboard overrides — gotchas

Refine instructions let users pin/remove macro tiles (e.g. "add EURUSD",
"remove VIX from the risk view"). Three things that bite if you forget them:

- **Persisted refine state must be a field on the pydantic data model.**
  The harness validates builder output with `model.model_validate(...).model_dump()`,
  which silently drops unknown keys. Any state you want to survive across
  refines (here, `overrides`) has to be declared on the model or it vanishes.
  **Why:** refines accumulate by reading the panel's own prior `data`.

- **Refine must special-case subject-agnostic panels before the generic path.**
  The generic heuristic returns `{}` for panels with no symbol/sector, which
  would wipe the panel's theme. `macro_dashboard` is handled first in both
  `_refine_params_llm` and `_refine_params_heuristic`.

- **Never resolve theme unconditionally in the heuristic.**
  `data.resolve_macro_theme()` falls back to "global", so calling it on a plain
  "add gold" would reset the theme. Detect an explicit theme word first and
  keep the current theme otherwise.

Other conventions: only real `MACRO_ASSETS` symbols are honored (unknown ones
ignored, honest-data); overrides merge latest-op-per-symbol so a later add
cancels a prior remove; `data.resolve_macro_symbols()` matches aliases
longest-first and consumes matches so "2y-10y" doesn't also match "2y".
