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
"""

from __future__ import annotations

import json
import sys
import urllib.request

from backend.client_config import HOOK_ENDPOINT


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


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw else {}
        body = {
            "tool_name": str(payload.get("tool_name") or ""),
            "tool_input": payload.get("tool_input") or {},
            "cwd": str(payload.get("cwd") or ""),
        }
        req = urllib.request.Request(
            HOOK_ENDPOINT,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            out = resp.read().decode("utf-8")
        # CodeBuddy expects stdout JSON; merge permissionDecision into
        # hookSpecificOutput as-is (the server already returns both shapes).
        sys.stdout.write(out)
    except Exception:  # noqa: BLE001 — fail-open so users aren't blocked
        sys.stdout.write(json.dumps(_allow(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
