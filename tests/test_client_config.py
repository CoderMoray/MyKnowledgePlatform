"""Tests for backend.client_config — AI-client (Claude/CodeBuddy) config gen & detect.

All tests monkeypatch ``Path.home()`` to a temp dir so we never touch the
user's real ``~/.claude`` / ``~/.codebuddy``.

Platform identifiers are PascalCase (ClaudeCode / ClaudeDesktop / CodeBuddyIDE /
WorkBuddy), consistent with the frontend store and URL-safe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.client_config import (
    KINDS,
    MCP_ONLY_PLATFORMS,
    PLATFORMS,
    _agent_template,
    _hooks_command_codebuddy,
    _hooks_command_claude,
    _platform_paths,
    agent_content,
    client_installed,
    detect_all,
    detect_platform,
    hooks_matcher,
    mcp_entry,
    remove_kind,
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
        write_kind("CodeBuddyIDE", "mcp")
        data = _read_json(mcp)
        servers = data["mcpServers"]
        assert "RAPID" in servers and "CodeGraph-MyKnowledge" in servers
        assert "MyKnowledge" in servers
        assert servers["MyKnowledge"]["type"] == "stdio"
        assert servers["MyKnowledge"]["args"] == ["-m", "backend.cli", "mcp"]
        assert "MYKNOWLEDGE_ROOT" in servers["MyKnowledge"]["env"]

    def test_adds_mcp_file_when_missing(self, fake_home: Path) -> None:
        """No existing mcp.json → created with only MyKnowledge."""
        write_kind("CodeBuddyIDE", "mcp")
        data = _read_json(fake_home / ".codebuddy" / "mcp.json")
        assert set(data["mcpServers"].keys()) == {"MyKnowledge"}

    def test_updates_existing_myknowledge(self, fake_home: Path) -> None:
        """Existing MyKnowledge entry is updated in place, others preserved."""
        mcp = fake_home / ".codebuddy" / "mcp.json"
        _write_json(mcp, {"mcpServers": {
            "MyKnowledge": {"type": "stdio", "command": "OLD"},
            "ardot": {"type": "stdio", "command": "a"},
        }})
        write_kind("CodeBuddyIDE", "mcp")
        data = _read_json(mcp)
        assert data["mcpServers"]["MyKnowledge"]["command"] != "OLD"
        assert "ardot" in data["mcpServers"]


class TestHooksIncremental:
    def test_creates_hooks_object_when_missing(self, fake_home: Path) -> None:
        """settings.json without hooks → hooks created with our PreToolUse."""
        s = fake_home / ".claude" / "settings.json"
        _write_json(s, {"enableAllProjectMcpServers": True})
        write_kind("ClaudeCode", "hooks")
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
        write_kind("ClaudeCode", "hooks")
        data = _read_json(s)
        # existing PostToolUse untouched
        assert data["hooks"]["PostToolUse"][0]["matcher"] == "Edit|Write"
        # our PreToolUse added
        assert any(m.get("matcher") == "Bash"
                   for m in data["hooks"]["PreToolUse"])

    def test_idempotent_no_duplicate(self, fake_home: Path) -> None:
        """Writing twice does not duplicate our matcher."""
        write_kind("ClaudeCode", "hooks")
        write_kind("ClaudeCode", "hooks")
        data = _read_json(fake_home / ".claude" / "settings.json")
        bash_count = sum(1 for m in data["hooks"]["PreToolUse"]
                         if m.get("matcher") == "Bash")
        assert bash_count == 1


class TestAgent:
    def test_creates_agent_file(self, fake_home: Path) -> None:
        write_kind("CodeBuddyIDE", "agent")
        path = fake_home / ".codebuddy" / "agents" / "MyKnowledge-agent.md"
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---")
        assert "name: MyKnowledge Agent" in text

    def test_agent_exists_not_overwritten(self, fake_home: Path) -> None:
        path = fake_home / ".codebuddy" / "agents" / "MyKnowledge-agent.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("CUSTOM", encoding="utf-8")
        res = write_kind("CodeBuddyIDE", "agent")
        assert res["status"] == "exists"
        assert path.read_text(encoding="utf-8") == "CUSTOM"  # untouched

    def test_agent_formats_differ_by_platform(self, fake_home: Path) -> None:
        cb = agent_content("CodeBuddyIDE")
        cl = agent_content("ClaudeCode")
        assert "mcpServers: MyKnowledge" in cb  # CodeBuddy specific
        assert "mcpServers: MyKnowledge" not in cl  # Claude doesn't use it


class TestClientInstalled:
    def test_claude_dir_exists(self, fake_home: Path, monkeypatch) -> None:
        """~/.claude exists → claude installed even if which() is empty."""
        (fake_home / ".claude").mkdir(parents=True)
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        assert client_installed("ClaudeCode") is True

    def test_claude_which_only(self, fake_home: Path, monkeypatch) -> None:
        """~/.claude absent but claude CLI on PATH → installed."""
        monkeypatch.setattr("shutil.which",
                            lambda name: "/usr/local/bin/claude" if name == "claude" else None)
        assert client_installed("ClaudeCode") is True

    def test_claude_neither(self, fake_home: Path, monkeypatch) -> None:
        """Neither dir nor CLI → not installed."""
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        assert client_installed("ClaudeCode") is False

    def test_codebuddy_dir(self, fake_home: Path) -> None:
        (fake_home / ".codebuddy").mkdir(parents=True)
        assert client_installed("CodeBuddyIDE") is True
        assert client_installed("CodeBuddyIDE") is True

    def test_codebuddy_absent(self, fake_home: Path) -> None:
        assert client_installed("CodeBuddyIDE") is False


class TestWorkBuddy:
    def test_platform_paths(self, fake_home: Path) -> None:
        p = _platform_paths("WorkBuddy")
        assert p["mcp_file"] == fake_home / ".workbuddy" / "mcp.json"
        assert p["settings_file"] == fake_home / ".workbuddy" / "settings.json"
        assert p["agents_dir"] == fake_home / ".workbuddy" / "agents"

    def test_client_installed_dir_exists(self, fake_home: Path) -> None:
        (fake_home / ".workbuddy").mkdir(parents=True)
        assert client_installed("WorkBuddy") is True

    def test_client_installed_absent(self, fake_home: Path) -> None:
        assert client_installed("WorkBuddy") is False

    def test_detect_all_includes_workbuddy(self, fake_home: Path,
                                           monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        res = detect_all()
        assert "WorkBuddy" in res
        assert set(res["WorkBuddy"].keys()) == {
            "client_installed", "mcp", "hooks", "agent"}
        assert res["WorkBuddy"]["client_installed"] is False

    def test_write_kind_workbuddy(self, fake_home: Path) -> None:
        write_kind("WorkBuddy", "mcp")
        assert (fake_home / ".workbuddy" / "mcp.json").exists()

    def test_agent_content_reuses_codebuddy_format(self, fake_home: Path) -> None:
        """WorkBuddy reuses the CodeBuddy (MCP-based) agent format."""
        assert agent_content("WorkBuddy") == agent_content("CodeBuddyIDE")
        assert "mcpServers: MyKnowledge" in agent_content("WorkBuddy")

    def test_unknown_platform_still_rejected(self, fake_home: Path) -> None:
        with pytest.raises(ValueError, match="不支持的平台"):
            _platform_paths("cursor")
        with pytest.raises(ValueError, match="不支持的平台"):
            client_installed("cursor")
        with pytest.raises(ValueError, match="不支持的平台"):
            write_kind("cursor", "mcp")


class TestClaudeDesktop:
    """ClaudeDesktop is MCP-only (no hooks / custom agents)."""

    def test_platform_paths(self, fake_home: Path) -> None:
        p = _platform_paths("ClaudeDesktop")
        assert p["mcp_file"] == \
            fake_home / "Library" / "Application Support" \
            / "Claude" / "claude_desktop_config.json"

    def test_kinds_mcp_only(self, fake_home: Path) -> None:
        from backend.client_config import _kinds_for
        assert _kinds_for("ClaudeDesktop") == ("mcp",)
        # full-surface platforms keep all three kinds
        assert _kinds_for("ClaudeCode") == ("mcp", "hooks", "agent")

    def test_client_installed_dir_exists(self, fake_home: Path) -> None:
        (fake_home / "Library" / "Application Support" / "Claude").mkdir(parents=True)
        assert client_installed("ClaudeDesktop") is True

    def test_client_installed_absent(self, fake_home: Path) -> None:
        assert client_installed("ClaudeDesktop") is False

    def test_write_kind_mcp(self, fake_home: Path) -> None:
        write_kind("ClaudeDesktop", "mcp")
        cfg = fake_home / "Library" / "Application Support" \
            / "Claude" / "claude_desktop_config.json"
        assert cfg.exists()
        data = _read_json(cfg)
        assert "MyKnowledge" in data["mcpServers"]

    def test_write_kind_hooks_rejected(self, fake_home: Path) -> None:
        with pytest.raises(ValueError, match="不支持 hooks"):
            write_kind("ClaudeDesktop", "hooks")

    def test_write_kind_agent_rejected(self, fake_home: Path) -> None:
        with pytest.raises(ValueError, match="不支持 agent"):
            write_kind("ClaudeDesktop", "agent")

    def test_remove_kind_mcp(self, fake_home: Path) -> None:
        write_kind("ClaudeDesktop", "mcp")
        res = remove_kind("ClaudeDesktop", "mcp")
        assert res["status"] == "removed"
        cfg = fake_home / "Library" / "Application Support" \
            / "Claude" / "claude_desktop_config.json"
        assert "MyKnowledge" not in _read_json(cfg)["mcpServers"]

    def test_detect_reports_hooks_agent_false(self, fake_home: Path) -> None:
        res = detect_platform("ClaudeDesktop")
        assert res["hooks"] is False
        assert res["agent"] is False
        assert res["mcp"] is False

    def test_detect_all_includes_claude_desktop(self, fake_home: Path,
                                                monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        res = detect_all()
        assert "ClaudeDesktop" in res
        assert set(res["ClaudeDesktop"].keys()) == {
            "client_installed", "mcp", "hooks", "agent"}


class TestAgentTemplate:
    def test_body_comes_from_template(self, fake_home: Path) -> None:
        """agent_content body matches the shipped template (content/code separation)."""
        body = _agent_template()
        assert "你是 MyKnowledge 知识管理平台的专业 Agent" in body
        assert body in agent_content("ClaudeCode")
        assert body in agent_content("CodeBuddyIDE")

    def test_frontmatter_differs_by_platform(self, fake_home: Path) -> None:
        cl = agent_content("ClaudeCode")
        cb = agent_content("CodeBuddyIDE")
        # frontmatter: codebuddy has agentMode/enabled/mcpServers; claude does not
        assert "agentMode: manual" in cb.split("---")[1]
        assert "mcpServers: MyKnowledge" in cb.split("---")[1]
        assert "agentMode: manual" not in cl.split("---")[1]
        assert "mcpServers: MyKnowledge" not in cl.split("---")[1]

    def test_missing_template_raises_clear_error(self, fake_home: Path,
                                                 monkeypatch) -> None:
        import backend.client_config as cc
        # point template resolution at a nonexistent file
        monkeypatch.setattr(
            cc, "_agent_template",
            lambda: (_ for _ in ()).throw(
                RuntimeError("缺失 Agent 模板")))
        with pytest.raises(RuntimeError, match="缺失 Agent 模板"):
            cc.agent_content("ClaudeCode")

    def test_frontmatter_reads_from_json(self, fake_home: Path) -> None:
        """Frontmatter comes from frontmatter.json, not hardcoded."""
        import backend.client_config as cc
        fm = cc._frontmatter_for("ClaudeCode")
        assert fm["name"] == "MyKnowledge Agent"
        assert "tools" in fm
        assert "model" in fm

    def test_frontmatter_booleans_render_lowercase_yaml(self, fake_home: Path) -> None:
        """Booleans render as true/false (YAML), not Python True/False."""
        cb = agent_content("CodeBuddyIDE")
        fm = cb.split("---")[1]
        assert "enabled: true" in fm
        assert "enabledAutoRun: true" in fm
        assert "enabled: True" not in fm

    def test_unknown_platform_frontmatter_raises(self, fake_home: Path) -> None:
        import backend.client_config as cc
        # ClaudeDesktop has no agent variant → frontmatter lookup raises
        with pytest.raises(RuntimeError, match="未覆盖平台"):
            cc._frontmatter_for("ClaudeDesktop")


class TestDetect:
    def test_detect_absent(self, fake_home: Path, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        res = detect_all()
        # every platform is absent (not installed, no MyKnowledge entries)
        assert set(res.keys()) == set(PLATFORMS)
        for pl in PLATFORMS:
            assert res[pl] == {
                "client_installed": False, "mcp": False,
                "hooks": False, "agent": False,
            }

    def test_detect_present(self, fake_home: Path, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        write_kind("ClaudeCode", "mcp")
        write_kind("ClaudeCode", "hooks")
        write_kind("CodeBuddyIDE", "mcp")
        res = detect_all()
        assert res["ClaudeCode"]["mcp"] is True
        assert res["ClaudeCode"]["hooks"] is True
        assert res["ClaudeCode"]["agent"] is False
        assert res["CodeBuddyIDE"]["mcp"] is True

    def test_client_installed_independent_of_kinds(self, fake_home: Path,
                                                   monkeypatch) -> None:
        """Dir present but no MCP configured → installed=true, mcp=false."""
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        (fake_home / ".codebuddy").mkdir(parents=True)  # installed, no config
        res = detect_platform("CodeBuddyIDE")
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
            write_kind("cursor", "mcp")

    def test_bad_kind(self, fake_home: Path) -> None:
        with pytest.raises(ValueError, match="不支持的配置类型"):
            write_kind("ClaudeCode", "nope")


class TestHooksMatcher:
    def test_commands_differ_by_platform(self, fake_home: Path) -> None:
        """ClaudeCode uses curl/$CLAUDE_TOOL_USE_INPUT; CodeBuddyIDE uses helper script."""
        claude = hooks_matcher("ClaudeCode")
        codebuddy = hooks_matcher("CodeBuddyIDE")
        assert claude["hooks"][0]["command"] != codebuddy["hooks"][0]["command"]
        assert "$CLAUDE_TOOL_USE_INPUT" in claude["hooks"][0]["command"]
        assert "backend.hooks_forward" in codebuddy["hooks"][0]["command"]

    def test_codebuddy_matcher_all(self, fake_home: Path) -> None:
        """CodeBuddy matcher '*' matches all tools (MCP allowed internally)."""
        assert hooks_matcher("CodeBuddyIDE")["matcher"] == "*"

    def test_claude_matcher_bash(self, fake_home: Path) -> None:
        assert hooks_matcher("ClaudeCode")["matcher"] == "Bash"

    def test_workbuddy_uses_claude_command(self, fake_home: Path) -> None:
        assert hooks_matcher("WorkBuddy")["matcher"] == "Bash"
        assert hooks_matcher("WorkBuddy")["hooks"][0]["command"] \
            == hooks_matcher("ClaudeCode")["hooks"][0]["command"]

    def test_codebuddy_write_kind_uses_helper(self, fake_home: Path) -> None:
        """Writing CodeBuddyIDE hooks stores the module-form helper command."""
        write_kind("CodeBuddyIDE", "hooks")
        data = _read_json(fake_home / ".codebuddy" / "settings.json")
        cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert "python3 -m backend.hooks_forward" == cmd


class TestRemoveKind:
    def test_remove_mcp_keeps_others(self, fake_home: Path) -> None:
        """mcpServers loses MyKnowledge, other servers preserved."""
        mcp = fake_home / ".codebuddy" / "mcp.json"
        _write_json(mcp, {"mcpServers": {
            "RAPID": {"type": "stdio", "command": "x"},
            "MyKnowledge": {"type": "stdio", "command": "y"},
        }})
        write_kind("CodeBuddyIDE", "mcp")  # ensures entry is ours-format
        remove_kind("CodeBuddyIDE", "mcp")
        servers = _read_json(mcp)["mcpServers"]
        assert "MyKnowledge" not in servers
        assert "RAPID" in servers

    def test_remove_hooks_keeps_others(self, fake_home: Path) -> None:
        """PreToolUse loses the MyKnowledge matcher, keeps other matchers/hooks.

        The user's own Bash hook (different command) must be preserved — only
        the MyKnowledge matcher (exact command signature) is removed.
        """
        s = fake_home / ".claude" / "settings.json"
        user_bash_cmd = "curl -s -X POST http://127.0.0.1:8080/hooks/pre-tool-use x"
        _write_json(s, {"hooks": {
            "PreToolUse": [
                {"matcher": "Bash",
                 "hooks": [{"type": "command", "command": user_bash_cmd}]},
                {"matcher": "Edit|Write",
                 "hooks": [{"type": "command", "command": "fmt"}]},
            ],
        }})
        write_kind("ClaudeCode", "hooks")  # appends our exact-command matcher
        remove_kind("ClaudeCode", "hooks")
        data = _read_json(s)
        cmds = [m["hooks"][0]["command"] for m in data["hooks"]["PreToolUse"]]
        # our exact MyKnowledge command gone, user's own hooks preserved
        assert "$CLAUDE_TOOL_USE_INPUT" not in "\n".join(cmds)
        assert user_bash_cmd in cmds
        assert "fmt" in cmds

    def test_remove_agent_deletes_file(self, fake_home: Path) -> None:
        write_kind("CodeBuddyIDE", "agent")
        path = fake_home / ".codebuddy" / "agents" / "MyKnowledge-agent.md"
        assert path.exists()
        remove_kind("CodeBuddyIDE", "agent")
        assert not path.exists()

    def test_remove_idempotent(self, fake_home: Path) -> None:
        """Removing an absent entry succeeds (no error)."""
        res = remove_kind("CodeBuddyIDE", "mcp")
        assert res["status"] == "removed"
        remove_kind("ClaudeCode", "agent")  # no file → still ok
        remove_kind("ClaudeCode", "hooks")  # no hooks → still ok

    def test_remove_unknown_platform_kind(self, fake_home: Path) -> None:
        with pytest.raises(ValueError, match="不支持的平台"):
            remove_kind("cursor", "mcp")
        with pytest.raises(ValueError, match="不支持的配置类型"):
            remove_kind("ClaudeCode", "nope")

    def test_api_delete_returns_removed(self, fake_home: Path) -> None:
        from backend.main import app
        c = TestClient(app)
        r = c.delete("/api/client-config/CodeBuddyIDE/mcp")
        assert r.status_code == 200
        assert r.json()["status"] == "removed"
        assert r.json()["kind"] == "mcp"

    def test_api_delete_reflects_in_detect(self, fake_home: Path) -> None:
        from backend.main import app
        c = TestClient(app)
        c.post("/api/client-config/CodeBuddyIDE/mcp")
        assert c.get("/api/client-config").json()["CodeBuddyIDE"]["mcp"] is True
        c.delete("/api/client-config/CodeBuddyIDE/mcp")
        assert c.get("/api/client-config").json()["CodeBuddyIDE"]["mcp"] is False

    def test_api_delete_bad_platform(self, fake_home: Path) -> None:
        from backend.main import app
        c = TestClient(app)
        r = c.delete("/api/client-config/cursor/mcp")
        assert r.status_code == 400


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
        r = c.post("/api/client-config/CodeBuddyIDE/mcp")
        assert r.status_code == 200
        data = r.json()
        assert data["platform"] == "CodeBuddyIDE"
        assert data["kind"] == "mcp"
        assert data["status"] == "written"
        assert data["detected"] is True

    def test_write_endpoint_bad_platform(self, fake_home: Path) -> None:
        from backend.main import app
        c = TestClient(app)
        r = c.post("/api/client-config/cursor/mcp")
        assert r.status_code == 400

    def test_mcp_entry_has_kb_root(self) -> None:
        """MCP entry env carries the resolved KB root."""
        entry = mcp_entry()
        assert "MYKNOWLEDGE_ROOT" in entry["env"]


class TestPlatformSpecJson:
    """Platform config paths are driven by AiClientConfig/platforms.json."""

    def test_platforms_derived_from_json(self, fake_home: Path) -> None:
        """PLATFORMS / MCP_ONLY_PLATFORMS come from platforms.json (single source)."""
        import backend.client_config as cc
        data = cc._load_platforms_data()
        json_platforms = tuple(data["platforms"].keys())
        assert PLATFORMS == json_platforms
        assert MCP_ONLY_PLATFORMS == tuple(
            k for k, v in data["platforms"].items() if v.get("mcp_only"))

    def test_claudedesktop_macos_official_path(self, fake_home: Path) -> None:
        """Claude Desktop macOS MCP path matches the official documented location."""
        p = _platform_paths("ClaudeDesktop")
        assert p["mcp_file"] == \
            fake_home / "Library" / "Application Support" \
            / "Claude" / "claude_desktop_config.json"

    def test_cli_names_from_json(self, fake_home: Path) -> None:
        """ClaudeCode exposes the ``claude`` CLI; others none."""
        import backend.client_config as cc
        assert cc._cli_name("ClaudeCode") == "claude"
        assert cc._cli_name("ClaudeDesktop") == ""

    def test_platform_spec_unknown_rejected(self, fake_home: Path) -> None:
        import backend.client_config as cc
        with pytest.raises(ValueError, match="不支持的平台"):
            cc._platform_spec("cursor")
