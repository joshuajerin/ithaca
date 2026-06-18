"""Test fixtures for the archive loader + gateway.

If a Postgres DSN is available (either ``DOOMBERG_ARCHIVE_URL`` is already set, or a
docker daemon is reachable so we can boot an ephemeral container), this builds a
``live_archive`` fixture: a small SAMPLE subset of ``data/v1_archive.json`` is loaded
into a fresh ``archive`` schema and a :class:`PgArchiveGateway` is handed back.

If neither is available, the live fixture skips and only the DB-free unit tests run.
"""
from __future__ import annotations

import itertools
import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ARCHIVE_JSON = _REPO_ROOT / "data" / "v1_archive.json"

# How many rows per table to pull into the sampled fixture. Large enough to exercise
# multi-symbol panels and point-in-time picks, small enough to load in well under a
# second.
SAMPLE_PER_TABLE = 400


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, timeout=15
        ).returncode == 0
    except Exception:
        return False


def _sample_archive(path: Path, per_table: int) -> Path:
    """Write a sampled subset JSON next to a tmp dir; return its path.

    Streams the big file with the loader's incremental reader and keeps the first
    ``per_table`` rows of each table -- EXCEPT ``ohlcv``, which is sampled
    symbol-first (all rows for a small set of symbols) so the panel actually overlaps
    on common trading days. This is required for the backtest-seam test to exercise
    rather than skip.
    """
    from doomberg_archive.loader import TABLES, iter_records

    ohlcv_symbol_cap = 6           # keep this many symbols' full OHLCV histories
    keep: dict[str, list[dict]] = {t: [] for t in TABLES}
    counts = {t: 0 for t in TABLES}
    ohlcv_symbols: set[str] = set()
    targets = set(TABLES)

    def _done() -> bool:
        for t in targets:
            if t == "ohlcv":
                if len(ohlcv_symbols) < ohlcv_symbol_cap:
                    return False
            elif counts[t] < per_table:
                return False
        return True

    for rec in iter_records(path):
        tbl = rec.get("tbl")
        if tbl not in targets:
            continue
        if tbl == "ohlcv":
            sym = (rec.get("row") or {}).get("symbol")
            if sym in ohlcv_symbols:
                keep[tbl].append(rec)
            elif len(ohlcv_symbols) < ohlcv_symbol_cap:
                ohlcv_symbols.add(sym)
                keep[tbl].append(rec)
            continue
        if counts[tbl] < per_table:
            keep[tbl].append(rec)
            counts[tbl] += 1
        if _done():
            break
    out_records = list(itertools.chain.from_iterable(keep[t] for t in TABLES))
    tmp = Path(os.environ.get("PYTEST_SAMPLE_DIR", "/tmp")) / f"v1_archive_sample_{uuid.uuid4().hex}.json"
    tmp.write_text(json.dumps(out_records))
    return tmp


def _wait_for_pg(dsn: str, timeout: float = 60.0) -> None:
    import psycopg

    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.0)
    raise RuntimeError(f"Postgres not ready within {timeout}s: {last}")


@pytest.fixture(scope="session")
def archive_dsn():
    """A reachable Postgres DSN with the SAMPLE archive loaded, or skip.

    Order of preference:
      1. ``DOOMBERG_ARCHIVE_URL`` already set -> use it as-is (assumed pre-loaded
         or that the test session may load into it).
      2. docker available -> boot an ephemeral postgres:16, load the sample, tear down.
      3. otherwise skip (unit tests still run).
    """
    pre = os.environ.get("DOOMBERG_ARCHIVE_URL")
    if pre:
        yield pre
        return

    if not _ARCHIVE_JSON.exists():
        pytest.skip(f"no archive JSON at {_ARCHIVE_JSON} and DOOMBERG_ARCHIVE_URL unset")
    if not _docker_available():
        pytest.skip("docker unavailable and DOOMBERG_ARCHIVE_URL unset; running unit tests only")

    port = _free_port()
    name = f"doomberg-archive-test-{uuid.uuid4().hex[:8]}"
    proc = subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", name,
            "-p", f"{port}:5432",
            "-e", "POSTGRES_PASSWORD=pw",
            "-e", "POSTGRES_DB=archive_test",
            "postgres:16",
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        pytest.skip(f"could not start postgres container: {proc.stderr.strip()}")

    dsn = f"postgresql://postgres:pw@127.0.0.1:{port}/archive_test"
    try:
        _wait_for_pg(dsn)
        yield dsn
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


@pytest.fixture(scope="session")
def loaded_counts(archive_dsn):
    """Load the SAMPLE subset into ``archive_dsn``; return ``{table: rows}``."""
    from doomberg_archive.loader import load_archive

    sample_path = _sample_archive(_ARCHIVE_JSON, SAMPLE_PER_TABLE)
    try:
        counts = load_archive(archive_dsn, sample_path, create_schema=True, truncate=True)
    finally:
        sample_path.unlink(missing_ok=True)
    return counts


@pytest.fixture
def gateway(archive_dsn, loaded_counts):
    """A :class:`PgArchiveGateway` over the loaded sample."""
    from doomberg_archive.gateway import PgArchiveGateway

    gw = PgArchiveGateway(archive_dsn)
    yield gw
    gw.close()
