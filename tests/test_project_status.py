"""Tests for ReadmeGenerator.rebuild_project_status() and garbage_collect()."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage, dump_frontmatter


@pytest.fixture
def gen(storage: Storage, tmp_kb_root: Path) -> ReadmeGenerator:
    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
    template.write_text(shipped.read_text(), encoding="utf-8")
    return ReadmeGenerator(storage=storage, template_path=template)


def _mk_proj(storage: Storage, rel: str, name: str, summary: str,
             status: str = "active", updated: str = "") -> None:
    """Helper: create a project with readme."""
    (storage.kb_root / rel).mkdir(parents=True, exist_ok=True)
    (storage.kb_root / rel / "common-knowledge").mkdir(exist_ok=True)
    (storage.kb_root / rel / "projects").mkdir(exist_ok=True)
    body = dump_frontmatter({
        "id": f"proj_{name}",
        "name": name,
        "summary": summary,
        "status": status,
        "updated": updated or date.today().isoformat(),
    }, "# placeholder")
    storage.write_readme(rel, {}, body)


class TestRebuildProjectStatus:
    def test_empty_kb(self, gen: ReadmeGenerator) -> None:
        content = gen.rebuild_project_status()
        assert "项目状态" in content
        assert "进行中" not in content  # no active projects

    def test_active_project(self, gen: ReadmeGenerator, storage: Storage,
                            tmp_kb_root: Path) -> None:
        _mk_proj(storage, "projects/p1", "P1", "project one")
        content = gen.rebuild_project_status()
        assert "进行中" in content
        assert "P1" in content
        assert "project one" in content

    def test_mixed_status(self, gen: ReadmeGenerator, storage: Storage,
                          tmp_kb_root: Path) -> None:
        _mk_proj(storage, "projects/current", "Current", "active project")
        _mk_proj(storage, "archive/done", "Done", "completed project",
                 status="completed")
        _mk_proj(storage, "archive/cancelled", "Cancelled", "cancelled project",
                 status="cancelled")
        _mk_proj(storage, "archive/old", "Old", "abandoned project",
                 status="abandoned", updated="2019-01-01")

        content = gen.rebuild_project_status()
        assert "进行中" in content
        assert "已完成" in content
        assert "已取消" in content
        assert "已废弃" in content
        assert "Current" in content
        assert "Done" in content
        assert "Cancelled" in content
        assert "Old" in content

    def test_writes_to_file(self, gen: ReadmeGenerator, storage: Storage,
                            tmp_kb_root: Path) -> None:
        _mk_proj(storage, "projects/p1", "P1", "p1")
        gen.rebuild_project_status()
        status_file = tmp_kb_root / "project-status.md"
        assert status_file.is_file()
        assert "P1" in status_file.read_text(encoding="utf-8")


class TestGarbageCollect:
    def test_removes_old_abandoned(self, gen: ReadmeGenerator, storage: Storage,
                                   tmp_kb_root: Path) -> None:
        old = date.today() - timedelta(days=40)
        _mk_proj(storage, "archive/old", "Old", "too old",
                 status="abandoned", updated=old.isoformat())
        removed = gen.garbage_collect()
        assert "Old" in removed
        assert not (tmp_kb_root / "archive" / "old").exists()

    def test_keeps_young_abandoned(self, gen: ReadmeGenerator, storage: Storage,
                                   tmp_kb_root: Path) -> None:
        recent = date.today() - timedelta(days=5)
        _mk_proj(storage, "archive/recent", "Recent", "too recent",
                 status="abandoned", updated=recent.isoformat())
        removed = gen.garbage_collect()
        assert removed == []
        assert (tmp_kb_root / "archive" / "recent").exists()

    def test_ignores_completed(self, gen: ReadmeGenerator, storage: Storage,
                               tmp_kb_root: Path) -> None:
        old = date.today() - timedelta(days=100)
        _mk_proj(storage, "archive/old", "Old", "old but completed",
                 status="completed", updated=old.isoformat())
        removed = gen.garbage_collect()
        assert removed == []
        assert (tmp_kb_root / "archive" / "old").exists()

    def test_returns_empty_when_nothing_to_do(self, gen: ReadmeGenerator) -> None:
        removed = gen.garbage_collect()
        assert removed == []
