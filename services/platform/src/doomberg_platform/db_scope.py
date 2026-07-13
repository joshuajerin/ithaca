"""Database access-scope decorators used by every platform store.

Postgres row-level security reads the scope set by :class:`PostgresDb`. SQLite
keeps these context managers as no-ops, so the same stores retain their local
development behavior.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any, TypeVar

_Store = TypeVar("_Store", bound=type[Any])


def _wrap_tenant(method: Callable[..., Any]) -> Callable[..., Any]:
    signature = inspect.signature(method)

    @wraps(method)
    def scoped(self: Any, *args: Any, **kwargs: Any) -> Any:
        bound = signature.bind(self, *args, **kwargs)
        tenant_id = str(bound.arguments["tenant_id"])
        with self._db.tenant_scope(tenant_id):
            return method(self, *args, **kwargs)

    return scoped


def _wrap_system(method: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(method)
    def scoped(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self._db.system_scope():
            return method(self, *args, **kwargs)

    return scoped


def tenant_scoped_store(
    *, system_methods: Iterable[str] = (), skip_methods: Iterable[str] = ()
) -> Callable[[_Store], _Store]:
    """Scope methods with a ``tenant_id`` argument and named system methods."""

    system = frozenset(system_methods)
    skipped = frozenset(skip_methods)

    def decorate(cls: _Store) -> _Store:
        for name, member in tuple(vars(cls).items()):
            if name == "__init__" or name in skipped or not inspect.isfunction(member):
                continue
            if name in system:
                setattr(cls, name, _wrap_system(member))
            elif "tenant_id" in inspect.signature(member).parameters:
                setattr(cls, name, _wrap_tenant(member))
        return cls

    return decorate


def system_scoped_store(cls: _Store) -> _Store:
    """Mark every method on a trusted infrastructure/authentication store."""

    for name, member in tuple(vars(cls).items()):
        if name != "__init__" and inspect.isfunction(member):
            setattr(cls, name, _wrap_system(member))
    return cls


def event_tenant_scoped(method: Callable[..., Any]) -> Callable[..., Any]:
    """Scope a trace-style method whose event mapping carries ``tenant_id``."""

    @wraps(method)
    def scoped(self: Any, event: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        tenant_id = str(event.get("tenant_id") or "")
        with self._db.tenant_scope(tenant_id):
            return method(self, event, *args, **kwargs)

    return scoped
