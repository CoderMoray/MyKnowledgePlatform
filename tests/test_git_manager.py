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

    def test_read_worktree_diff(self, git_manager: GitManager, tmp_path: Path) -> None:
        (tmp_path / "f.md").write_text("original")
        git_manager.commit("first")
        (tmp_path / "f.md").write_text("modified")

        diff = git_manager.read_worktree_diff()
        assert "modified" in diff
        assert "original" in diff

    def test_read_worktree_diff_clean(self, git_manager: GitManager, tmp_path: Path) -> None:
        (tmp_path / "f.md").write_text("content")
        git_manager.commit("first")

        assert git_manager.read_worktree_diff() == ""


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


class TestGitManagerWorktreeStatus:
    def test_filters_system_noise(self, git_manager: GitManager, tmp_path: Path) -> None:
        """Runtime system files (.mcp-heartbeat, .events/) must not count."""
        (tmp_path / ".mcp-heartbeat").write_text("write:0")
        (tmp_path / ".events").mkdir()
        (tmp_path / ".events" / "version.json").write_text("{}")
        (tmp_path / ".DS_Store").write_text("")
        assert git_manager.worktree_status() == []

    def test_returns_user_files_only(self, git_manager: GitManager, tmp_path: Path) -> None:
        (tmp_path / ".mcp-heartbeat").write_text("write:0")
        (tmp_path / "common-knowledge").mkdir()
        (tmp_path / "common-knowledge" / "draft.md").write_text("# draft body")
        status = git_manager.worktree_status()
        assert status == [("??", "common-knowledge/draft.md")]

    def test_read_worktree_diff_full_includes_untracked(self, git_manager: GitManager,
                                                        tmp_path: Path) -> None:
        (tmp_path / "common-knowledge").mkdir()
        (tmp_path / "common-knowledge" / "draft.md").write_text("# draft body")
        diff = git_manager.read_worktree_diff_full(["common-knowledge/draft.md"])
        assert "draft body" in diff
        assert "+" in diff  # synthetic addition diff

    def test_read_worktree_diff_full_clean(self, git_manager: GitManager, tmp_path: Path) -> None:
        (tmp_path / "f.md").write_text("content")
        git_manager.commit("first")
        assert git_manager.read_worktree_diff_full([]) == ""

    def test_staged_rename_returns_destination_path(self, git_manager: GitManager,
                                                    tmp_path: Path) -> None:
        """git mv (staged rename) must yield the *new* path, not 'old -> new'."""
        import subprocess
        (tmp_path / "common-knowledge").mkdir(parents=True)
        (tmp_path / "common-knowledge" / "old.md").write_text("# old body")
        git_manager.commit("add old")
        subprocess.run(
            ["git", "mv", "common-knowledge/old.md", "common-knowledge/new.md"],
            cwd=tmp_path, check=True)
        assert git_manager.worktree_status() == [("R ", "common-knowledge/new.md")]

    def test_unstaged_rename_delete_plus_untracked(self, git_manager: GitManager,
                                                   tmp_path: Path) -> None:
        """Worktree rename (delete old + create new) parses both correctly."""
        (tmp_path / "common-knowledge").mkdir(parents=True)
        (tmp_path / "common-knowledge" / "old.md").write_text("# old body")
        git_manager.commit("add old")
        (tmp_path / "common-knowledge" / "old.md").unlink()
        (tmp_path / "common-knowledge" / "new.md").write_text("# new body")
        status = git_manager.worktree_status()
        assert (" D", "common-knowledge/old.md") in status
        assert ("??", "common-knowledge/new.md") in status

    def test_no_head_untracked_diff(self, git_manager: GitManager, tmp_path: Path) -> None:
        """Empty repo (no HEAD yet) + untracked draft must still produce a diff."""
        (tmp_path / "common-knowledge").mkdir(parents=True)
        (tmp_path / "common-knowledge" / "draft.md").write_text("# draft body")
        diff = git_manager.read_worktree_diff_full(["common-knowledge/draft.md"])
        assert "draft body" in diff

    def test_hidden_underscore_prefix_still_noise(self, git_manager: GitManager,
                                                  tmp_path: Path) -> None:
        """New runtime files starting with '.' at root are caught generically."""
        (tmp_path / ".cache").mkdir()
        (tmp_path / ".cache" / "x").write_text("1")
        (tmp_path / ".tmp_heartbeat").write_text("1")
        assert git_manager.worktree_status() == []
