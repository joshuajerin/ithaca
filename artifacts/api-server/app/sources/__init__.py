"""Free, key-less market-data source adapters.

Each adapter is isolated behind a small function that normalizes a raw response
into the project's DB schema shape and raises on failure so the worker can log
and continue without taking down the rest of the ingestion loop.
"""
