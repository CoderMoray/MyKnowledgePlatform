"""Tests for backend.client_config — AI-client (Claude/CodeBuddy) config gen & detect.

All tests monkeypatch ``Path.home()`` to a temp dir so we never touch the
user's real ``~/.claude`` / ``~/.codebuddy``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.client_config import (
    KINDS,
    PLATFORMS,
    agent_content,
    client_installed,
    detect_all,
    detect_platform,
    mcp_entry,
    write_kind,
)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch) -> Path:
    """Point Path.home() at a temp dir and return it."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestMCPIncrementalMerge:
    def test_preserves_existing_servers(self, fake_home: Path) -> None:
        """Other servers (RAPID/CodeGraph) survive; MyKnowledge is added."""
        mcp = fake_home / ".codebuddy" / "mcp.json"
        _write_json(mcp, {"mcpServers": {
            "RAPID": {"type": "stdio", "command": "x"},
            "CodeGraph-MyKnowledge": {"type": "stdio", "command": "y"},
        }})
        write_kind("codebuddy", "mcp")
        data = _read_json(mcp)
        servers = data["mcpServers"]
        assert "RAPID" in servers and "CodeGraph-MyKnowledge" in servers
        assert "MyKnowledge" in servers
        assert servers["MyKnowledge"]["type"] == "stdio"
        assert servers["MyKnowledge"]["args"] == ["-m", "backend.cli", "mcp"]
        assert "MYKNOWLEDGE_ROOT" in servers["MyKnowledge"]["env"]

    def test_adds_mcp_file_when_missing(self, fake_home: Path) -> None:
        """No existing mcp.json → created with only MyKnowledge."""
        write_kind("codebuddy", "mcp")
        data = _read_json(fake_home / ".codebuddy" / "mcp.json")
        assert set(data["mcpServers"].keys()) == {"MyKnowledge"}

    def test_updates_existing_myknowledge(self, fake_home: Path) -> None:
        """Existing MyKnowledge entry is updated in place, others preserved."""
        mcp = fake_home / ".codebuddy" / "mcp.json"
        _write_json(mcp, {"mcpServers": {
            "MyKnowledge": {"type": "stdio", "command": "OLD"},
            "ardot": {"type": "stdio", "command": "a"},
        }})
        write_kind("codebuddy", "mcp")
        data = _read_json(mcp)
        assert data["mcpServers"]["MyKnowledge"]["command"] != "OLD"
        assert "ardot" in data["mcpServers"]


class TestHooksIncremental:
    def test_creates_hooks_object_when_missing(self, fake_home: Path) -> None:
        """settings.json without hooks → hooks created with our PreToolUse."""
        s = fake_home / ".claude" / "settings.json"
        _write_json(s, {"enableAllProjectMcpServers": True})
        write_kind("claude", "hooks")
        data = _read_json(s)
        assert data["enableAllProjectMcpServers"] is True  # preserved
        hk = data["hooks"]
        matchers = [m.get("matcher") for m in hk["PreToolUse"]]
        assert "Bash" in matchers
        assert "127.0.0.1:8080/hooks/pre-tool-use" in \
            hk["PreToolUse"][0]["hooks"][0]["command"]

    def test_appends_without_overwriting_existing(self, fake_home: Path) -> None:
        """Existing hooks preserved; our Bash matcher appended if absent."""
        s = fake_home / ".claude" / "settings.json"
        _write_json(s, {"hooks": {
            "PostToolUse": [{"matcher": "Edit|Write",
                             "hooks": [{"type": "command", "command": "fmt"}]}],
        }})
        write_kind("claude", "hooks")
        data = _read_json(s)
        # existing PostToolUse untouched
        assert data["hooks"]["PostToolUse"][0]["matcher"] == "Edit|Write"
        # our PreToolUse added
        assert any(m.get("matcher") == "Bash"
                   for m in data["hooks"]["PreToolUse"])

    def test_idempotent_no_duplicate(self, fake_home: Path) -> None:
        """Writing twice does not duplicate our matcher."""
        write_kind("claude", "hooks")
        write_kind("claude", "hooks")
        data = _read_json(fake_home / ".claude" / "settings.json")
        bash_count = sum(1 for m in data["hooks"]["PreToolUse"]
                         if m.get("matcher") == "Bash")
        assert bash_count == 1


class TestAgent:
    def test_creates_agent_file(self, fake_home: Path) -> None:
        write_kind("codebuddy", "agent")
        path = fake_home / ".codebuddy" / "agents" / "MyKnowledge-agent.md"
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---")
        assert "name: MyKnowledge Agent" in text

    def test_agent_exists_not_overwritten(self, fake_home: Path) -> None:
        path = fake_home / ".codebuddy" / "agents" / "MyKnowledge-agent.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("CUSTOM", encoding="utf-8")
        res = write_kind("codebuddy", "agent")
        assert res["status"] == "exists"
        assert path.read_text(encoding="utf-8") == "CUSTOM"  # untouched

    def test_agent_formats_differ_by_platform(self, fake_home: Path) -> None:
        cb = agent_content("codebuddy")
        cl = agent_content("claude")
        assert "mcpServers: MyKnowledge" in cb  # CodeBuddy specific
        assert "mcpServers: MyKnowledge" not in cl  # Claude doesn't use it


class TestClientInstalled:
    def test_claude_dir_exists(self, fake_home: Path, monkeypatch) -> None:
        """~/.claude exists → claude installed even if which() is empty."""
        (fake_home / ".claude").mkdir(parents=True)
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        assert client_installed("claude") is True

    def test_claude_which_only(self, fake_home: Path, monkeypatch) -> None:
        """~/.claude absent but claude CLI on PATH → installed."""
        monkeypatch.setattr("shutil.which",
                            lambda name: "/usr/local/bin/claude" if name == "claude" else None)
        assert client_installed("claude") is True

    def test_claude_neither(self, fake_home: Path, monkeypatch) -> None:
        """Neither dir nor CLI → not installed."""
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        assert client_installed("claude") is False

    def test_codebuddy_dir(self, fake_home: Path) -> None:
        (fake_home / ".codebuddy").mkdir(parents=True)
        assert client_installed("codebuddy") is True
        assert client_installed("codebuddy") is True

    def test_codebuddy_absent(self, fake_home: Path) -> None:
        assert client_installed("codebuddy") is False


class TestDetect:
    def test_detect_absent(self, fake_home: Path, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        res = detect_all()
        assert res == {
            "claude": {"client_installed": False, "mcp": False, "hooks": False, "agent": False},
            "codebuddy": {"client_installed": False, "mcp": False, "hooks": False, "agent": False},
        }

    def test_detect_present(self, fake_home: Path, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        write_kind("claude", "mcp")
        write_kind("claude", "hooks")
        write_kind("codebuddy", "mcp")
        res = detect_all()
        assert res["claude"]["mcp"] is True
        assert res["claude"]["hooks"] is True
        assert res["claude"]["agent"] is False
        assert res["codebuddy"]["mcp"] is True

    def test_client_installed_independent_of_kinds(self, fake_home: Path,
                                                   monkeypatch) -> None:
        """Dir present but no MCP configured → installed=true, mcp=false."""
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        (fake_home / ".codebuddy").mkdir(parents=True)  # installed, no config
        res = detect_platform("codebuddy")
        assert res["client_installed"] is True
        assert res["mcp"] is False

    def test_detect_all_includes_client_installed(self, fake_home: Path,
                                                  monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        res = detect_all()
        for pl in PLATFORMS:
            assert "client_installed" in res[pl]


class TestInvalidInput:
    def test_bad_platform(self, fake_home: Path) -> None:
        with pytest.raises(ValueError, match="不支持的平台"):
            write_kind("workbuddy", "mcp")

    def test_bad_kind(self, fake_home: Path) -> None:
        with pytest.raises(ValueError, match="不支持的配置类型"):
            write_kind("claude", "nope")


class TestREST:
    def test_detect_endpoint(self, fake_home: Path) -> None:
        from backend.main import app
        c = TestClient(app)
        r = c.get("/api/client-config")
        assert r.status_code == 200
        data = r.json()
        for pl in PLATFORMS:
            assert set(data[pl].keys()) == {
                "client_installed", "mcp", "hooks", "agent"}

    def test_write_endpoint(self, fake_home: Path) -> None:
        from backend.main import app
        c = TestClient(app)
        r = c.post("/api/client-config/codebuddy/mcp")
        assert r.status_code == 200
        data = r.json()
        assert data["platform"] == "codebuddy"
        assert data["kind"] == "mcp"
        assert data["status"] == "written"
        assert data["detected"] is True

    def test_write_endpoint_bad_platform(self, fake_home: Path) -> None:
        from backend.main import app
        c = TestClient(app)
        r = c.post("/api/client-config/workbuddy/mcp")
        assert r.status_code == 400

    def test_mcp_entry_has_kb_root(self) -> None:
        """MCP entry env carries the resolved KB root."""
        entry = mcp_entry()
        assert "MYKNOWLEDGE_ROOT" in entry["env"]
