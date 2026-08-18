"""Desktop backend entry — used by the macOS Electron app.

A thin launcher that imports the FastAPI ``app`` object directly (instead of
the string form ``"backend.main:app"``) so PyInstaller can statically trace
every route and its dependencies, then serves it on 127.0.0.1 with uvicorn.

The Electron shell spawns this binary with ``--port N`` (an auto-picked free
port) and polls ``/api/status`` until the server responds, then points its
BrowserWindow at ``http://127.0.0.1:PORT``.

The same frozen binary also acts as the CodeBuddy PreToolUse hook runner when
invoked with ``--hooks-forward``: it reads the hook JSON from stdin, forwards it
to the running webserver's ``/hooks/pre-tool-use`` handler and prints the
response (fail-open).  Because an onedir PyInstaller bundle has no standalone
python, ``client_config._hooks_command_codebuddy()`` points the hook at this
binary (``sys.executable --hooks-forward``) in frozen builds.  The
``from backend import hooks_forward`` import below lets PyInstaller trace the
forwarder into the PYZ bundle so it is importable in-process.
"""

from __future__ import annotations

import argparse
import os
import sys

import uvicorn

from backend import hooks_forward
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
    parser.add_argument(
        "--hooks-forward", action="store_true",
        help="run as the CodeBuddy PreToolUse hook forwarder (stdin→hook→stdout)",
    )
    args = parser.parse_args(argv)

    if args.hooks_forward:
        # PreToolUse hook mode: read stdin JSON, forward to the running
        # webserver hook endpoint, print the response (fail-open).
        # Nothing else is initialized — the hook should be fast and side-effect
        # free, and must never block the user when the backend is unreachable.
        return hooks_forward.main()

    os.environ["MYKNOWLEDGE_ROOT"] = str(resolve_root(args.root))

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", timeout_graceful_shutdown=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
