"""doomberg_archive -- the v1 market-data archive datastore + loader + read gateway.

The v1 archive (240,220 rows across 15 market-data tables) is READ-ONLY reference data
loaded into Postgres schema ``archive``. Skills read it ONLY through
:class:`~doomberg_archive.gateway.ArchiveGateway`.
"""
from __future__ import annotations

from .gateway import ArchiveGateway, PgArchiveGateway
from .loader import (
    SCHEMA,
    TABLE_COLUMNS,
    TABLES,
    create_table_sql,
    group_records,
    iter_records,
    load_archive,
    row_to_tuple,
)

__all__ = [
    "ArchiveGateway",
    "PgArchiveGateway",
    "load_archive",
    "iter_records",
    "group_records",
    "row_to_tuple",
    "create_table_sql",
    "TABLE_COLUMNS",
    "TABLES",
    "SCHEMA",
]
