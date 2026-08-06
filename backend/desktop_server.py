"""Desktop backend entry — used by the macOS Electron app.

A thin launcher that imports the FastAPI ``app`` object directly (instead of
the string form ``"backend.main:app"``) so PyInstaller can statically trace
every route and its dependencies, then serves it on 127.0.0.1 with uvicorn.

The Electron shell spawns this binary with ``--port N`` (an auto-picked free
port) and polls ``/api/status`` until the server responds, then points its
BrowserWindow at ``http://127.0.0.1:PORT``.
"""

from __future__ import annotations

import argparse
import os
import sys

import uvicorn

from backend.config import resolve_root
from backend.main import app  # noqa: F401 — importing registers all routes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="myknowledge-desktop-backend")
    parser.add_argument(
        "--port", type=int, default=8080,
        help="listen port (default 8080)",
    )
    parser.add_argument(
        "--root", default=None,
        help="knowledge base root (default: ~/.myknowledge, or MYKNOWLEDGE_ROOT)",
    )
    args = parser.parse_args(argv)

    os.environ["MYKNOWLEDGE_ROOT"] = str(resolve_root(args.root))

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
