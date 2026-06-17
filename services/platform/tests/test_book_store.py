"""BookStore: tenant-scoped paper book with an optimistic version guard."""

from __future__ import annotations

import uuid

import pytest

from doomberg_platform import BookConflict, BookNotFound, BookStore


@pytest.fixture()
def books(db) -> BookStore:
    return BookStore(db)


def test_get_absent_is_none(books):
    assert books.get(str(uuid.uuid4()), str(uuid.uuid4())) is None


def test_ensure_creates_flat_all_cash_book(books):
    t, r = str(uuid.uuid4()), str(uuid.uuid4())
    book = books.ensure(t, r, capital=100_000.0)
    assert book["capital"] == 100_000.0
    assert book["weights"] == {}
    assert book["cash"] == 100_000.0  # all cash when flat
    assert book["version"] == 0


def test_ensure_is_idempotent(books):
    t, r = str(uuid.uuid4()), str(uuid.uuid4())
    first = books.ensure(t, r, capital=50_000.0)
    second = books.ensure(t, r, capital=999.0)  # capital arg ignored once it exists
    assert second["capital"] == first["capital"] == 50_000.0
    assert second["version"] == 0


def test_apply_sets_weights_bumps_version_and_derives_cash(books):
    t, r = str(uuid.uuid4()), str(uuid.uuid4())
    books.ensure(t, r, capital=100_000.0)
    out = books.apply(t, r, target_weights={"AAA": 0.6, "BBB": 0.4},
                      marks={"AAA": 10.0, "BBB": 20.0}, expect=0)
    assert out["weights"] == {"AAA": 0.6, "BBB": 0.4}
    assert out["gross"] == 1.0
    assert out["cash"] == 0.0
    assert out["marks"] == {"AAA": 10.0, "BBB": 20.0}
    assert out["version"] == 1


def test_apply_drops_zero_weights(books):
    t, r = str(uuid.uuid4()), str(uuid.uuid4())
    books.ensure(t, r)
    out = books.apply(t, r, target_weights={"AAA": 0.5, "BBB": 0.0}, expect=0)
    assert out["weights"] == {"AAA": 0.5}


def test_apply_optimistic_conflict(books):
    t, r = str(uuid.uuid4()), str(uuid.uuid4())
    books.ensure(t, r)
    books.apply(t, r, target_weights={"AAA": 1.0}, expect=0)  # -> version 1
    with pytest.raises(BookConflict):
        books.apply(t, r, target_weights={"BBB": 1.0}, expect=0)  # stale expect


def test_apply_without_book_raises(books):
    with pytest.raises(BookNotFound):
        books.apply(str(uuid.uuid4()), str(uuid.uuid4()), target_weights={"AAA": 1.0})


def test_tenant_isolation(books):
    t, other, r = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    books.ensure(t, r)
    assert books.get(other, r) is None
