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

from doomberg_control.money import make_applier
from doomberg_core import Core
from doomberg_platform import Platform
from doomberg_runtime import AlwaysOpen, BacktestWorker, PaperScheduler, RegularHoursCalendar


def main() -> int:
    db = os.environ.get("DOOMBERG_DB", ":memory:")
    if db == ":memory:":
        print("WARNING: DOOMBERG_DB=:memory: — workers won't share state with the gateways.\n"
              "         Set DOOMBERG_DB to a file path (e.g. ./doomberg.db).")
    platform = Platform(db)
    core = Core()  # live data gateway (free sources); offline cores are injected in tests/demos

    backtest_interval = float(os.environ.get("DOOMBERG_BACKTEST_INTERVAL_S", "2"))
    paper_interval = float(os.environ.get("DOOMBERG_PAPER_INTERVAL_S", "60"))
    # Honor market hours only if asked; daily-close paper + the staleness gate default to always-on.
    calendar = RegularHoursCalendar() if os.environ.get("DOOMBERG_MARKET_HOURS") == "1" else AlwaysOpen()

    worker = BacktestWorker(platform, core)
    scheduler = PaperScheduler(platform, core, make_applier(platform), calendar=calendar)

    stop = threading.Event()
    threads = [
        threading.Thread(target=worker.run_forever, kwargs={"interval_s": backtest_interval, "stop": stop},
                         name="backtest-worker", daemon=True),
        threading.Thread(target=scheduler.run_forever, kwargs={"interval_s": paper_interval, "stop": stop},
                         name="paper-scheduler", daemon=True),
    ]

    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    print(f"doomberg conductor up — db={db}, backtest every {backtest_interval}s, "
          f"paper every {paper_interval}s, calendar={type(calendar).__name__}")
    for t in threads:
        t.start()
    stop.wait()
    print("\nstopping…")
    for t in threads:
        t.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
