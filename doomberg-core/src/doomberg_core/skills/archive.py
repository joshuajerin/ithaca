"""The ``ArchiveGateway`` read seam.

Defined locally (duck-typed Protocol) so the skills can be built + tested in parallel with
legacy concrete implementations. Any object that structurally satisfies these method
signatures — including the in-memory ``FakeArchive`` in the tests — can back a
:class:`~doomberg_core.skills.SkillSet`.

Rows are plain JSON-shaped dicts whose keys match the canonical ``archive.*`` columns in
``docs/plans/doomberg-v2/DATA-LAYER-INTERFACES.md``. Skills NEVER issue raw SQL; they read only
through these methods.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # numpy is a hard dep at runtime; the annotation stays cheap to import.
    import numpy as np


@runtime_checkable
class ArchiveGateway(Protocol):
    # ---- prices ----
    def ohlcv(self, symbol: str, start: str | None = None, end: str | None = None) -> list[dict]: ...
    def ohlcv_panel(
        self, symbols: list[str], start: str | None = None, end: str | None = None
    ) -> tuple[list[str], "np.ndarray", list[str]]:  # dates, closes[T,N], symbols
        ...

    # ---- reference ----
    def universe(self, tracked_only: bool = True) -> list[dict]: ...
    def sectors(self) -> list[dict]: ...

    # ---- fundamentals ----
    def fundamentals(self, symbols: list[str]) -> list[dict]: ...
    def fundamentals_pit(self, symbol: str, as_of: str) -> dict | None: ...

    # ---- analyst / news / sentiment ----
    def analyst_ratings(self, symbols: list[str]) -> list[dict]: ...
    def news(self, ticker: str | None = None, sector: str | None = None, limit: int = 50) -> list[dict]: ...
    def sentiment(self, scope_type: str, scope: str) -> dict | None: ...

    # ---- ownership / flows ----
    def congress_trades(
        self, ticker: str | None = None, member: str | None = None, limit: int = 100
    ) -> list[dict]: ...
    def insider_transactions(self, symbol: str, limit: int = 100) -> list[dict]: ...
    def inst_holdings(
        self, ticker: str | None = None, cik: str | None = None, period: str | None = None
    ) -> list[dict]: ...
    def inst_filings(self, cik: str | None = None, period: str | None = None) -> list[dict]: ...
    def etf_holdings(self, etf: str) -> list[dict]: ...
    def etf_exposure(self, symbol: str) -> list[dict]: ...

    # ---- macro ----
    def macro(self) -> dict: ...


__all__ = ["ArchiveGateway"]
