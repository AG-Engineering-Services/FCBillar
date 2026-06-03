"""CLI entry point: `fcb-opens-api [--host] [--port] [--reload]`.

Starts uvicorn with the FastAPI app. This is a thin wrapper so that
users don't have to remember the module path.
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fcb-opens-api",
        description="Run the fcb-opens HTTP API server.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="enable auto-reload for dev")
    args = parser.parse_args(argv)

    import uvicorn  # imported lazily so `fcb-opens --help` stays fast

    uvicorn.run(
        "fcb_opens.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
