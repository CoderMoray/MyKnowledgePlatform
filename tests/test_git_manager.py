"""Tests for backend/git_manager.py."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

from backend.git_manager import GitManager, GitError


@pytest.fixture
def git_manager(tmp_path: Path) -> GitManager:
    """A GitManager pointing at a fresh temp directory."""
    gm = GitManager(tmp_path)
    gm.init()
    return gm


class TestGitManagerInit:
    def test_init_creates_dot_git(self, tmp_path: Path) -> None:
        gm = GitManager(tmp_path)
        assert not gm.is_initialized()
        gm.init()
        assert gm.is_initialized()

    def test_init_idempotent(self, git_manager: GitManager) -> None:
        git_manager.init()  # second call should be a no-op
        assert git_manager.is_initialized()


class TestGitManagerCommit:
    def test_head_is_none_before_any_commit(self, git_manager: GitManager, tmp_path: Path) -> None:
        assert git_manager.get_head_hash() is None

    def test_commit_returns_hash(self, git_manager: GitManager, tmp_path: Path) -> None:
        (tmp_path / "hello.md").write_text("hello")
        h = git_manager.commit("initial")
        assert h is not None
        assert len(h) == 40  # SHA1 length

    def test_commit_nothing_returns_none(self, git_manager: GitManager) -> None:
        h = git_manager.commit("nothing to commit")
        assert h is None

    def test_multiple_commits(self, git_manager: GitManager, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("a")
        h1 = git_manager.commit("first")
        (tmp_path / "b.md").write_text("b")
        h2 = git_manager.commit("second")
        assert h1 != h2


class TestGitManagerDiff:
    def test_diff_between_commits(self, git_manager: GitManager, tmp_path: Path) -> None:
        (tmp_path / "f.md").write_text("line1\nline2\n")
        h1 = git_manager.commit("first")
        (tmp_path / "f.md").write_text("line1\nchanged\nline3\n")
        h2 = git_manager.commit("second")

        diff = git_manager.read_diff(h1, h2)
        assert "changed" in diff
        assert "line1" in diff

    def test_diff_against_working_tree(self, git_manager: GitManager, tmp_path: Path) -> None:
        (tmp_path / "f.md").write_text("original")
        h = git_manager.commit("first")
        (tmp_path / "f.md").write_text("modified")

        diff = git_manager.read_diff(h)
        assert "modified" in diff


class TestGitManagerCheckpoint:
    def test_write_and_read(self, git_manager: GitManager, tmp_path: Path) -> None:
        cp_file = tmp_path / "checkpoint.txt"
        git_manager.write_checkpoint("abc123", cp_file)
        assert git_manager.read_checkpoint(cp_file) == "abc123"

    def test_read_nonexistent_returns_none(self, git_manager: GitManager, tmp_path: Path) -> None:
        assert git_manager.read_checkpoint(tmp_path / "no_such_file") is None

    def test_checkpoint_stripped(self, git_manager: GitManager, tmp_path: Path) -> None:
        cp_file = tmp_path / "cp.txt"
        git_manager.write_checkpoint("  abc123\n", cp_file)
        assert git_manager.read_checkpoint(cp_file) == "abc123"

    def test_diff_from_checkpoint(self, git_manager: GitManager, tmp_path: Path) -> None:
        cp_file = tmp_path / "cp.txt"
        (tmp_path / "f.md").write_text("v1")
        h1 = git_manager.commit("first")
        git_manager.write_checkpoint(h1, cp_file)

        (tmp_path / "f.md").write_text("v2")
        git_manager.commit("second")

        diff = git_manager.diff_from_checkpoint(cp_file)
        assert diff is not None
        assert "v2" in diff


class TestGitManagerStatus:
    def test_has_uncommitted_changes(self, git_manager: GitManager, tmp_path: Path) -> None:
        (tmp_path / "f.md").write_text("new file")
        assert git_manager.has_uncommitted_changes()

    def test_no_uncommitted_changes_after_commit(self, git_manager: GitManager, tmp_path: Path) -> None:
        (tmp_path / "f.md").write_text("content")
        git_manager.commit("done")
        assert not git_manager.has_uncommitted_changes()
