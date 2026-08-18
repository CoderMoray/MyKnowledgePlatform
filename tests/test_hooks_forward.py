"""Tests for backend/hooks_forward.py — the CodeBuddy stdin→hook forwarder.

Also covers that hooks_forward is standalone (no ``backend`` package import)
so it can be run as ``python <path>/hooks_forward.py`` and reuses the same
forwarder inside the PyInstaller desktop binary (``desktop_server --hooks-forward``).
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from backend import hooks_forward
from backend import desktop_server


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

    def test_forward_fn_returns_response(self, monkeypatch) -> None:
        """The extracted ``forward`` fn returns the response string (no stdout)."""
        expected = {"continue": True, "ok": 1}

        def fake_urlopen(req, timeout):  # noqa: ANN001
            return _FakeResp(json.dumps(expected))

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        payload = json.dumps({"tool_name": "write_to_file", "tool_input": {},
                              "cwd": "/"})
        assert json.loads(hooks_forward.forward(payload)) == expected

    def test_default_endpoint(self) -> None:
        """The default hook endpoint matches client_config's constant."""
        from backend.client_config import HOOK_ENDPOINT as CC_ENDPOINT
        assert hooks_forward.HOOK_ENDPOINT == CC_ENDPOINT

    def test_env_override(self, monkeypatch) -> None:
        """MYKNOWLEDGE_HOOK_ENDPOINT env var overrides the default endpoint."""
        # reload the module so the module-level constant picks up the env var
        monkeypatch.setenv("MYKNOWLEDGE_HOOK_ENDPOINT", "http://127.0.0.1:9999/hooks/pre-tool-use")
        import importlib
        module = importlib.reload(hooks_forward)
        assert module.HOOK_ENDPOINT == "http://127.0.0.1:9999/hooks/pre-tool-use"
        # restore default constant for subsequent tests
        monkeypatch.delenv("MYKNOWLEDGE_HOOK_ENDPOINT", raising=False)
        importlib.reload(hooks_forward)


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

    def test_forward_fn_fail_open(self, monkeypatch) -> None:
        """forward() returns the allow decision on failure (does not raise)."""

        def boom(req, timeout):  # noqa: ANN001
            raise OSError("down")

        monkeypatch.setattr(urllib.request, "urlopen", boom)
        data = json.loads(hooks_forward.forward(json.dumps({"tool_name": "x"})))
        assert data["continue"] is True
        assert data["hookSpecificOutput"]["permissionDecision"] == "allow"


class TestStandalone:
    """hooks_forward runs without the backend package import."""

    def test_no_backend_import_in_source(self) -> None:
        """Source must not import the backend package (standalone requirement)."""
        src = Path(hooks_forward.__file__).read_text(encoding="utf-8")
        assert "from backend" not in src
        assert "import backend" not in src

    def test_run_as_standalone_script(self, tmp_path: Path, monkeypatch) -> None:
        """`python <path>/hooks_forward.py` forwards stdin→stdout (fail-open)."""
        import os
        src = Path(hooks_forward.__file__)
        # Copy to an isolated dir so the backend package is not importable via cwd.
        dest = tmp_path / "hooks_forward.py"
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(dest)],
            input=json.dumps({"tool_name": "x", "tool_input": {}, "cwd": "/"}),
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "MYKNOWLEDGE_HOOK_ENDPOINT": "http://127.0.0.1:1/hooks/pre-tool-use"},
        )
        # Endpoint unreachable → fail-open allow, still exits 0.
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["continue"] is True
        assert data["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_desktop_binary_hooks_forward_flag(self, monkeypatch, tmp_path) -> None:
        """desktop_server --hooks-forward forwards stdin and stays fail-open."""
        # Ensure the running webserver is unreachable → fail-open allow.
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda req, timeout: (_ for _ in ()).throw(OSError("down")))
        monkeypatch.setattr(sys, "stdin",
                            io.StringIO(json.dumps({"tool_name": "x", "tool_input": {}, "cwd": "/"})))
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        assert desktop_server.main(["--hooks-forward"]) == 0
        data = json.loads(out.getvalue())
        assert data["continue"] is True
        assert data["hookSpecificOutput"]["permissionDecision"] == "allow"
