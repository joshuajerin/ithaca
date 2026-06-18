---
name: Debounced effect timer starvation in panels
description: Why a debounced re-run effect in a terminal panel can silently never fire, and how to make it reliable.
---

# Debounced re-run effects must not depend on churning references

Terminal dashboard panels receive their `data` (the parsed panel payload) as a prop
from the Dashboard parent, which re-renders frequently (live data polling,
framer-motion animation). On many of those re-renders the parent passes a **new
`data` object reference** even when content is unchanged.

If a debounced side-effect (e.g. "re-run the projection 450ms after the user edits a
slider") is written as:

```ts
const run = useCallback(async () => { ...uses data.symbols... }, [data.symbols]);
useEffect(() => {
  const t = setTimeout(run, 450);
  return () => clearTimeout(t);
}, [horizon, drift, dirty, run]); // ← `run` identity churns with data
```

then every incidental parent re-render changes `run`'s identity, the effect cleanup
fires, and the 450ms timer is rescheduled. When re-renders arrive faster than the
debounce window, **the timer never completes and the action never fires** — and it
presents as *flaky*: it works whenever there happens to be a render gap, fails when
there isn't.

**Why:** this caused the What-If Scenario "instant re-run" to fire sometimes and
silently do nothing other times in e2e tests.

**How to apply:**
- Keep mutable inputs (e.g. `data.symbols`, `canTune`) in a `useRef` you assign on
  every render, and make the callback `useCallback(..., [])` so it is referentially
  stable.
- Make the debounce `useEffect` depend on **primitives only** (the edited values +
  a `dirty` flag), never on `data` or the callback.
- Same principle for a panel's "reset local edits when a new payload arrives" effect:
  key it off a **stable string signature** of the parsed scenario
  (`prompt|scope|symbols|horizon|drift`), not the `data` object reference — otherwise
  every re-render wipes the user's in-progress tweaks.
