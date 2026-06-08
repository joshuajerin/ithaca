"""Portfolio construction & optimization (pure numpy).

Turns expected returns (mu) and a covariance matrix (Sigma) into target weights
under real-world constraints, using the standard quant construction methods:

- Mean-variance      — min-variance / max-Sharpe / target-vol modes.
- Black-Litterman    — blend a market-implied equilibrium prior with views.
- Risk parity        — equal risk contribution (long-only).
- Hierarchical risk parity (HRP) — Lopez de Prado's cluster-based allocation.

Constraints supported: long-only vs long/short, per-name max position, sector
caps, gross/net exposure limits, and a turnover penalty relative to a current
book. The module is intentionally pure and deterministic (numpy + stdlib only,
no DB / network / scipy) so it is trivially unit-testable — callers own sourcing
mu / Sigma / market weights / sector map and the live/mock provenance decision.

All inputs/outputs are annualized to match the risk model: ``cov`` is the
annualized asset covariance and ``mu`` the annualized expected return vector.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

TRADING_DAYS = 252


# ----------------------------- constraints -----------------------------
@dataclass
class Constraints:
    """Real-world portfolio constraints.

    ``long_only`` forces every weight >= 0 (the lower bound becomes 0); otherwise
    names may be shorted down to ``-max_position``. ``net`` is the target sum of
    weights (1.0 = fully invested; 0.0 = market-neutral). ``gross`` caps the sum
    of absolute weights (only binds for long/short books). ``sector_caps`` maps a
    sector id to its maximum absolute weight share. ``turnover_penalty`` is the
    lambda on the L1 distance to ``current`` (a name->weight map of the existing
    book) added to the mean-variance objective.
    """

    long_only: bool = True
    max_position: float = 1.0
    net: float = 1.0
    gross: Optional[float] = None
    sector_caps: Dict[str, float] = field(default_factory=dict)
    turnover_penalty: float = 0.0
    # Per-name lower-bound override (length n). Used to forbid shorting a name
    # whose borrow is locate-infeasible: set its floor to 0 so the optimizer can
    # still go long but never short it. Tightens (raises) the box floor only.
    lb_override: Optional[np.ndarray] = None
    # Per-name annual borrow/short cost (length n, as a return drag e.g. 0.03 =
    # 300bps). Enters the utility as a linear penalty on the short leg, so the
    # optimizer only shorts a name when its expected alpha clears its borrow fee.
    short_cost: Optional[np.ndarray] = None

    def bounds(self, n: int) -> Tuple[np.ndarray, np.ndarray]:
        hi = float(max(1e-6, self.max_position))
        lo = 0.0 if self.long_only else -hi
        lo_arr = np.full(n, lo, dtype=float)
        hi_arr = np.full(n, hi, dtype=float)
        if self.lb_override is not None:
            ov = np.asarray(self.lb_override, dtype=float)
            if ov.shape == lo_arr.shape:
                # Raise the floor toward (at most) 0 where shorting is blocked;
                # never loosen below the structural lower bound.
                lo_arr = np.maximum(lo_arr, ov)
        return lo_arr, hi_arr

    def gross_limit(self) -> float:
        # Gross = sum|w| >= |sum w| = |net| is a hard identity, so a gross budget
        # below |net| is infeasible; floor it at |net| so the projection can never
        # silently violate the constraint. Callers that want to surface the
        # infeasibility should compare the requested gross to |net| up front.
        if self.gross is not None:
            return max(float(self.gross), abs(self.net))
        # Long-only fully-invested books have gross == |net|; long/short default
        # to a 200% gross budget when not otherwise specified.
        return abs(self.net) if self.long_only else max(abs(self.net), 2.0)


@dataclass
class OptResult:
    weights: np.ndarray
    status: str  # "optimal" | "infeasible-relaxed"
    iterations: int
    binding: List[str] = field(default_factory=list)


# ----------------------------- projections -----------------------------
def _project_box_sum(
    v: np.ndarray, lo: np.ndarray, hi: np.ndarray, total: float, iters: int = 50
) -> np.ndarray:
    """Euclidean projection of ``v`` onto {lo <= w <= hi, sum(w) == total}.

    Classic bisection on a scalar shift tau: w_i = clip(v_i - tau, lo_i, hi_i),
    where sum(w) decreases monotonically in tau, so a root for sum == total is
    found by bisection.
    """
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    # Feasibility guard: if the box cannot reach the target sum, clamp to the
    # nearest reachable corner.
    if total <= lo.sum():
        return lo.copy()
    if total >= hi.sum():
        return hi.copy()
    tau_lo = float((v - hi).min()) - 1.0
    tau_hi = float((v - lo).max()) + 1.0
    tau = 0.5 * (tau_lo + tau_hi)
    for _ in range(iters):
        tau = 0.5 * (tau_lo + tau_hi)
        w = np.clip(v - tau, lo, hi)
        if w.sum() > total:
            tau_lo = tau
        else:
            tau_hi = tau
    return np.clip(v - tau, lo, hi)


def _project_halfspace_sum(v: np.ndarray, members: np.ndarray, cap: float) -> np.ndarray:
    """Project onto the halfspace sum(v[members]) <= cap (equal split of excess)."""
    s = float(v[members].sum())
    if s <= cap or not members.any():
        return v
    w = v.copy()
    w[members] -= (s - cap) / float(members.sum())
    return w


def _project_l1_ball(v: np.ndarray, radius: float) -> np.ndarray:
    """Euclidean projection onto the L1 ball {||w||_1 <= radius} (Duchi 2008)."""
    if radius <= 0:
        return np.zeros_like(v)
    a = np.abs(v)
    if a.sum() <= radius:
        return v.copy()
    u = np.sort(a)[::-1]
    css = np.cumsum(u) - radius
    rng = np.arange(1, u.size + 1)
    cond = u - css / rng > 0
    rho = int(np.nonzero(cond)[0][-1])
    theta = css[rho] / (rho + 1.0)
    return np.sign(v) * np.maximum(a - theta, 0.0)


def _project_feasible(
    v: np.ndarray,
    lo: np.ndarray,
    hi: np.ndarray,
    total: float,
    sector_members: Sequence[Tuple[np.ndarray, float]],
    gross: Optional[float],
    iters: int = 80,
    tol: float = 1e-9,
) -> np.ndarray:
    """Project ``v`` onto the full constraint intersection via Dykstra's algorithm.

    When only the box+budget set is active (no sector caps, no binding gross) the
    single combined projection is exact and returned immediately; otherwise the
    extra inequality sets (sector halfspaces, gross L1 ball) are folded in with
    Dykstra's alternating projections, which converges to the projection onto the
    intersection of the convex sets.
    """
    gross_binds = gross is not None and gross < float(np.abs(v).sum())
    if not sector_members and not gross_binds:
        return _project_box_sum(v, lo, hi, total)

    projs = [lambda x: _project_box_sum(x, lo, hi, total)]
    for members, cap in sector_members:
        projs.append(lambda x, m=members, c=cap: _project_halfspace_sum(x, m, c))
    if gross is not None:
        projs.append(lambda x, g=gross: _project_l1_ball(x, g))

    x = v.copy()
    corr = [np.zeros_like(v) for _ in projs]
    for _ in range(iters):
        x_old = x.copy()
        for i, proj in enumerate(projs):
            y = proj(x + corr[i])
            corr[i] = x + corr[i] - y
            x = y
        if float(np.max(np.abs(x - x_old))) < tol:
            break
    # Re-assert the budget exactly (Dykstra leaves it within tol).
    return _project_box_sum(x, lo, hi, total)


# ----------------------------- mean-variance core -----------------------------
def _sector_members(sectors: Optional[Sequence], cons: Constraints, n: int):
    if not sectors or not cons.sector_caps:
        return []
    out = []
    for sid, cap in cons.sector_caps.items():
        members = np.array([str(s) == str(sid) for s in sectors], dtype=bool)
        if members.any():
            out.append((members, float(cap)))
    return out


def _solve_utility(
    mu: np.ndarray,
    cov: np.ndarray,
    gamma: float,
    cons: Constraints,
    sectors: Optional[Sequence],
    current: Optional[np.ndarray],
    iters: int = 400,
    w_init: Optional[np.ndarray] = None,
    eig: Optional[float] = None,
) -> np.ndarray:
    """Maximize w'mu - (gamma/2) w'cov w - turnover_penalty * ||w - current||_1.

    Projected (sub)gradient ascent onto the constraint set. The step size is set
    from the largest eigenvalue of ``gamma*cov`` (Lipschitz constant of the
    smooth part) for stable convergence. ``w_init`` warm-starts the iteration
    (used to chain a gamma sweep cheaply) and ``eig`` caches the cov spectrum.
    """
    n = mu.size
    lo, hi = cons.bounds(n)
    members = _sector_members(sectors, cons, n)
    gross = cons.gross_limit()

    if eig is None:
        eig = float(np.linalg.eigvalsh(cov).max()) if n else 1.0
    L = max(gamma * eig, 1e-8)
    step = 1.0 / L
    to = float(cons.turnover_penalty)
    w0 = current if current is not None else None

    sc = None
    if cons.short_cost is not None:
        sc_arr = np.asarray(cons.short_cost, dtype=float)
        if sc_arr.shape == (n,):
            sc = np.maximum(sc_arr, 0.0)

    start = w_init if w_init is not None else np.full(n, cons.net / n)
    w = _project_feasible(start, lo, hi, cons.net, members, gross)
    for _ in range(iters):
        grad = mu - gamma * (cov @ w)
        if to > 0 and w0 is not None:
            grad = grad - to * np.sign(w - w0)
        if sc is not None:
            # Linear borrow-cost penalty on the short leg: cost = sum sc_i*max(-w_i,0),
            # whose subgradient pushes shorted names (w<0) back up toward zero so a
            # name is only shorted when its alpha clears its borrow fee.
            grad = grad + sc * (w < 0)
        w_new = _project_feasible(w + step * grad, lo, hi, cons.net, members, gross)
        if float(np.max(np.abs(w_new - w))) < 1e-9:
            w = w_new
            break
        w = w_new
    return w


def _binding(w: np.ndarray, cons: Constraints, sectors: Optional[Sequence]) -> List[str]:
    out: List[str] = []
    _, hi = cons.bounds(w.size)
    tol = 1e-4
    if np.any(np.abs(w) >= hi - tol):
        out.append(f"max position {cons.max_position*100:.0f}%")
    members = _sector_members(sectors, cons, w.size)
    for m, cap in members:
        if float(w[m].sum()) >= cap - tol:
            out.append("sector cap")
            break
    gross = cons.gross_limit()
    if float(np.abs(w).sum()) >= gross - tol and not cons.long_only:
        out.append(f"gross {gross*100:.0f}%")
    if cons.long_only and np.any(np.abs(w) <= tol):
        out.append("long-only floor")
    return out


def mean_variance(
    mu: np.ndarray,
    cov: np.ndarray,
    mode: str = "max_sharpe",
    cons: Optional[Constraints] = None,
    sectors: Optional[Sequence] = None,
    current: Optional[np.ndarray] = None,
    rf: float = 0.0,
    target_vol: float = 0.15,
) -> OptResult:
    """Mean-variance optimal weights for the requested ``mode``.

    - ``min_variance``: minimize w'cov w (ignores mu).
    - ``max_sharpe``: sweep the risk-aversion gamma on a log grid, solve the
      utility problem for each and keep the highest realized Sharpe (robust to
      the constraints, which preclude the closed-form tangency portfolio).
    - ``target_vol``: bisect gamma so the realized annualized vol matches
      ``target_vol`` as closely as the constraints allow.
    """
    mu = np.asarray(mu, dtype=float)
    cov = np.atleast_2d(np.asarray(cov, dtype=float))
    cons = cons or Constraints()
    n = mu.size
    if n == 0:
        raise ValueError("no assets to optimize")

    eig = float(np.linalg.eigvalsh(cov).max()) if n else 1.0

    if mode == "min_variance":
        w = _solve_utility(np.zeros(n), cov, 1.0, cons, sectors, current, eig=eig)
        return OptResult(w, "optimal", 0, _binding(w, cons, sectors))

    gammas = np.geomspace(0.5, 200.0, 14)

    if mode == "target_vol":
        # Vol decreases monotonically in gamma; bisect on the gamma grid.
        w = None
        lo_i, hi_i = 0, len(gammas) - 1
        for _ in range(14):
            mid = (lo_i + hi_i) // 2
            w = _solve_utility(mu, cov, float(gammas[mid]), cons, sectors, current,
                               w_init=w, eig=eig)
            vol = float(np.sqrt(max(w @ cov @ w, 0.0)))
            if vol > target_vol:
                lo_i = mid + 1  # need more risk aversion
            else:
                hi_i = mid
            if lo_i >= hi_i:
                break
        w = _solve_utility(mu, cov, float(gammas[min(lo_i, len(gammas) - 1)]), cons,
                           sectors, current, w_init=w, eig=eig)
        return OptResult(w, "optimal", 0, _binding(w, cons, sectors))

    # max_sharpe (default): pick the gamma with the best realized Sharpe. Sweep
    # gammas low->high, warm-starting each solve from the previous solution so
    # the constrained projection converges in a handful of iterations.
    best_w = None
    best_sharpe = -np.inf
    w = None
    for g in gammas:
        w = _solve_utility(mu, cov, float(g), cons, sectors, current, w_init=w, eig=eig)
        vol = float(np.sqrt(max(w @ cov @ w, 0.0)))
        if vol <= 1e-9:
            continue
        sharpe = (float(w @ mu) - rf) / vol
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_w = w.copy()
    if best_w is None:
        best_w = _solve_utility(mu, cov, 1.0, cons, sectors, current, eig=eig)
    return OptResult(best_w, "optimal", 0, _binding(best_w, cons, sectors))


# ----------------------------- Black-Litterman -----------------------------
def implied_risk_aversion(mkt_ann_return: float, mkt_ann_var: float, rf: float = 0.0) -> float:
    """delta = (E[r_mkt] - rf) / var(r_mkt), clamped to a sane [1, 10] range."""
    if mkt_ann_var <= 0:
        return 2.5
    delta = (mkt_ann_return - rf) / mkt_ann_var
    if not np.isfinite(delta) or delta <= 0:
        return 2.5
    return float(np.clip(delta, 1.0, 10.0))


def black_litterman(
    cov: np.ndarray,
    w_mkt: np.ndarray,
    view_returns: np.ndarray,
    delta: float = 2.5,
    tau: float = 0.05,
    view_confidence: float = 1.0,
    rf: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Posterior expected returns blending the market prior with absolute views.

    Uses the standard Black-Litterman formula with one absolute view per asset
    (P = I), where ``view_returns`` are the (signal/factor-implied) expected
    returns. The equilibrium prior is ``pi = delta * cov @ w_mkt``. Returns
    ``(mu_posterior, pi_prior)`` so callers can show how views shifted the prior.
    """
    cov = np.atleast_2d(np.asarray(cov, dtype=float))
    w_mkt = np.asarray(w_mkt, dtype=float)
    q = np.asarray(view_returns, dtype=float)
    n = cov.shape[0]

    pi = delta * (cov @ w_mkt)
    tau_cov = tau * cov
    tau_cov_inv = np.linalg.pinv(tau_cov)
    # Omega scales the view uncertainty; higher confidence -> tighter Omega.
    conf = max(1e-3, float(view_confidence))
    omega = np.diag(np.maximum(np.diag(tau_cov) / conf, 1e-10))
    omega_inv = np.linalg.pinv(omega)

    a = tau_cov_inv + omega_inv  # P = I
    b = tau_cov_inv @ pi + omega_inv @ q
    mu_post = np.linalg.solve(a, b) if n else q
    return mu_post, pi


# ----------------------------- risk parity -----------------------------
def risk_parity(cov: np.ndarray, iters: int = 500, tol: float = 1e-10) -> np.ndarray:
    """Long-only equal-risk-contribution weights via cyclical coordinate descent.

    Minimizes (1/2) w'cov w - (1/n) sum(ln w_i) over w > 0 (Spinu 2013); the
    solution is proportional to the ERC portfolio, where every holding
    contributes the same share of total risk. Weights are normalized to sum to 1.
    """
    cov = np.atleast_2d(np.asarray(cov, dtype=float))
    n = cov.shape[0]
    if n == 1:
        return np.ones(1)
    w = np.full(n, 1.0 / n)
    diag = np.diag(cov)
    for _ in range(iters):
        w_old = w.copy()
        for i in range(n):
            a = diag[i]
            b = float(cov[i] @ w) - a * w[i]  # contribution from j != i
            if a <= 0:
                continue
            # Solve a*w_i^2 + b*w_i - 1/n = 0 for the positive root.
            w[i] = (-b + np.sqrt(b * b + 4.0 * a / n)) / (2.0 * a)
        if float(np.max(np.abs(w - w_old))) < tol:
            break
    return w / w.sum()


# ----------------------------- hierarchical risk parity -----------------------------
def _corr_from_cov(cov: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.clip(np.diag(cov), 1e-16, None))
    corr = cov / np.outer(d, d)
    return np.clip(corr, -1.0, 1.0)


def _hrp_linkage_order(corr: np.ndarray) -> List[int]:
    """Single-linkage agglomerative clustering -> quasi-diagonal leaf order.

    Distance d_ij = sqrt((1 - corr_ij) / 2). Clusters are merged by nearest
    single-linkage distance; the recursive leaf order of the resulting tree is
    the quasi-diagonalization used by HRP.
    """
    n = corr.shape[0]
    if n <= 1:
        return list(range(n))
    dist = np.sqrt(np.clip((1.0 - corr) / 2.0, 0.0, None))
    # Active clusters: id -> list of leaf indices; pairwise single-linkage dist.
    clusters: Dict[int, List[int]] = {i: [i] for i in range(n)}
    cdist: Dict[Tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            cdist[(i, j)] = float(dist[i, j])
    next_id = n
    while len(clusters) > 1:
        # Find the closest pair of active clusters.
        ids = list(clusters.keys())
        best = None
        best_d = np.inf
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                a, b = ids[x], ids[y]
                key = (a, b) if a < b else (b, a)
                d = cdist.get(key, np.inf)
                if d < best_d:
                    best_d = d
                    best = (a, b)
        a, b = best
        merged = clusters[a] + clusters[b]
        # Single-linkage distance from the new cluster to every other cluster.
        for c in ids:
            if c in (a, b):
                continue
            da = cdist.get((a, c) if a < c else (c, a), np.inf)
            db = cdist.get((b, c) if b < c else (c, b), np.inf)
            cdist[(min(next_id, c), max(next_id, c))] = min(da, db)
        del clusters[a]
        del clusters[b]
        clusters[next_id] = merged
        next_id += 1
    return next(iter(clusters.values()))


def _cluster_var(cov: np.ndarray, items: List[int]) -> float:
    """Inverse-variance-weighted variance of a sub-cluster (HRP building block)."""
    sub = cov[np.ix_(items, items)]
    ivp = 1.0 / np.clip(np.diag(sub), 1e-16, None)
    ivp = ivp / ivp.sum()
    return float(ivp @ sub @ ivp)


def hrp(cov: np.ndarray) -> np.ndarray:
    """Hierarchical Risk Parity weights (Lopez de Prado 2016), long-only, sum 1.

    Quasi-diagonalize via single-linkage clustering, then recursively bisect the
    ordered list, splitting capital between the two halves in inverse proportion
    to each half's cluster variance.
    """
    cov = np.atleast_2d(np.asarray(cov, dtype=float))
    n = cov.shape[0]
    if n == 1:
        return np.ones(1)
    order = _hrp_linkage_order(_corr_from_cov(cov))
    w = np.ones(n)
    clusters = [order]
    while clusters:
        new_clusters = []
        for items in clusters:
            if len(items) <= 1:
                continue
            half = len(items) // 2
            left, right = items[:half], items[half:]
            var_l = _cluster_var(cov, left)
            var_r = _cluster_var(cov, right)
            alpha = 1.0 - var_l / (var_l + var_r) if (var_l + var_r) > 0 else 0.5
            for i in left:
                w[i] *= alpha
            for i in right:
                w[i] *= 1.0 - alpha
            new_clusters.extend([left, right])
        clusters = new_clusters
    return w / w.sum()


def apply_long_only_constraints(
    w: np.ndarray, cons: Constraints, sectors: Optional[Sequence] = None
) -> np.ndarray:
    """Clamp a long-only allocation (risk-parity / HRP) into the box + sector caps.

    Risk parity and HRP produce raw long-only weights summing to 1; this projects
    them onto {0 <= w <= max_position, sum == net, sector caps} so the same
    constraints layer applies to every construction method.
    """
    n = w.size
    lo, hi = cons.bounds(n)
    lo = np.maximum(lo, 0.0)  # these methods are long-only by construction
    members = _sector_members(sectors, cons, n)
    return _project_feasible(w * cons.net, lo, hi, cons.net, members, cons.gross_limit())


# ----------------------------- analytics -----------------------------
def portfolio_stats(
    w: np.ndarray, mu: np.ndarray, cov: np.ndarray, rf: float = 0.0
) -> Dict[str, float]:
    """Expected return / vol / Sharpe plus gross & net exposure for a weight set."""
    w = np.asarray(w, dtype=float)
    mu = np.asarray(mu, dtype=float)
    cov = np.atleast_2d(np.asarray(cov, dtype=float))
    exp_ret = float(w @ mu)
    var = float(w @ cov @ w)
    vol = float(np.sqrt(max(var, 0.0)))
    sharpe = (exp_ret - rf) / vol if vol > 1e-12 else 0.0
    return {
        "expReturn": exp_ret,
        "vol": vol,
        "sharpe": sharpe,
        "gross": float(np.abs(w).sum()),
        "net": float(w.sum()),
    }


def risk_contributions(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Percent of total portfolio risk contributed by each holding (sums to 100)."""
    w = np.asarray(w, dtype=float)
    cov = np.atleast_2d(np.asarray(cov, dtype=float))
    var = float(w @ cov @ w)
    if var <= 1e-16:
        return np.zeros_like(w)
    mctr = (cov @ w) / np.sqrt(var)
    rc = w * mctr
    total = rc.sum()
    return rc / total * 100.0 if total != 0 else np.zeros_like(w)
