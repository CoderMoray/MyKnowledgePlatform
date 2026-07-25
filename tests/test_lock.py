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
        lock.write_text("99999:9999999999")  # far future
        assert acquire_lock(storage) is False

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
        assert len(parts) == 2
        assert parts[0].isdigit()  # PID
        assert parts[1].isdigit()  # timestamp
        now = int(time.time())
        assert abs(now - int(parts[1])) < 5  # within 5 seconds
