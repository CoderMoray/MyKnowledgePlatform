"""Tests for ``myknowledge init`` CLI command."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pytest

from backend.cli import cmd_init, build_parser
from backend.storage import Storage, parse_frontmatter


def _make_args(root: str) -> argparse.Namespace:
    p = build_parser()
    return p.parse_args(["init", "--root", root])


class TestCmdInit:
    def test_creates_directory_tree(self, tmp_path: Path) -> None:
        root = str(tmp_path / ".myknowledge")
        args = _make_args(root)
        rc = cmd_init(args)
        assert rc == 0

        kb = Path(root)
        assert kb.is_dir()
        assert (kb / "_templates").is_dir()
        assert (kb / "_templates" / "readme.md").is_file()
        assert (kb / "common-knowledge").is_dir()
        assert (kb / "projects").is_dir()
        assert (kb / "archive").is_dir()
        assert (kb / "publish").is_dir()

    def test_copies_templates(self, tmp_path: Path) -> None:
        root = str(tmp_path / "kb")
        args = _make_args(root)
        cmd_init(args)

        kb = Path(root)
        tmpl = kb / "_templates"
        assert (tmpl / "readme.md").is_file()
        assert (tmpl / "common-knowledge.md").is_file()

    def test_creates_readme_with_frontmatter(self, tmp_path: Path) -> None:
        root = str(tmp_path / "kb")
        args = _make_args(root)
        cmd_init(args)

        kb = Path(root)
        readme = kb / "readme.md"
        assert readme.is_file()
        meta, body = parse_frontmatter(readme.read_text(encoding="utf-8"))
        assert meta["id"] == "root"
        assert meta["name"] == "MyKnowledge"
        assert "## 结构说明" in body

    def test_creates_project_status(self, tmp_path: Path) -> None:
        root = str(tmp_path / "kb")
        args = _make_args(root)
        cmd_init(args)

        assert (Path(root) / "project-status.md").is_file()

    def test_git_initialized(self, tmp_path: Path) -> None:
        root = str(tmp_path / "kb")
        args = _make_args(root)
        cmd_init(args)

        assert (Path(root) / ".git").is_dir()

    def test_git_has_initial_commit(self, tmp_path: Path) -> None:
        root = str(tmp_path / "kb")
        args = _make_args(root)
        cmd_init(args)

        from backend.git_manager import GitManager
        gm = GitManager(Path(root))
        h = gm.get_head_hash()
        assert h is not None
        assert len(h) == 40

    def test_refuses_existing_dir(self, tmp_path: Path) -> None:
        root = str(tmp_path / "kb")
        os.makedirs(root, exist_ok=True)
        (Path(root) / "placeholder.md").write_text("hi")
        args = _make_args(root)
        rc = cmd_init(args)
        assert rc == 1  # error exit code

    def test_root_has_initial_readme(self, tmp_path: Path) -> None:
        root = str(tmp_path / "kb")
        args = _make_args(root)
        cmd_init(args)

        storage = Storage(kb_root=Path(root))
        rm = storage.get_readme_meta("")
        assert rm.id == "root"
        assert rm.name == "MyKnowledge"
        assert rm.summary == "项目知识库初始化"
