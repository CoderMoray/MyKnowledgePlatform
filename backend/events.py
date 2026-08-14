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


def broadcast(kb_root: Path, event_type: str = "write") -> None:
    """Record a KB event.

    Writes an incrementing millisecond timestamp and the event *type* to
    ``.events/version.json``.  Both MCP and REST share this file — the SSE
    endpoint polls it.

    ``event_type`` is ``"write"`` by default (backward-compatible: callers
    that don't pass a type keep the old behaviour).  Other values (e.g.
    ``"diagnose"``) let the SSE endpoint distinguish event kinds so the
    frontend can respond only to relevant ones.
    """
    vp = _version_path(kb_root)
    vp.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": int(time.time() * 1000), "type": event_type}
    vp.write_text(json.dumps(data), encoding="utf-8")


def poll_version(kb_root: Path) -> int:
    """Return the current version number (0 if no events yet)."""
    return poll_event(kb_root).get("version", 0)


def poll_event(kb_root: Path) -> dict:
    """Return the last broadcast event ``{"version", "type"}`` (empty if none).

    Never raises on a missing/corrupt file — returns ``{}``.
    """
    vp = _version_path(kb_root)
    if not vp.exists():
        return {}
    try:
        data = json.loads(vp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data
