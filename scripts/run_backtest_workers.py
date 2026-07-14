#!/usr/bin/env python
"""Dedicated backtest worker process for Kubernetes compute pods."""

from __future__ import annotations

import os
import signal
import threading

from ithaca_core import Core
from ithaca_platform import Platform
from ithaca_runtime import BacktestWorker, object_storage_configured


def main() -> int:
    db = os.environ.get("ITHACA_DB", ":memory:")
    if db == ":memory:":
        raise RuntimeError("dedicated backtest workers require a shared ITHACA_DB")
    if os.environ.get("ITHACA_ENV", "").lower() in {"prod", "production"}:
        if not object_storage_configured():
            raise RuntimeError("production backtest workers require durable artifact storage")

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    platform = Platform(db)
    worker = BacktestWorker(
        platform,
        Core(),
        batch=int(os.environ.get("ITHACA_BACKTEST_BATCH", "4")),
    )
    interval = float(os.environ.get("ITHACA_BACKTEST_INTERVAL_S", "2"))
    print(
        f"dedicated backtest worker up — id={worker.worker_id}, interval={interval}s, "
        f"batch={worker.batch}, durable_artifacts={object_storage_configured()}"
    )
    worker.run_forever(interval_s=interval, stop=stop)
    print("backtest worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
