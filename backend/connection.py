"""In-process MCP connection tracking for AI-client platforms.

Each platform's MCP server reports a heartbeat to the webserver
(``POST /api/mcp/heartbeat``); this module keeps the ``{platform: last_active}``
map in memory and classifies liveness into 3 levels by TTL.

Because the store is in-memory, a webserver restart resets it — every platform
then reads ``not_connected`` until it reports again.  A platform whose MCP
process is killed hard falls back to the TTL (last heartbeat ages past 30min →
``lost``), so no separate disconnect signal is required for that case.

Levels:
  - ``connected``    last active < 10 min
  - ``inactive``     10–30 min since last active
  - ``lost``         >= 30 min since last active
  - ``not_connected`` never reported (or process restarted)
"""

from __future__ import annotations

import threading
import time

CONNECTED_AFTER = 10 * 60    # <10 min
LOST_AFTER = 30 * 60         # >=30 min
LOST_MARK_AGE = 3600         # graceful-exit "mark lost" sets last_active this far back

_lock = threading.Lock()
_last_active: dict[str, float] = {}


def report(platform: str, now: float | None = None) -> None:
    """Record a heartbeat for *platform* at (default: now)."""
    if not platform:
        return
    with _lock:
        _last_active[platform] = now if now is not None else time.time()


def mark_lost(platform: str, now: float | None = None) -> None:
    """Explicitly mark a platform lost (graceful MCP exit).

    Sets last_active far enough back that :func:`status` returns ``lost``.
    """
    if not platform:
        return
    now = now if now is not None else time.time()
    with _lock:
        _last_active[platform] = now - LOST_MARK_AGE


def status(platform: str, now: float | None = None) -> str:
    """Classify a platform's current connection level."""
    now = now if now is not None else time.time()
    with _lock:
        last = _last_active.get(platform)
    if last is None:
        return "not_connected"
    age = now - last
    if age < CONNECTED_AFTER:
        return "connected"
    if age < LOST_AFTER:
        return "inactive"
    return "lost"


def reset() -> None:
    """Clear all tracked platforms (tests / restart)."""
    with _lock:
        _last_active.clear()
