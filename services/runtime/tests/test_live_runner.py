"""Tests for run_paper_tick: proposes a delta, NEVER writes the book, staleness denial."""

from __future__ import annotations

import datetime as dt

import pytest

from ithaca_runtime import run_paper_tick

from runtime_helpers import seed_queued_run


def _promote_to_live(platform, tenant_id, spec):
    """Create a paper run and advance it to a live deployment state."""
    run_id = seed_queued_run(platform, tenant_id, spec, kind="paper")
    platform.runs.transition(tenant_id, run_id, "running", expect=1)
    platform.runs.transition(tenant_id, run_id, "promoted", expect=2)
    platform.runs.transition(tenant_id, run_id, "live", expect=3)
    return run_id


def test_paper_tick_proposes_delta_and_never_writes_book(platform, tenant_id, spec, core):
    run_id = _promote_to_live(platform, tenant_id, spec)
    before = dict(platform.runs.get(tenant_id, run_id))

    proposal = run_paper_tick(tenant_id, run_id, platform=platform, core=core,
                              book={"capital": 100_000.0, "weights": {}})

    assert proposal["action"] == "propose"
    assert proposal["deltas"]              # momentum on an uptrending universe selects names
    assert proposal["targetWeights"]
    # The worker must NOT mutate the run row / book (control plane is the only writer).
    after = platform.runs.get(tenant_id, run_id)
    assert after == before
    assert after["result"] is None
    # mark + fill (proposal) events emitted; no transition written by the worker.
    types = platform.trace.types(run_id)
    assert "mark" in types and "fill" in types
    assert "run_transition" not in types
    fill = [e for e in platform.trace.events_by_run[run_id] if e["type"] == "fill"][0]
    assert fill["data"]["proposed"] is True


def test_paper_tick_delta_accounts_for_current_book(platform, tenant_id, spec, core):
    """Delta = target - current; an already-held name nets to a smaller delta."""
    run_id = _promote_to_live(platform, tenant_id, spec)

    flat = run_paper_tick(tenant_id, run_id, platform=platform, core=core,
                          book={"weights": {}})
    target = flat["targetWeights"]
    sym = next(iter(target))

    # Start already holding exactly the target weight in one name -> its delta is ~0.
    held = run_paper_tick(tenant_id, run_id, platform=platform, core=core,
                          book={"weights": {sym: target[sym]}})
    assert sym not in held["deltas"]  # netted out (no change needed for that name)


def test_paper_tick_stale_data_denial(platform, tenant_id, spec, core):
    """If the freshest mark is older than max_staleness_s, skip-and-alert (denial), no fill."""
    run_id = _promote_to_live(platform, tenant_id, spec)
    # Force 'now' far into the future so the (real-dated) panel looks stale.
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=400)

    proposal = run_paper_tick(tenant_id, run_id, platform=platform, core=core,
                              now=future, max_staleness_s=3600, book={"weights": {}})

    assert proposal["action"] == "skip"
    assert proposal["reason"] == "stale_data"
    assert proposal["deltas"] == {}
    types = platform.trace.types(run_id)
    assert "denial" in types
    assert "fill" not in types
    denial = [e for e in platform.trace.events_by_run[run_id] if e["type"] == "denial"][0]
    assert denial["data"]["reason"] == "stale_data"


def test_paper_tick_no_marks_denial(platform, tenant_id, spec):
    """No priced symbols -> denial + skip, never a fill."""
    class _EmptyGatewayCore:
        class _GW:
            def price_panel(self, symbols, range_="1y", as_of=None):
                import numpy as np
                from ithaca_core.gateway.data_gateway import PricePanel
                return PricePanel([], np.zeros((0, 0)), [], list(symbols)), {"provenance": {}}
        gateway = _GW()

    run_id = _promote_to_live(platform, tenant_id, spec)
    proposal = run_paper_tick(tenant_id, run_id, platform=platform, core=_EmptyGatewayCore())

    assert proposal["action"] == "skip"
    assert proposal["reason"] == "no_marks"
    assert "denial" in platform.trace.types(run_id)
    assert "fill" not in platform.trace.types(run_id)


def test_paper_tick_missing_run_raises(platform, tenant_id, core):
    import uuid
    with pytest.raises(KeyError):
        run_paper_tick(tenant_id, str(uuid.uuid4()), platform=platform, core=core)
