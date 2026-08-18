"""Tests for backend/hooks_forward.py — the CodeBuddy stdin→hook forwarder."""

from __future__ import annotations

import io
import json
import sys
import urllib.request

from backend import hooks_forward


class _FakeResp:
    def __init__(self, text: str):
        self._text = text

    def read(self) -> bytes:
        return self._text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestForwarder:
    def test_forward_stdin_to_hook(self, monkeypatch) -> None:
        """Reads stdin JSON, POSTs it to the hook endpoint, prints response."""
        sent = {}
        payload = {"tool_name": "execute_command",
                   "tool_input": {"command": "rm x"},
                   "cwd": "/tmp"}
        expected = {"continue": True,
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny"}}

        def fake_urlopen(req, timeout):  # noqa: ANN001
            sent["url"] = req.full_url
            sent["method"] = req.get_method()
            sent["data"] = json.loads(req.data.decode("utf-8"))
            return _FakeResp(json.dumps(expected))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)

        hooks_forward.main()
        assert json.loads(out.getvalue()) == expected
        assert sent["data"] == payload
        assert sent["method"] == "POST"
        assert sent["url"].endswith("/hooks/pre-tool-use")


class TestFailOpen:
    def test_failure_returns_allow(self, monkeypatch) -> None:
        """POST failure → fail-open allow (never block the user)."""

        def boom(req, timeout):  # noqa: ANN001
            raise OSError("server down")

        monkeypatch.setattr(urllib.request, "urlopen", boom)
        monkeypatch.setattr(sys, "stdin",
                            io.StringIO(json.dumps({"tool_name": "x"})))
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)

        hooks_forward.main()
        data = json.loads(out.getvalue())
        assert data["continue"] is True
        assert data["hookSpecificOutput"]["permissionDecision"] == "allow"
