"""Tests for backend/connection — MCP heartbeat + liveness classification."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend import connection
from backend.client_config import detect_platform


def _reset():
    connection.reset()


class TestLivenessLevels:
    def test_not_connected_initial(self) -> None:
        _reset()
        assert connection.status("ClaudeCode") == "not_connected"

    def test_connected_under_10min(self) -> None:
        _reset()
        now = 1_000_000.0
        connection.report("ClaudeCode", now)
        assert connection.status("ClaudeCode", now + 599) == "connected"

    def test_inactive_10_to_30min(self) -> None:
        _reset()
        now = 1_000_000.0
        connection.report("ClaudeCode", now)
        assert connection.status("ClaudeCode", now + 1200) == "inactive"
        assert connection.status("ClaudeCode", now + 1799) == "inactive"

    def test_lost_after_30min(self) -> None:
        _reset()
        now = 1_000_000.0
        connection.report("ClaudeCode", now)
        assert connection.status("ClaudeCode", now + 1801) == "lost"

    def test_boundary_connected_10min(self) -> None:
        _reset()
        now = 1_000_000.0
        connection.report("ClaudeCode", now)
        # exactly 10 min = connected (<10min), 10 min + epsilon = inactive
        assert connection.status("ClaudeCode", now + 600 - 1) == "connected"
        assert connection.status("ClaudeCode", now + 600) == "inactive"

    def test_boundary_lost_30min(self) -> None:
        _reset()
        now = 1_000_000.0
        connection.report("ClaudeCode", now)
        assert connection.status("ClaudeCode", now + 1800 - 1) == "inactive"
        assert connection.status("ClaudeCode", now + 1800) == "lost"

    def test_mark_lost(self) -> None:
        _reset()
        now = 1_000_000.0
        connection.report("ClaudeCode", now)
        connection.mark_lost("ClaudeCode", now)
        assert connection.status("ClaudeCode", now + 1) == "lost"

    def test_platforms_independent(self) -> None:
        _reset()
        now = 1_000_000.0
        connection.report("ClaudeCode", now)
        assert connection.status("ClaudeCode", now + 100) == "connected"
        assert connection.status("WorkBuddy", now + 100) == "not_connected"


class TestHeartbeatEndpoint:
    def test_heartbeat_updates_connection(self, tmp_path) -> None:
        from backend.main import app
        import backend.main as bm
        from backend.storage import Storage
        from backend.readme_generator import ReadmeGenerator
        from pathlib import Path
        storage = Storage(kb_root=tmp_path)
        t = Path(tmp_path) / "_templates" / "readme.md"
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("# {name}\n\n{summary}")
        gen = ReadmeGenerator(storage=storage, template_path=t)
        bm.get_storage = lambda: (storage, gen)
        c = TestClient(app)
        _reset()

        r = c.post("/api/mcp/heartbeat",
                   headers={"X-MYKNOWLEDGE-CLIENT": "ClaudeCode"})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert connection.status("ClaudeCode") == "connected"

    def test_heartbeat_unknown_client_ignored(self, tmp_path) -> None:
        from backend.main import app
        import backend.main as bm
        from backend.storage import Storage
        from pathlib import Path
        bm.get_storage = lambda: (Storage(kb_root=tmp_path), None)
        c = TestClient(app)
        _reset()
        # unknown platform → ignored, NOT recorded
        r = c.post("/api/mcp/heartbeat",
                   headers={"X-MYKNOWLEDGE-CLIENT": "NotAPlatform"})
        assert r.json()["status"] == "ignored"
        assert connection.status("NotAPlatform") == "not_connected"

    def test_heartbeat_missing_client_ignored(self, tmp_path) -> None:
        """No MYKNOWLEDGE_CLIENT (old config) → ignored (backward compat)."""
        from backend.main import app
        import backend.main as bm
        from backend.storage import Storage
        bm.get_storage = lambda: (Storage(kb_root=tmp_path), None)
        c = TestClient(app)
        _reset()
        r = c.post("/api/mcp/heartbeat", headers={})
        assert r.json()["status"] == "ignored"

    def test_heartbeat_disconnect_marks_lost(self, tmp_path) -> None:
        from backend.main import app
        import backend.main as bm
        from backend.storage import Storage
        from pathlib import Path
        bm.get_storage = lambda: (Storage(kb_root=tmp_path), None)
        c = TestClient(app)
        _reset()
        connection.report("ClaudeCode")
        c.post("/api/mcp/heartbeat",
               headers={"X-MYKNOWLEDGE-CLIENT": "ClaudeCode",
                        "X-MYKNOWLEDGE-DISCONNECT": "1"})
        assert connection.status("ClaudeCode") == "lost"

    def test_detect_includes_connection(self, tmp_path) -> None:
        import backend.main as bm
        from backend.storage import Storage
        bm.get_storage = lambda: (Storage(kb_root=tmp_path), None)
        from fastapi.testclient import TestClient
        from backend.main import app
        c = TestClient(app)
        _reset()
        data = c.get("/api/client-config").json()
        for pl in data:
            assert data[pl]["connection"] == "not_connected"


class TestDetectConnectionField:
    def test_platform_detect_connection(self) -> None:
        _reset()
        assert detect_platform("ClaudeCode")["connection"] == "not_connected"
        connection.report("ClaudeCode", time.time())
        assert detect_platform("ClaudeCode")["connection"] == "connected"


class TestCmdMcpSignals:
    """SIGTERM/KeyboardInterrupt must report disconnect (mark lost) before exit."""

    def test_sigterm_handler_reports_disconnect(self, monkeypatch) -> None:
        import backend.cli as cli
        reported = []
        monkeypatch.setattr(cli, "_stop_heartbeat",
                            lambda p: reported.append(p))
        cli._install_signal_handlers("ClaudeCode")

        import signal
        with pytest.raises(SystemExit) as exc:
            signal.raise_signal(signal.SIGTERM)
        assert exc.value.code == 0
        assert reported == ["ClaudeCode"]

    def test_sigint_handler_reports_disconnect(self, monkeypatch) -> None:
        import backend.cli as cli
        reported = []
        monkeypatch.setattr(cli, "_stop_heartbeat",
                            lambda p: reported.append(p))
        cli._install_signal_handlers("WorkBuddy")

        import signal
        with pytest.raises(SystemExit) as exc:
            signal.raise_signal(signal.SIGINT)
        assert exc.value.code == 0
        assert reported == ["WorkBuddy"]
