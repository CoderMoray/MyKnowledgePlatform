"""Git operations for the knowledge base.

``GitManager`` is instantiated with the repository root (usually
``kb_root``).  Call ``commit()`` after every write-through operation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


class GitError(RuntimeError):
    """Raised when a ``git`` command fails."""


class GitManager:
    """Wrap ``git`` operations for a knowledge base directory."""

    def __init__(self, repo_root: Path) -> None:
        self.repo = repo_root.resolve()

    # ── low-level runner ─────────────────────────────────────

    def _run(self, *args: str, check: bool = True) -> str:
        try:
            r = subprocess.run(
                ["git"] + list(args),
                cwd=str(self.repo),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise GitError("git command timed out")
        except FileNotFoundError:
            raise GitError("git binary not found on PATH")

        if check and r.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
        return r.stdout.strip()

    # ── lifecycle ────────────────────────────────────────────

    def init(self) -> None:
        """Initialize the repo if not already a git directory."""
        if (self.repo / ".git").exists():
            return
        self._run("init")
        self._run("config", "user.name", "myknowledge")
        self._run("config", "user.email", "myknowledge@local")

    def is_initialized(self) -> bool:
        return (self.repo / ".git").is_dir()

    # ── commit ───────────────────────────────────────────────

    def commit(self, message: str) -> Optional[str]:
        """``git add -A`` + ``git commit``.

        Returns the commit hash, or ``None`` if nothing to commit.
        Raises ``GitError`` on failure.
        """
        self._run("add", "-A")

        status = self._run("status", "--porcelain")
        if not status:
            return None

        self._run("commit", "-m", message)
        return self.get_head_hash()

    # ── head & log ───────────────────────────────────────────

    def get_head_hash(self) -> Optional[str]:
        try:
            return self._run("rev-parse", "HEAD")
        except GitError:
            return None

    def log(self, n: int = 5) -> str:
        """Last *n* commits (oneline)."""
        return self._run("log", f"-{n}", "--oneline")

    def has_uncommitted_changes(self) -> bool:
        try:
            return bool(self._run("status", "--porcelain"))
        except GitError:
            return False

    # ── diff ─────────────────────────────────────────────────

    def read_diff(self, from_hash: str, to_hash: Optional[str] = None) -> str:
        """Diff between two commits, or against working tree."""
        args = ["diff", from_hash]
        if to_hash:
            args.append(to_hash)
        return self._run(*args)

    # ── checkpoint ───────────────────────────────────────────

    def write_checkpoint(self, commit_hash: str, checkpoint_file: Path) -> None:
        """Write the agent-processed commit hash."""
        checkpoint_file.write_text(commit_hash.strip(), encoding="utf-8")

    def read_checkpoint(self, checkpoint_file: Path) -> Optional[str]:
        """Read the checkpoint, or ``None`` if missing."""
        if not checkpoint_file.exists():
            return None
        return checkpoint_file.read_text(encoding="utf-8").strip()

    def diff_from_checkpoint(self, checkpoint_file: Path) -> Optional[str]:
        """Return diff from checkpoint to HEAD."""
        cp = self.read_checkpoint(checkpoint_file)
        if not cp:
            return None
        return self.read_diff(cp, self.get_head_hash() or "HEAD")
