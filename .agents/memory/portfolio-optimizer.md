---
name: Portfolio construction & optimization
description: Durable decisions for the optimizer pillar — real-data inputs, why solvers are home-grown, and the constraint-incompatibility traps that produce degenerate books.
---

# Portfolio Construction & Optimization

Same three-layer shape as the factor-risk-model and signal-library pillars: a
pure-numpy engine, an honest-coverage data bridge, and a passthrough skill/panel.

## Decisions worth keeping

- **No scipy in this repl.** All solvers (mean-variance, Black-Litterman, ERC risk
  parity, HRP) are home-grown numpy. Constraints are enforced by **Dykstra
  alternating projection** onto the intersection of box / sector-cap / gross / net
  sets — not a QP. **Why:** no QP library available; alternating projection is the
  simplest thing that satisfies all constraint sets at once.

- **Expected returns are factor-implied, not a separate forecast:**
  `mu = exposures @ factor_ann_returns`, reusing the risk model's covariance.
  **Why:** keeps the pillar real-data-only and consistent with the factor model;
  don't introduce an independent return model.

## Traps (cost real debugging — don't reintroduce)

- **Risk parity / HRP are inherently long-only & fully invested.** If a request
  carries shorting or market-neutral (net=0), projecting onto {w>=0, sum=0}
  collapses to an **all-zero degenerate book**. Reconcile these methods to
  long-only net=1 and *report* the override — never silently emit zeros.

- **Never silently relax a user constraint.** Two infeasibilities recur: a
  per-name cap below |net|/n, and a **gross budget below |net|** (gross = Σ|w| ≥
  |Σw| = |net| is a hard identity, so gross<|net| is impossible). Both must be
  loosened to stay solvable AND surfaced (panel/voice note + status), not hidden.
  The engine floors `gross_limit()` at |net| so projection never silently
  violates; the bridge reports the relaxation. Silently changing intent (either
  one) was a code-review reject.

- **Heuristic routing:** put the optimizer branch *before* the risk-model/risk
  branches (the phrases "risk parity"/"minimum variance" contain "risk"/"variance"),
  and only prefer explicit symbols when >=2 are given — `_extract_symbols` returns
  single-letter false positives (e.g. "A" from the word "a").

- **Big expected-return magnitudes are expected**, not a bug — factor premia ×
  tilts, annualized the same way the factor model does.
