from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("ITHACA_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("ITHACA_IBKR_ENGINE_PORT", "8090"))
    uvicorn.run("ithaca_ibkr_engine.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
