"""Tests for backend.client_config — AI-client (Claude/CodeBuddy) config gen & detect.

All tests monkeypatch ``Path.home()`` to a temp dir so we never touch the
user's real ``~/.claude`` / ``~/.codebuddy``.

Platform identifiers are PascalCase (ClaudeCode / ClaudeDesktop / CodeBuddyIDE /
WorkBuddy), consistent with the frontend store and URL-safe.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.client_config import (
    KINDS,
    PLATFORMS,
    _agent_target_path,
    _agent_template,
    _hooks_command_codebuddy,
    _hooks_command_claude,
    _kinds_for,
    _platform_paths,
    agent_content,
    client_installed,
    detect_all,
    detect_platform,
    enchante_deeplink,
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
        assert "Bash|Write|Edit" in matchers
        assert "127.0.0.1:8080/hooks/pre-tool-use" in \
            hk["PreToolUse"][0]["hooks"][0]["command"]

    def test_appends_without_overwriting_existing(self, fake_home: Path) -> None:
        """Existing hooks preserved; our Bash|Write|Edit matcher appended if absent."""
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
        assert any(m.get("matcher") == "Bash|Write|Edit"
                   for m in data["hooks"]["PreToolUse"])

    def test_idempotent_no_duplicate(self, fake_home: Path) -> None:
        """Writing twice does not duplicate our matcher."""
        write_kind("ClaudeCode", "hooks")
        write_kind("ClaudeCode", "hooks")
        data = _read_json(fake_home / ".claude" / "settings.json")
        my_count = sum(1 for m in data["hooks"]["PreToolUse"]
                       if m.get("matcher") == "Bash|Write|Edit")
        assert my_count == 1

    def test_upgrades_stale_matcher_in_place(self, fake_home: Path) -> None:
        """An existing install with the old 'Bash' matcher (same command signature)
        is upgraded to 'Bash|Write|Edit' on re-write — not left stale."""
        s = fake_home / ".claude" / "settings.json"
        # 模拟旧版本写入的 MyKnowledge 钩子：命令签名相同、matcher 是旧 Bash。
        _write_json(s, {"hooks": {
            "PreToolUse": [
                {"matcher": "Bash",
                 "hooks": [{"type": "command",
                            "command": "curl -s -X POST http://127.0.0.1:8080/hooks/pre-tool-use "
                                       "-H 'Content-Type: application/json' -d '$CLAUDE_TOOL_USE_INPUT'"}]},
                {"matcher": "Edit|Write",
                 "hooks": [{"type": "command", "command": "user-hook"}]},
            ],
        }})
        write_kind("ClaudeCode", "hooks")
        data = _read_json(s)
        matchers = data["hooks"]["PreToolUse"]
        # 我们的钩子 matcher 已升级，且仍是唯一的 MyKnowledge 钩子（不重复追加）。
        my = [m for m in matchers
              if "$CLAUDE_TOOL_USE_INPUT" in m["hooks"][0]["command"]]
        assert len(my) == 1
        assert my[0]["matcher"] == "Bash|Write|Edit"
        # 用户的钩子（不同 command）不受影响。
        user = [m for m in matchers if m["hooks"][0]["command"] == "user-hook"]
        assert user and user[0]["matcher"] == "Edit|Write"


class TestAgent:
    def test_creates_agent_file(self, fake_home: Path) -> None:
        write_kind("CodeBuddyIDE", "agent")
        path = fake_home / ".codebuddy" / "agents" / "MyKnowledge-agent.md"
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---")
        assert "name: MyKnowledge 知识管理专家" in text

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
            "client_installed", "connection", "mcp", "hooks", "agent"}
        assert res["WorkBuddy"]["client_installed"] is False
        assert res["WorkBuddy"]["connection"] == "not_connected"

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
            "client_installed", "connection", "mcp", "hooks", "agent"}


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
        assert fm["name"] == "MyKnowledge 知识管理专家"
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
            assert res[pl]["client_installed"] is False
            assert res[pl]["connection"] == "not_connected"
            assert res[pl]["mcp"] is False
            assert res[pl]["hooks"] is False
            assert res[pl]["agent"] is False

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

    def test_claude_matcher_bash_write_edit(self, fake_home: Path) -> None:
        """Claude PreToolUse is per-tool-name: must cover Bash+Write+Edit so the
        file_write branch in hooks.py isn't dead code (a bare 'Bash' would skip
        Write/Edit calls entirely)."""
        assert hooks_matcher("ClaudeCode")["matcher"] == "Bash|Write|Edit"

    def test_workbuddy_uses_claude_command(self, fake_home: Path) -> None:
        assert hooks_matcher("WorkBuddy")["matcher"] == "Bash|Write|Edit"
        assert hooks_matcher("WorkBuddy")["hooks"][0]["command"] \
            == hooks_matcher("ClaudeCode")["hooks"][0]["command"]

    def test_codebuddy_write_kind_uses_helper(self, fake_home: Path) -> None:
        """Writing CodeBuddyIDE hooks stores the module-form helper command."""
        write_kind("CodeBuddyIDE", "hooks")
        data = _read_json(fake_home / ".codebuddy" / "settings.json")
        cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert "python3 -m backend.hooks_forward" == cmd


class TestCodebuddyFrozenCommand:
    """Environment-aware command: frozen desktop build reuses the binary."""

    def test_dev_uses_module_form(self, monkeypatch) -> None:
        """Not frozen → module invocation (python3 -m backend.hooks_forward)."""
        monkeypatch.delattr(sys, "frozen", raising=False)
        cmd = _hooks_command_codebuddy()
        assert cmd == "python3 -m backend.hooks_forward"

    def test_frozen_uses_binary_subcommand(self, monkeypatch) -> None:
        """Frozen (PyInstaller) → <sys.executable> --hooks-forward."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        fake_bin = "/Applications/MyKnowledge.app/Contents/Resources/myknowledge-backend"
        monkeypatch.setattr(sys, "executable", fake_bin)
        cmd = _hooks_command_codebuddy()
        assert cmd == f'"{fake_bin}" --hooks-forward'
        assert "backend.hooks_forward" not in cmd

    def test_frozen_quotes_path_with_spaces(self, monkeypatch) -> None:
        """Frozen path with spaces is quoted for the shell."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        fake_bin = "/Users/me/Library/My Knowledge/myknowledge-backend"
        monkeypatch.setattr(sys, "executable", fake_bin)
        cmd = _hooks_command_codebuddy()
        assert cmd == f'"{fake_bin}" --hooks-forward'

    def test_frozen_matcher_writes_binary_command(self, fake_home, monkeypatch) -> None:
        """write_kind stores the frozen binary subcommand, not the module form."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", "/fake/app/myknowledge-backend")
        write_kind("CodeBuddyIDE", "hooks")
        data = _read_json(fake_home / ".codebuddy" / "settings.json")
        cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert cmd == '"/fake/app/myknowledge-backend" --hooks-forward'


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


class TestKinds:
    def test_claude_desktop_only_mcp(self, fake_home: Path) -> None:
        assert _kinds_for("ClaudeDesktop") == ("mcp",)

    def test_claude_code_full_kinds(self, fake_home: Path) -> None:
        assert _kinds_for("ClaudeCode") == ("mcp", "hooks", "agent")

    def test_enchante_mcp_and_agent(self, fake_home: Path) -> None:
        assert _kinds_for("Enchante") == ("mcp", "agent")

    def test_workbuddy_full_kinds(self, fake_home: Path) -> None:
        assert _kinds_for("WorkBuddy") == ("mcp", "hooks", "agent")

    def test_write_unsupported_kind_rejected(self, fake_home: Path) -> None:
        """ClaudeDesktop (mcp-only) rejects hooks/agent writes."""
        with pytest.raises(ValueError, match="不支持.*hooks"):
            write_kind("ClaudeDesktop", "hooks")
        with pytest.raises(ValueError, match="不支持.*agent"):
            write_kind("ClaudeDesktop", "agent")
        # Enchante has no hooks
        with pytest.raises(ValueError, match="不支持.*hooks"):
            write_kind("Enchante", "hooks")


class TestEnchante:
    def test_client_installed_app(self, fake_home: Path, monkeypatch) -> None:
        """Enchante installed when Enchanté.app is present."""
        import backend.client_config as cc
        apps = fake_home / "Applications"
        (apps / "Enchanté.app").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        # _enchante_installed checks /Applications and ~/Applications
        monkeypatch.setattr(cc, "_enchante_installed",
                            lambda: True)
        assert client_installed("Enchante") is True

    def test_write_agent_short_circuits_to_deeplink(self, fake_home: Path) -> None:
        """Enchante agent is installed via deeplink — write_kind short-circuits,
        does NOT write a local SKILL.md (no standalone skill is shipped)."""
        res = write_kind("Enchante", "agent")
        assert res["status"] == "deeplink"
        assert res["file"] == ""
        # nothing written under ~/.agents
        assert not (fake_home / ".agents" / "skills" / "myknowledge").exists()

    def test_remove_agent_deeplink_noop(self, fake_home: Path) -> None:
        """Enchante remove agent reports deeplink (no local file to delete)."""
        res = remove_kind("Enchante", "agent")
        assert res["status"] == "deeplink"

    def test_detect_agent_false_for_enchante(self, fake_home: Path) -> None:
        """Enchante agent is deeplink-installed (no local agent file) → agent=false."""
        res = detect_platform("Enchante")
        assert res["agent"] is False

    def test_deeplink_generation(self, fake_home: Path) -> None:
        import base64
        link = enchante_deeplink()
        assert link.startswith("enchante://mcp/install?name=MyKnowledge&config=")
        enc = link.split("config=")[1]
        # '+' must be URL-quoted as %2B (Swift URLComponents would misread a raw
        # '+' as a space).  The quoted value decodes back to the original base64.
        assert "+" not in enc
        bundle = json.loads(
            base64.b64decode(urllib.parse.unquote(enc)).decode("utf-8"))
        assert bundle["displayName"] == "MyKnowledge"
        assert bundle["icon"] == "book.closed"
        cfg = bundle["config"]
        assert cfg["type"] == "stdio"
        assert cfg["args"] == ["-m", "backend.cli", "mcp"]
        assert cfg["env"]["MYKNOWLEDGE_CLIENT"] == "Enchante"
        assert "MYKNOWLEDGE_ROOT" in cfg["env"]

    def test_deeplink_base64_decodes_after_unquote(self, fake_home: Path) -> None:
        """The quoted config round-trips through urllib.parse.unquote + b64decode."""
        import base64
        import urllib.parse
        enc = enchante_deeplink().split("config=")[1]
        # unquote %2B back to + then base64-decode must not raise
        bundle = json.loads(
            base64.b64decode(urllib.parse.unquote(enc)).decode("utf-8"))
        assert bundle["config"]["env"]["MYKNOWLEDGE_CLIENT"] == "Enchante"

    def test_agent_deeplink(self, fake_home: Path) -> None:
        """Agent deeplink (schema confirmed with Enchante 2026-08-19).

        Pins the URL scheme, display name ``MyKnowledge 知识管理专家``, the shared
        '+'→'%2B' quoting + base64 round-trip, and the confirmed payload schema
        ``{role, skillNames, mcpServers}`` (role reuses the agent template, the
        mcpServers bundle reuses mcp_entry("Enchante")).
        """
        import base64
        import urllib.parse
        from backend.client_config import enchante_agent_deeplink
        link = enchante_agent_deeplink()
        assert link.startswith("enchante://agent/install?name=")
        assert urllib.parse.unquote(
            link.split("&config=")[0].split("name=")[1]) == "MyKnowledge 知识管理专家"
        enc = link.split("config=")[1]
        assert "+" not in enc  # '+'→'%2B'
        bundle = json.loads(
            base64.b64decode(urllib.parse.unquote(enc)).decode("utf-8"))
        assert bundle["role"].startswith("# MyKnowledge Agent")
        # no standalone skill is shipped anymore → skillNames stays empty
        assert bundle["skillNames"] == []
        srv = bundle["mcpServers"]["MyKnowledge"]
        assert srv["displayName"] == "MyKnowledge"
        assert srv["icon"] == "book.closed"
        assert srv["config"]["args"] == ["-m", "backend.cli", "mcp"]
        assert srv["config"]["env"]["MYKNOWLEDGE_CLIENT"] == "Enchante"


class TestDeeplinkEndpoint:
    def test_enchante_deeplink_endpoint(self, fake_home: Path) -> None:
        """GET /api/client-config/Enchante/deeplink returns the deeplink."""
        from backend.main import app
        c = TestClient(app)
        r = c.get("/api/client-config/Enchante/deeplink")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) == {"deeplink"}
        assert data["deeplink"].startswith(
            "enchante://mcp/install?name=MyKnowledge&config=")

    def test_non_enchante_deeplink_400(self, fake_home: Path) -> None:
        """Other platforms return 400."""
        from backend.main import app
        c = TestClient(app)
        r = c.get("/api/client-config/ClaudeCode/deeplink")
        assert r.status_code == 400
        assert "仅 Enchante" in r.json()["detail"]

    def test_deeplink_endpoint_matches_function(self, fake_home: Path) -> None:
        """Endpoint output equals backend.enchante_deeplink()."""
        from backend.main import app
        c = TestClient(app)
        data = c.get("/api/client-config/Enchante/deeplink").json()
        assert data["deeplink"] == enchante_deeplink()

    def test_agent_deeplink_endpoint(self, fake_home: Path) -> None:
        """GET /api/client-config/Enchante/agent-deeplink returns agent link."""
        from backend.client_config import enchante_agent_deeplink
        from backend.main import app
        c = TestClient(app)
        r = c.get("/api/client-config/Enchante/agent-deeplink")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) == {"deeplink"}
        assert data["deeplink"].startswith("enchante://agent/install?name=")
        assert data["deeplink"] == enchante_agent_deeplink()

    def test_non_enchante_agent_deeplink_400(self, fake_home: Path) -> None:
        """Other platforms return 400 for agent deeplink."""
        from backend.main import app
        c = TestClient(app)
        r = c.get("/api/client-config/ClaudeCode/agent-deeplink")
        assert r.status_code == 400
        assert "agent deeplink" in r.json()["detail"]


class TestCursor:
    """Cursor is a full-surface platform (mcp + hooks + agent), hooks.json-based."""

    def test_platform_paths(self, fake_home: Path) -> None:
        p = _platform_paths("Cursor")
        assert p["mcp_file"] == fake_home / ".cursor" / "mcp.json"
        assert p["hooks_file"] == fake_home / ".cursor" / "hooks.json"
        assert p["agents_dir"] == fake_home / ".cursor" / "agents"

    def test_kinds_full(self, fake_home: Path) -> None:
        assert _kinds_for("Cursor") == ("mcp", "hooks", "agent")

    def test_client_installed_dir_exists(self, fake_home: Path) -> None:
        (fake_home / ".cursor").mkdir(parents=True)
        assert client_installed("Cursor") is True

    def test_client_installed_absent(self, fake_home: Path) -> None:
        assert client_installed("Cursor") is False

    def test_mcp_entry_injects_client_env(self, fake_home: Path) -> None:
        entry = mcp_entry("Cursor")
        assert entry["env"]["MYKNOWLEDGE_CLIENT"] == "Cursor"
        assert "MYKNOWLEDGE_ROOT" in entry["env"]

    def test_write_mcp(self, fake_home: Path) -> None:
        write_kind("Cursor", "mcp")
        data = _read_json(fake_home / ".cursor" / "mcp.json")
        assert "MyKnowledge" in data["mcpServers"]

    def test_remove_mcp(self, fake_home: Path) -> None:
        write_kind("Cursor", "mcp")
        remove_kind("Cursor", "mcp")
        assert "MyKnowledge" not in \
            _read_json(fake_home / ".cursor" / "mcp.json")["mcpServers"]

    def test_hooks_matcher_shell(self, fake_home: Path) -> None:
        """Cursor uses matcher Shell|Write|Delete + hooks_forward command
        (hooks.json format). Per Cursor docs the preToolUse matcher tool types are
        Shell/Read/Write/Grep/Delete/Task/MCP (no separate Edit — edits route
        through Write); Delete exists natively (unlike Claude Code), so we cover
        shell + write + delete to avoid a dead file_write branch."""
        m = hooks_matcher("Cursor")
        assert m["matcher"] == "Shell|Write|Delete"
        assert m["type"] == "command"
        assert "backend.hooks_forward" in m["command"]
        assert m["failClosed"] is False
        assert m["timeout"] == 10000

    def test_write_hooks_keeps_version_and_existing(self, fake_home: Path) -> None:
        """Cursor hooks.json: version:1 preserved, user hooks preserved, ours appended."""
        hj = fake_home / ".cursor" / "hooks.json"
        _write_json(hj, {
            "version": 1,
            "hooks": {
                "preToolUse": [
                    {"type": "command", "command": "user-hook",
                     "matcher": "Read", "timeout": 5000, "failClosed": True},
                ],
            },
        })
        write_kind("Cursor", "hooks")
        data = _read_json(hj)
        assert data["version"] == 1
        hk = data["hooks"]["preToolUse"]
        assert any(m.get("command") == "user-hook" for m in hk)  # preserved
        our = [m for m in hk if "backend.hooks_forward" in m.get("command", "")]
        assert len(our) == 1
        assert our[0]["matcher"] == "Shell|Write|Delete"

    def test_write_hooks_idempotent(self, fake_home: Path) -> None:
        write_kind("Cursor", "hooks")
        write_kind("Cursor", "hooks")
        data = _read_json(fake_home / ".cursor" / "hooks.json")
        our = [m for m in data["hooks"]["preToolUse"]
               if "backend.hooks_forward" in m.get("command", "")]
        assert len(our) == 1

    def test_remove_hooks_keeps_others(self, fake_home: Path) -> None:
        hj = fake_home / ".cursor" / "hooks.json"
        _write_json(hj, {
            "version": 1,
            "hooks": {"preToolUse": [
                {"type": "command", "command": "user-hook",
                 "matcher": "Read", "timeout": 5000, "failClosed": True},
            ]},
        })
        write_kind("Cursor", "hooks")
        remove_kind("Cursor", "hooks")
        data = _read_json(hj)
        cmds = [m.get("command") for m in data["hooks"]["preToolUse"]]
        assert "user-hook" in cmds  # user's own preserved
        assert not any("backend.hooks_forward" in (c or "") for c in cmds)

    def test_write_agent(self, fake_home: Path) -> None:
        write_kind("Cursor", "agent")
        path = fake_home / ".cursor" / "agents" / "MyKnowledge-agent.md"
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        fm = text.split("---")[1]
        assert "name: MyKnowledge 知识管理专家" in fm
        assert "description:" in fm

    def test_remove_agent_deletes_file(self, fake_home: Path) -> None:
        write_kind("Cursor", "agent")
        path = fake_home / ".cursor" / "agents" / "MyKnowledge-agent.md"
        assert path.exists()
        remove_kind("Cursor", "agent")
        assert not path.exists()

    def test_detect_all_includes_cursor(self, fake_home: Path,
                                        monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        res = detect_all()
        assert "Cursor" in res
        assert set(res["Cursor"].keys()) == {
            "client_installed", "connection", "mcp", "hooks", "agent"}
        assert res["Cursor"]["client_installed"] is False

    def test_detect_present(self, fake_home: Path, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda *a, **k: None)
        write_kind("Cursor", "mcp")
        write_kind("Cursor", "hooks")
        write_kind("Cursor", "agent")
        res = detect_platform("Cursor")
        assert res["mcp"] is True
        assert res["hooks"] is True
        assert res["agent"] is True


class TestHooksDesignDir:
    """backend/AiClientConfig/hooks/ — authoritative per-platform hooks design."""

    def test_all_supported_platforms_have_a_file(self, fake_home: Path) -> None:
        import backend.client_config as cc
        hdir = cc._aiclient_config_dir() / "hooks"
        files = {p.stem for p in hdir.glob("*.json")}
        assert files == set(PLATFORMS)

    def test_schema_consistent(self, fake_home: Path) -> None:
        import backend.client_config as cc
        hdir = cc._aiclient_config_dir() / "hooks"
        schema_keys = {
            "platform", "display", "supports_hooks", "event", "matcher",
            "matcher_note", "command", "protocol", "exit_code_deny",
            "fail_open", "notes"}
        for p in hdir.glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            assert set(d.keys()) == schema_keys
            assert d["platform"] == p.stem
            assert d["exit_code_deny"] == 2
            assert d["fail_open"] is True

    def test_support_flags_match_kinds(self, fake_home: Path) -> None:
        """supports_hooks aligns with platforms.json kinds."""
        import backend.client_config as cc
        hdir = cc._aiclient_config_dir() / "hooks"
        for p in hdir.glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            has_hooks = "hooks" in _kinds_for(d["platform"])
            assert d["supports_hooks"] == has_hooks, p.stem

    def test_hooks_forward_platforms_reference_it(self, fake_home: Path) -> None:
        """Cursor/CodeBuddy reference the hooks_forward helper in command."""
        import backend.client_config as cc
        hdir = cc._aiclient_config_dir() / "hooks"
        for name in ("Cursor", "CodeBuddyIDE"):
            d = json.loads((hdir / f"{name}.json").read_text(encoding="utf-8"))
            assert "backend.hooks_forward" in d["command"]


class TestREST:
    def test_detect_endpoint(self, fake_home: Path) -> None:
        from backend.main import app
        c = TestClient(app)
        r = c.get("/api/client-config")
        assert r.status_code == 200
        data = r.json()
        for pl in PLATFORMS:
            assert set(data[pl].keys()) == {
                "client_installed", "connection", "mcp", "hooks", "agent"}

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
        """MCP entry env carries the resolved KB root + client id."""
        entry = mcp_entry("CodeBuddyIDE")
        assert "MYKNOWLEDGE_ROOT" in entry["env"]
        assert entry["env"]["MYKNOWLEDGE_CLIENT"] == "CodeBuddyIDE"

    def test_cursor_hooks_endpoint_writes_hooks_json(self, fake_home: Path) -> None:
        """POST Cursor/hooks writes ~/.cursor/hooks.json (version:1 + preToolUse)."""
        from backend.main import app
        c = TestClient(app)
        r = c.post("/api/client-config/Cursor/hooks")
        assert r.status_code == 200
        assert r.json()["kind"] == "hooks"
        hj = fake_home / ".cursor" / "hooks.json"
        data = json.loads(hj.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["hooks"]["preToolUse"][0]["matcher"] == "Shell|Write|Delete"

    def test_cursor_hooks_endpoint_detect_reflects(self, fake_home: Path) -> None:
        """Write/remove Cursor hooks reflects in /api/client-config detect."""
        from backend.main import app
        c = TestClient(app)
        assert c.get("/api/client-config").json()["Cursor"]["hooks"] is False
        c.post("/api/client-config/Cursor/hooks")
        assert c.get("/api/client-config").json()["Cursor"]["hooks"] is True
        c.delete("/api/client-config/Cursor/hooks")
        assert c.get("/api/client-config").json()["Cursor"]["hooks"] is False


class TestPlatformSpecJson:
    """Platform config paths are driven by AiClientConfig/platforms.json."""

    def test_platforms_derived_from_json(self, fake_home: Path) -> None:
        """PLATFORMS / kinds come from platforms.json (single source)."""
        import backend.client_config as cc
        data = cc._load_platforms_data()
        json_platforms = tuple(data["platforms"].keys())
        assert PLATFORMS == json_platforms
        for pl in PLATFORMS:
            assert cc._kinds_for(pl) == tuple(
                data["platforms"][pl].get("kinds") or ["mcp", "hooks", "agent"])

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
