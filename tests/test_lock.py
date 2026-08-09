"""Tests for .lock mechanism."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from backend.mcp_server import acquire_lock, release_lock, _lock_file
from backend.storage import Storage


class TestAcquireLock:
    def test_acquire_when_no_lock(self, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        assert acquire_lock(storage) is True
        assert _lock_file(tmp_kb_root).exists()

    def test_acquire_when_locked_by_other(self, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        lock = _lock_file(tmp_kb_root)
        # 存活进程（父进程）+ far future → 有效他人锁，不可强占
        lock.write_text(f"{os.getppid()}:9999999999")
        assert acquire_lock(storage) is False

    def test_acquire_reclaims_dead_pid(self, tmp_kb_root: Path) -> None:
        """锁的持有 pid 已死 → 视为死锁，立即强占（无需等超时）。"""
        storage = Storage(kb_root=tmp_kb_root)
        lock = _lock_file(tmp_kb_root)
        lock.write_text("999999:9999999999")  # dead pid + far future
        assert acquire_lock(storage) is True

    def test_acquire_after_expiry(self, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        lock = _lock_file(tmp_kb_root)
        lock.write_text("99999:1")  # very old
        assert acquire_lock(storage) is True
        content = lock.read_text(encoding="utf-8")
        assert str(os.getpid()) in content

    def test_acquire_after_corrupt_lock(self, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        lock = _lock_file(tmp_kb_root)
        lock.write_text("corrupt content")
        assert acquire_lock(storage) is True


class TestReleaseLock:
    def test_release_removes_lock(self, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        assert acquire_lock(storage) is True
        release_lock(storage)
        assert not _lock_file(tmp_kb_root).exists()

    def test_release_when_no_lock(self, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        release_lock(storage)  # should not raise


class TestLockContent:
    def test_lock_format(self, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        acquire_lock(storage)
        content = _lock_file(tmp_kb_root).read_text(encoding="utf-8")
        parts = content.split(":")
        assert len(parts) >= 2  # {pid}:{ts}(:{agent} 可选)
        assert parts[0].isdigit()  # PID
        assert parts[1].isdigit()  # timestamp
        now = int(time.time())
        assert abs(now - int(parts[1])) < 5  # within 5 seconds


class TestSanitizeAgent:
    def test_keeps_valid_chars(self) -> None:
        from backend.mcp_server import _sanitize_agent
        assert _sanitize_agent("codebuddy:task-123") == "codebuddy:task-123"
        assert _sanitize_agent("ai/agent@1") == "ai/agent@1"

    def test_drops_invalid_chars(self) -> None:
        from backend.mcp_server import _sanitize_agent
        # 空格、中文等不在白名单 → 去掉
        assert _sanitize_agent("a/b c@d") == "a/bc@d"

    def test_empty_and_truncate(self) -> None:
        from backend.mcp_server import _sanitize_agent
        assert _sanitize_agent("") == ""
        assert _sanitize_agent(None) == ""
        assert _sanitize_agent("x" * 100) == "x" * 64
