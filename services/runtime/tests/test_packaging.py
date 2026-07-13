"""Production dependency checks for the worker runtime."""

from importlib.util import find_spec


def test_worker_runtime_includes_databento_sdk() -> None:
    """The production worker must be able to use the configured Databento source."""

    assert find_spec("databento") is not None
