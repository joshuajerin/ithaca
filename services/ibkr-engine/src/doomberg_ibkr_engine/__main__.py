from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("DOOMBERG_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("DOOMBERG_IBKR_ENGINE_PORT", "8090"))
    uvicorn.run("doomberg_ibkr_engine.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
