"""PreToolUse hook forwarder for CodeBuddy IDE.

CodeBuddy passes PreToolUse hook data on **stdin** (JSON) and expects the
response JSON on **stdout** — unlike Claude (which uses ``$CLAUDE_TOOL_USE_INPUT``).

This helper:
  1. reads the stdin JSON → extracts ``{tool_name, tool_input, cwd}``
  2. POSTs it to the MyKnowledge webserver hook endpoint (/hooks/pre-tool-use)
  3. prints the response JSON on stdout

Failure fallback: if the POST fails (server down / bad payload), we print an
**allow** decision so legitimate user operations are never blocked by an
unreachable hook endpoint.

**Standalone**: this module has **no dependency on the ``backend`` package** so
it can run in two ways:
  - development:  ``python3 -m backend.hooks_forward``
  - standalone:   ``python3 <path>/hooks_forward.py``  (any interpreter)
  - PyInstaller frozen desktop app: the ``myknowledge-backend`` binary is invoked
    with ``--hooks-forward`` (see ``desktop_server.py``), which calls
    :func:`forward` / :func:`main` here. Because the module is imported by
    ``desktop_server``, PyInstaller traces it into the PYZ bundle so it is
    importable inside the frozen binary (no standalone python exists in onedir).

The hook endpoint is an env-or-default constant (``MYKNOWLEDGE_HOOK_ENDPOINT``),
kept identical to ``backend/client_config.py::HOOK_ENDPOINT``'s default so a
standalone run targets the same webserver.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

# Same default as backend/client_config.py::HOOK_ENDPOINT. Read from env so a
# deployed/standalone hook can be redirected without editing the script.
DEFAULT_HOOK_ENDPOINT = "http://127.0.0.1:8080/hooks/pre-tool-use"
HOOK_ENDPOINT = os.environ.get("MYKNOWLEDGE_HOOK_ENDPOINT") or DEFAULT_HOOK_ENDPOINT


def _allow() -> dict:
    """Default allow response used on any failure (fail-open)."""
    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "MyKnowledge hook 端点不可达，放行。",
        },
    }


def forward(raw: str) -> str:
    """Forward one stdin payload string to the hook endpoint; return the stdout string.

    This is the transport+decision logic split out of ``main`` so it is
    unit-testable without patching ``sys.stdin``/``sys.stdout``. On any failure
    it returns the fail-open allow decision (never raises).
    """
    try:
        payload = json.loads(raw) if raw else {}
        body = {
            "tool_name": str(payload.get("tool_name") or ""),
            "tool_input": payload.get("tool_input") or {},
            "cwd": str(payload.get("cwd") or ""),
        }
        req = urllib.request.Request(  # noqa: S310 — local webserver hook
            HOOK_ENDPOINT,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            out = resp.read().decode("utf-8")
        # CodeBuddy expects stdout JSON; merge permissionDecision into
        # hookSpecificOutput as-is (the server already returns both shapes).
        return out
    except Exception:  # noqa: BLE001 — fail-open so users aren't blocked
        return json.dumps(_allow(), ensure_ascii=False)


def main() -> int:
    """Read stdin, forward, write the response to stdout (fail-open)."""
    sys.stdout.write(forward(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
