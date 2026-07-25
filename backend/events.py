"""Event broadcasting — notifies SSE subscribers of KB changes.

Architecture (local → cloud):
  - Local:  file-based version counter (``.events/version.json``)
  - Cloud:  swap ``_broadcast`` / ``_poll_version`` for Redis pub/sub or
            database NOTIFY; the SSE endpoint stays unchanged.

Usage::

    from backend.events import broadcast
    broadcast(kb_root)   # after every write
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def _version_path(kb_root: Path) -> Path:
    return kb_root / ".events" / "version.json"


def broadcast(kb_root: Path) -> None:
    """Record a write event.

    Writes an incrementing millisecond timestamp to ``.events/version.json``.
    Both MCP and REST share this file — the SSE endpoint polls it.
    """
    vp = _version_path(kb_root)
    vp.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": int(time.time() * 1000)}
    vp.write_text(json.dumps(data), encoding="utf-8")


def poll_version(kb_root: Path) -> int:
    """Return the current version number (0 if no events yet)."""
    vp = _version_path(kb_root)
    if not vp.exists():
        return 0
    try:
        return json.loads(vp.read_text(encoding="utf-8")).get("version", 0)
    except (json.JSONDecodeError, OSError):
        return 0
