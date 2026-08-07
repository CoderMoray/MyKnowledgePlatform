"""Tests for MCP maintenance tools (validate_doc, read_diff, check_integrity)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.git_manager import GitManager
from backend.mcp_server import create_mcp_app, acquire_lock
from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage


@pytest.fixture
def app_with_git(storage: Storage, tmp_kb_root: Path):
    """App with gen + git enabled."""
    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
    template.write_text(shipped.read_text(), encoding="utf-8")

    gen = ReadmeGenerator(storage=storage, template_path=template)
    gen.rebuild("", name="TestKB", summary="test")

    acquire_lock(storage)  # create lock for write tools
    gm = GitManager(tmp_kb_root)
    gm.init()
    gm.commit("init")

    return create_mcp_app(storage, gen=gen, gm=gm)


def _tool_text(result) -> str:
    return result[0][0].text


class TestValidateDoc:
    def test_valid_doc(self, app_with_git, storage: Storage) -> None:
        storage.write_document("common-knowledge/good.md",
                               {"type": "knowledge", "summary": "ok"},
                               "# good")
        result = asyncio.run(app_with_git.call_tool(
            "maint__validate_doc", {"path": "common-knowledge/good.md"}))
        text = _tool_text(result)
        assert "✓" in text

    def test_missing_summary(self, app_with_git, storage: Storage) -> None:
        storage.write_document("common-knowledge/bad.md",
                               {"type": "knowledge"},
                               "# bad")
        result = asyncio.run(app_with_git.call_tool(
            "maint__validate_doc", {"path": "common-knowledge/bad.md"}))
        text = _tool_text(result)
        assert "⚠" in text
        assert "summary" in text

    def test_nonexistent(self, app_with_git) -> None:
        result = asyncio.run(app_with_git.call_tool(
            "maint__validate_doc", {"path": "common-knowledge/nope.md"}))
        text = _tool_text(result)
        assert "✗" in text

    def test_invalid_format(self, app_with_git) -> None:
        """Path without valid prefix should also return a controlled error."""
        result = asyncio.run(app_with_git.call_tool(
            "maint__validate_doc", {"path": "nope.md"}))
        text = _tool_text(result)
        # The error message contains recovery instructions
        assert "common-knowledge" in text or "projects" in text


class TestReadDiff:
    def test_with_checkpoint(self, app_with_git, storage: Storage,
                             tmp_kb_root: Path) -> None:
        gm = GitManager(tmp_kb_root)
        head = gm.get_head_hash()
        gm.write_checkpoint(head, tmp_kb_root / "agent-commit.txt")

        # Make a change
        storage.write_document("common-knowledge/new.md",
                               {"summary": "new"}, "# new")
        gm.commit("add doc")

        result = asyncio.run(app_with_git.call_tool(
            "maint__read_diff", {"from_hash": ""}))
        text = _tool_text(result)
        assert "new" in text or "add doc" in text

    def test_no_checkpoint(self, app_with_git) -> None:
        result = asyncio.run(app_with_git.call_tool(
            "maint__read_diff", {"from_hash": ""}))
        text = _tool_text(result)
        # Should either fail gracefully or show no-checkpoint message
        assert text


# ══════════════════════════════════════════════════════════════
#  Write-lock concurrency (pid-based mutex + re-entrancy)
# ══════════════════════════════════════════════════════════════


class TestLock:
    @staticmethod
    def _write_lock(tmp_kb_root: Path, pid: int, ts: int,
                    agent: str = "") -> None:
        (tmp_kb_root / ".lock").write_text(
            f"{pid}:{ts}:{agent}", encoding="utf-8")

    def test_cross_process_blocked(self, storage: Storage,
                                   tmp_kb_root: Path) -> None:
        """A valid lock from another pid must block a write section."""
        from backend.mcp_server import _lock_enter
        import time
        self._write_lock(tmp_kb_root, pid=999999, ts=int(time.time()))
        with pytest.raises(RuntimeError):
            _lock_enter(storage)

    def test_release_keeps_other_pid_lock(self, storage: Storage,
                                          tmp_kb_root: Path) -> None:
        """release_lock must NOT delete a lock owned by another pid."""
        from backend.mcp_server import release_lock
        import time
        self._write_lock(tmp_kb_root, pid=999999, ts=int(time.time()))
        release_lock(storage)
        assert (tmp_kb_root / ".lock").exists()

    def test_reentrant_same_pid(self, storage: Storage,
                                tmp_kb_root: Path) -> None:
        """Lock held by this process is re-entrant: no error, no release."""
        from backend.mcp_server import (acquire_lock, release_lock,
                                        _lock_enter)
        assert acquire_lock(storage) is True
        assert _lock_enter(storage) is False  # re-entered — caller must NOT release
        assert (tmp_kb_root / ".lock").exists()  # outer holder still owns it
        release_lock(storage)
        assert not (tmp_kb_root / ".lock").exists()

    def test_agent_tag_and_acquire_tool(self, app_with_git, storage: Storage,
                                        tmp_kb_root: Path) -> None:
        """maint__acquire_lock(agent=...) records the agent id."""
        from backend.mcp_server import _read_lock, lock_owner
        (tmp_kb_root / ".lock").unlink(missing_ok=True)  # fixture holds a lock
        result = asyncio.run(app_with_git.call_tool(
            "maint__acquire_lock", {"agent": "archiver"}))
        assert "LOCK ACQUIRED" in _tool_text(result)
        info = _read_lock(tmp_kb_root)
        assert info and info["agent"] == "archiver"
        assert lock_owner(storage) == "archiver"

    def test_busy_reports_holder(self, app_with_git, storage: Storage,
                                 tmp_kb_root: Path) -> None:
        """Another pid's lock → LOCK BUSY names the holder."""
        import time
        self._write_lock(tmp_kb_root, pid=999999, ts=int(time.time()),
                         agent="rival")
        result = asyncio.run(app_with_git.call_tool("maint__acquire_lock", {}))
        text = _tool_text(result)
        assert "LOCK BUSY" in text
        assert "rival" in text

    def test_wait_acquire_timeout_and_success(self, storage: Storage,
                                              tmp_kb_root: Path) -> None:
        """wait=True polls: times out against a live foreign lock, then succeeds."""
        from backend.mcp_server import acquire_lock, release_lock
        import time
        self._write_lock(tmp_kb_root, pid=999999, ts=int(time.time()))
        assert acquire_lock(storage, wait=True, timeout=1) is False
        (tmp_kb_root / ".lock").unlink(missing_ok=True)  # foreign lock frees
        assert acquire_lock(storage, wait=True, timeout=5) is True
        release_lock(storage)

    def test_reentrant_refreshes_lock(self, storage: Storage,
                                      tmp_kb_root: Path) -> None:
        """Re-entering our own lock refreshes its timestamp (long-session keepalive)."""
        import os, time
        from backend.mcp_server import _read_lock, _lock_enter
        self._write_lock(tmp_kb_root, pid=os.getpid(),
                         ts=int(time.time()) - 240, agent="sess")
        assert _lock_enter(storage) is False  # re-entrant
        info = _read_lock(tmp_kb_root)
        assert info is not None
        assert abs(int(time.time()) - info["ts"]) < 5  # timestamp refreshed
        assert info["agent"] == "sess"  # holder preserved

    def test_lock_timeout_env(self, monkeypatch) -> None:
        """MYKNOWLEDGE_LOCK_TIMEOUT controls the lock lifetime."""
        from backend.mcp_server import _lock_timeout
        assert _lock_timeout() == 300  # default
        monkeypatch.setenv("MYKNOWLEDGE_LOCK_TIMEOUT", "60")
        assert _lock_timeout() == 60
        monkeypatch.setenv("MYKNOWLEDGE_LOCK_TIMEOUT", "abc")
        assert _lock_timeout() == 300  # invalid → fallback
        monkeypatch.setenv("MYKNOWLEDGE_LOCK_TIMEOUT", "5")
        assert _lock_timeout() == 30  # floor 30s

    def test_agent_with_colon_parsed_fully(self, storage: Storage,
                                           tmp_kb_root: Path) -> None:
        """Agent ids may contain ':' (contract: client:task) — must be kept whole."""
        import os, time
        from backend.mcp_server import _read_lock
        self._write_lock(tmp_kb_root, pid=os.getpid(),
                         ts=int(time.time()), agent="codebuddy:task-999")
        info = _read_lock(tmp_kb_root)
        assert info is not None
        assert info["agent"] == "codebuddy:task-999"
