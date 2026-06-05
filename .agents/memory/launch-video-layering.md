---
name: Launch video layering & perf
description: How the launch-video artifact avoids transition lag and text/background overlap.
---

# Launch video layering & perf

The launch-video template composites persistent layers controlled by a derived
`baseSceneKey` (strip `_r[12]$` off `currentSceneKey`), NOT by remounting per scene.

**Perf rules (lag fixes):**
- DotWaveBackground keeps ONE persistent rAF loop (useEffect deps `[]`); pass
  `active` via a ref so toggling it never restarts the loop. Restarting rAF on every
  scene change was the main source of transition lag.
- Never animate CSS `filter: blur()` or use `backdrop-blur` in scenes — both tank
  framerate. Animate only opacity / scale / translate / scaleY.
- Cap canvas dpr (~1.5), widen dot spacing (~30), lerp amplitude for smoothness.

**Overlap fixes (readability):**
- Text scenes sit above the canvas with a `CenterScrim` (radial black gradient) or a
  solid `bg-black/NN` panel behind copy. Lower the canvas max dot alpha (~0.6) so dots
  never compete with white text.
- The Voice Orb is a single persistent element repositioned per scene (x/y/scale +
  `visible` opacity prop) so it never sits under body text.

**Why:** user reported "laggy on transitions, text overlaps in bg and front."
**How to apply:** when adding scenes, gate persistent layers (DotWave/Orb/Dashboard)
on `baseSceneKey`; give every text scene its own scrim; keep AnimatePresence keyed by
`currentSceneKey` (not baseSceneKey) so the scene-lock `_r1/_r2` loop still re-fires.
Strict monochrome — no green.
