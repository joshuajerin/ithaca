#!/usr/bin/env python
"""The deploy-layer conductor process — run the backtest worker + paper scheduler locally.

This is the loop nothing drove before: the control plane enqueues runs and gates promotions,
and THIS process pulls the backtest queue and ticks live paper deployments on a cadence. In
production it is a DO worker pod (or two); locally it is one process over the shared
``DOOMBERG_DB`` so a created run actually executes without a manual call.

    DOOMBERG_DB=./doomberg.db uv run python scripts/run_workers.py

Both loops run in daemon threads; Ctrl-C stops them cleanly. The paper scheduler uses the
control plane's single-writer ``apply_paper_delta`` so the book is only ever written there.
"""
from __future__ import annotations

import os
import signal
import threading
from contextlib import suppress

from doomberg_control.money import make_applier
from doomberg_core import Core
from doomberg_platform import Platform
from doomberg_runtime import (
    AdaptiveDashboardWorker,
    AlwaysOpen,
    BacktestWorker,
    NotificationDispatcher,
    PaperScheduler,
    RegularHoursCalendar,
    TriggerJobWorker,
)
from doomberg_runtime.leader import acquire_loop_lease, process_owner, release_loop_lease


def main() -> int:
    db = os.environ.get("DOOMBERG_DB", ":memory:")
    if db == ":memory:":
        print("WARNING: DOOMBERG_DB=:memory: — workers won't share state with the gateways.\n"
              "         Set DOOMBERG_DB to a file path (e.g. ./doomberg.db).")
    platform = Platform(db)
    core = Core()  # live data gateway (free sources); offline cores are injected in tests/demos

    backtest_interval = float(os.environ.get("DOOMBERG_BACKTEST_INTERVAL_S", "2"))
    trigger_job_interval = float(os.environ.get("DOOMBERG_TRIGGER_JOB_INTERVAL_S", "2"))
    notification_interval = float(os.environ.get("DOOMBERG_NOTIFICATION_INTERVAL_S", "2"))
    paper_interval = float(os.environ.get("DOOMBERG_PAPER_INTERVAL_S", "60"))
    adaptive_dashboard_interval = float(os.environ.get("DOOMBERG_ADAPTIVE_DASHBOARD_INTERVAL_S", "60"))
    paper_lease_ttl = float(os.environ.get(
        "DOOMBERG_PAPER_LEASE_TTL_S",
        str(max(180.0, paper_interval * 3.0)),
    ))
    # Honor market hours only if asked; daily-close paper + the staleness gate default to always-on.
    calendar = RegularHoursCalendar() if os.environ.get("DOOMBERG_MARKET_HOURS") == "1" else AlwaysOpen()

    worker = BacktestWorker(platform, core)
    trigger_worker = TriggerJobWorker(platform, core)
    notification_dispatcher = NotificationDispatcher(platform)
    adaptive_dashboard_worker = AdaptiveDashboardWorker(platform)
    scheduler = PaperScheduler(platform, core, make_applier(platform), calendar=calendar)
    paper_owner_id = process_owner("paper-scheduler")

    def run_paper_scheduler() -> None:
        while not stop.is_set():
            if acquire_loop_lease(
                platform,
                lease_name="paper-scheduler",
                owner_id=paper_owner_id,
                ttl_seconds=paper_lease_ttl,
                role="paper-scheduler",
            ):
                scheduler.tick_once()
            stop.wait(paper_interval)
        with suppress(Exception):
            release_loop_lease(platform, lease_name="paper-scheduler", owner_id=paper_owner_id)

    def run_adaptive_dashboard_worker() -> None:
        while not stop.is_set():
            result = adaptive_dashboard_worker.poll_once()
            if result.get("status") == "ran" or result.get("failed"):
                print(f"adaptive dashboard recompute: {result}")
            stop.wait(adaptive_dashboard_interval)

    stop = threading.Event()
    threads = [
        threading.Thread(target=trigger_worker.run_forever, kwargs={"interval_s": trigger_job_interval, "stop": stop},
                         name="trigger-job-worker", daemon=True),
        threading.Thread(
            target=notification_dispatcher.run_forever,
            kwargs={"interval_s": notification_interval, "stop": stop},
            name="notification-dispatcher",
            daemon=True,
        ),
        threading.Thread(target=run_paper_scheduler, name="paper-scheduler", daemon=True),
        threading.Thread(
            target=run_adaptive_dashboard_worker,
            name="adaptive-dashboard-worker",
            daemon=True,
        ),
    ]
    if os.environ.get("DOOMBERG_ENABLE_BACKTEST_LOOP", "1").strip().lower() in {"1", "true", "yes"}:
        threads.insert(
            0,
            threading.Thread(
                target=worker.run_forever,
                kwargs={"interval_s": backtest_interval, "stop": stop},
                name="backtest-worker",
                daemon=True,
            ),
        )

    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    backtest_mode = "embedded" if any(t.name == "backtest-worker" for t in threads) else "dedicated"
    print(f"doomberg conductor up — db={db}, backtest={backtest_mode} every {backtest_interval}s, "
          f"trigger jobs every {trigger_job_interval}s, paper every {paper_interval}s, "
          f"notifications every {notification_interval}s, "
          f"adaptive dashboard every {adaptive_dashboard_interval}s, "
          f"paper lease ttl={paper_lease_ttl}s owner={paper_owner_id}, "
          f"calendar={type(calendar).__name__}")
    for t in threads:
        t.start()
    stop.wait()
    print("\nstopping…")
    for t in threads:
        t.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
