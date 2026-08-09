"""Tests for ``myknowledge rebuild`` CLI command."""

from __future__ import annotations

from pathlib import Path

from backend.cli import build_parser, cmd_init, cmd_rebuild
from backend.storage import Storage


def _mk_kb(tmp_path: Path) -> Path:
    root = str(tmp_path / "kb")
    args = build_parser().parse_args(["init", "--root", root])
    assert cmd_init(args) == 0
    return Path(root)


class TestCmdRebuild:
    def test_rebuild_root(self, tmp_path: Path) -> None:
        kb = _mk_kb(tmp_path)
        args = build_parser().parse_args(["rebuild", "--root", str(kb)])
        assert cmd_rebuild(args) == 0
        assert (kb / "readme.md").is_file()
        assert (kb / "project-status.md").is_file()

    def test_rebuild_project_layer(self, tmp_path: Path) -> None:
        kb = _mk_kb(tmp_path)
        storage = Storage(kb_root=kb)
        storage.write_document(
            "projects/P/common-knowledge/x.md", {"summary": "s"}, "# x")
        args = build_parser().parse_args(
            ["rebuild", "--root", str(kb), "projects/P"])
        assert cmd_rebuild(args) == 0
        readme = (kb / "projects" / "P" / "readme.md")
        assert readme.is_file()
        assert "x.md" in readme.read_text(encoding="utf-8")

    def test_rebuild_rejects_bad_path(self, tmp_path: Path) -> None:
        kb = _mk_kb(tmp_path)
        args = build_parser().parse_args(
            ["rebuild", "--root", str(kb), "../evil"])
        assert cmd_rebuild(args) == 1
        assert not (kb.parent / "evil").exists()

    def test_rebuild_rejects_missing_kb(self, tmp_path: Path) -> None:
        args = build_parser().parse_args(
            ["rebuild", "--root", str(tmp_path / "nope")])
        assert cmd_rebuild(args) == 1

    def test_rebuild_rejects_nonexistent_project(self, tmp_path: Path) -> None:
        kb = _mk_kb(tmp_path)
        args = build_parser().parse_args(
            ["rebuild", "--root", str(kb), "projects/nope"])
        assert cmd_rebuild(args) == 1
