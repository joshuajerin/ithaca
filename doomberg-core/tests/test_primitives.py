"""Strategy primitives: shape, warm-up NaNs, no-lookahead, and rank selection."""
from __future__ import annotations

import numpy as np

from doomberg_core.registry import evaluate_primitive


def _closes(n=60, k=3):
    # deterministic increasing-ish panel
    base = np.linspace(100, 130, n)
    return np.column_stack([base * (1 + 0.001 * j) for j in range(k)])


def test_momentum_warmup_and_shape():
    closes = _closes(60, 3)
    scores, selected = evaluate_primitive("momentum", closes, {"lookback": 20})
    assert scores.shape == (60, 3) and selected.shape == (60, 3)
    # warm-up region undefined / not selected
    assert np.all(np.isnan(scores[:20]))
    assert not selected[:20].any()


def test_no_lookahead_momentum():
    """A primitive's value at bar t must not change when FUTURE bars are perturbed."""
    closes = _closes(60, 1)
    s1, _ = evaluate_primitive("momentum", closes, {"lookback": 10})
    perturbed = closes.copy()
    perturbed[40:] *= 1.5  # change only the future
    s2, _ = evaluate_primitive("momentum", perturbed, {"lookback": 10})
    np.testing.assert_allclose(s1[:40], s2[:40], equal_nan=True)


def test_rank_returns_selects_top_n():
    rng = np.random.default_rng(0)
    closes = np.cumprod(1 + rng.normal(0, 0.01, size=(120, 5)), axis=0) * 100
    scores, selected = evaluate_primitive("rank_returns", closes, {"lookback": 30, "top": 2})
    last = selected[-1]
    assert last.sum() == 2
    # the two selected names must be the two highest scores at that bar
    chosen = np.where(last)[0]
    not_chosen = np.where(~last)[0]
    assert scores[-1, chosen].min() >= scores[-1, not_chosen].max()
