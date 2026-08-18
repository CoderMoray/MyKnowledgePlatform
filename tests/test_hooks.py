"""Tests for /hooks/pre-tool-use — guarding bare AI operations on the KB.

KB root is monkeypatched to a temp dir so we never touch the real
``~/.myknowledge``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.hooks as hooks


@pytest.fixture
def kb_root(tmp_path: Path, monkeypatch) -> Path:
    """Point hooks.resolve_root at a temp KB root."""
    monkeypatch.setattr(hooks, "resolve_root", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)


class TestMCP:
    def test_mcp_tool_allow(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "mcp__MyKnowledge__write__create_document",
            "tool_input": {},
            "cwd": str(kb_root),
        })
        assert r.status_code == 200
        d = r.json()
        assert d["permission"] == "allow"
        assert d["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_mcp_colon_allow(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "mcp:MyKnowledge", "tool_input": {}, "cwd": ""})
        assert r.json()["permission"] == "allow"


class TestNonKB:
    def test_project_code_allow(self, kb_root: Path, client) -> None:
        """Tool call targeting project code (outside KB) → allow."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/myproject/src/app.py",
                           "content": "x"},
            "cwd": "/tmp/myproject",
        })
        assert r.json()["permission"] == "allow"


class TestKBWriteDeny:
    def test_bash_rm_kb_deny(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Bash",
            "tool_input": {"command": f"rm -rf {kb_root}/projects/P"},
            "cwd": str(kb_root),
        })
        d = r.json()
        assert d["permission"] == "deny"
        assert "write__delete_document" in d["agent_message"]

    def test_bash_redirect_kb_deny(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Bash",
            "tool_input": {"command": f"echo x > {kb_root}/common-knowledge/a.md"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"

    def test_write_tool_kb_deny(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Write",
            "tool_input": {"file_path": str(kb_root / "common-knowledge" / "a.md"),
                           "content": "x"},
            "cwd": str(kb_root),
        })
        d = r.json()
        assert d["permission"] == "deny"
        assert "write__create_document" in d["agent_message"]

    def test_edit_tool_kb_deny(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Edit",
            "tool_input": {"file_path": str(kb_root / "projects" / "P"
                                            / "common-knowledge" / "b.md")},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"

    def test_delete_tool_kb_deny(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Delete",
            "tool_input": {"file_path": str(kb_root / "common-knowledge" / "c.md")},
            "cwd": str(kb_root),
        })
        d = r.json()
        assert d["permission"] == "deny"
        assert "write__delete_document" in d["agent_message"]


class TestCodeBuddyAliases:
    """CodeBuddy IDE tool names are normalized to the internal ones."""

    def test_execute_command_equals_bash(self, kb_root: Path, client) -> None:
        """execute_command rm on KB → deny (same as Bash rm)."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "execute_command",
            "tool_input": {"command": f"rm -rf {kb_root}/projects/P"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"

    def test_write_to_file_equals_write(self, kb_root: Path, client) -> None:
        """write_to_file on a KB file → deny (same as Write)."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "write_to_file",
            "tool_input": {"file_path": str(kb_root / "common-knowledge" / "a.md")},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"
        assert "write__create_document" in r.json()["agent_message"]

    def test_edit_file_equals_edit(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "edit_file",
            "tool_input": {"file_path": str(kb_root / "common-knowledge" / "b.md")},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"

    def test_delete_file_equals_delete(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "delete_file",
            "tool_input": {"file_path": str(kb_root / "common-knowledge" / "c.md")},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"
        assert "write__delete_document" in r.json()["agent_message"]

    def test_non_kb_write_alias_allowed(self, kb_root: Path, client) -> None:
        """CodeBuddy write to project code (outside KB) → allow."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "write_to_file",
            "tool_input": {"file_path": "/tmp/proj/app.py"},
            "cwd": "/tmp/proj",
        })
        assert r.json()["permission"] == "allow"


class TestCursorShellTool:
    """Cursor preToolUse reports the ``Shell`` tool (its matcher type) for shell
    commands; it must be normalized to ``Bash`` so KB bare-write interception
    applies (same judgement as execute_command)."""

    def test_shell_rm_kb_deny(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Shell",
            "tool_input": {"command": f"rm -rf {kb_root}/projects/P"},
            "cwd": str(kb_root),
        })
        d = r.json()
        assert d["permission"] == "deny"
        assert "write__delete_document" in d["agent_message"]

    def test_shell_redirect_kb_deny(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Shell",
            "tool_input": {"command": f"echo x > {kb_root}/common-knowledge/a.md"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"

    def test_shell_non_kb_allow(self, kb_root: Path, client) -> None:
        """Cursor Shell command not referencing KB → allow."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Shell",
            "tool_input": {"command": "ls -la /tmp"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "allow"

    def test_normalize_shell_to_bash(self) -> None:
        assert hooks._normalize_tool_name("Shell") == "Bash"


class TestRedirectionPrecision:
    """'>' is precise: only a KB-inside redirection target is a KB write."""

    def test_redirect_outside_kb_allow(self, kb_root: Path, client) -> None:
        """cmd > /tmp/xxx.log (KB-external target) → allow."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Bash",
            "tool_input": {"command": f"cmd > /tmp/xxx.log"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "allow"

    def test_redirect_inside_kb_deny(self, kb_root: Path, client) -> None:
        """echo x > <KB>/common-knowledge/a.md (KB-internal target) → deny."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Bash",
            "tool_input": {
                "command": f"echo x > {kb_root}/common-knowledge/a.md"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"

    def test_rm_kb_deny(self, kb_root: Path, client) -> None:
        """rm -rf <KB>/common-knowledge → deny (command references KB)."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Bash",
            "tool_input": {"command": f"rm -rf {kb_root}/common-knowledge"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"

    def test_rm_with_root_flag_not_bypassable(self, kb_root: Path, client) -> None:
        """rm -rf <KB>/x --root <KB> → deny (--root cannot bypass)."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Bash",
            "tool_input": {
                "command": f"rm -rf {kb_root}/x --root {kb_root}"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"

    def test_serve_with_root_redirect_log_allow(self, kb_root: Path,
                                                client) -> None:
        """myknowledge serve --root <KB> > /tmp/xxx.log → allow (not a KB write)."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Bash",
            "tool_input": {
                "command": f"myknowledge serve --root {kb_root} > /tmp/xxx.log"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "allow"

    def test_append_redirect_inside_kb_deny(self, kb_root: Path, client) -> None:
        """echo x >> <KB>/a.md (append into KB) → deny."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Bash",
            "tool_input": {"command": f"echo x >> {kb_root}/common-knowledge/a.md"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"

    def test_fd_dup_redirect_not_false_positive(self, kb_root: Path, client) -> None:
        """2>&1 (fd dup, no file target) on a KB command → not a redirection-write."""
        # Command references KB via --root, redirects stderr to fd 1 (no KB write)
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Bash",
            "tool_input": {
                "command": f"myknowledge serve --root {kb_root} 2>&1"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "allow"


class TestKBReadAllow:
    def test_read_tool_allow(self, kb_root: Path, client) -> None:
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Read",
            "tool_input": {"file_path": str(kb_root / "common-knowledge" / "a.md")},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "allow"

    def test_grep_allow(self, kb_root: Path, client) -> None:
        """Bash grep on KB is a read → allow (no destructive pattern)."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Bash",
            "tool_input": {"command": f"grep -r foo {kb_root}"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "allow"


class TestEdgeCases:
    def test_relative_path_resolution(self, kb_root: Path, client) -> None:
        """Relative tool_input path resolved against cwd → detected as KB."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Edit",
            "tool_input": {"file_path": "common-knowledge/x.md"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"

    def test_space_chinese_path(self, kb_root: Path, client) -> None:
        """Paths with spaces / Chinese chars inside KB are detected."""
        kb = kb_root / "projects" / "以旧换新" / "common-knowledge" / "我的 文档.md"
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Write",
            "tool_input": {"file_path": str(kb)},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "deny"

    def test_dotdot_escape_outside_kb(self, kb_root: Path, client) -> None:
        """Traversal escaping the KB root is NOT a KB path → allow."""
        r = client.post("/hooks/pre-tool-use", json={
            "tool_name": "Write",
            "tool_input": {"file_path": "../outside.txt"},
            "cwd": str(kb_root),
        })
        assert r.json()["permission"] == "allow"
