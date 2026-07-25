"""Tests for backend/readme_generator.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage, dump_frontmatter


@pytest.fixture
def gen(storage: Storage, tmp_kb_root: Path) -> ReadmeGenerator:
    """Generator using the shipped template."""
    template = (
        Path(__file__).resolve().parent.parent
        / "backend" / "templates" / "readme.md"
    )
    return ReadmeGenerator(storage=storage, template_path=template)


def _create_project(storage: Storage, kb_root: Path,
                    rel: str, name: str, summary: str) -> None:
    """Helper: create minimal project structure with readme."""
    proj_dir = kb_root / rel
    proj_dir.mkdir(parents=True, exist_ok=True)
    ck_dir = proj_dir / "common-knowledge"
    ck_dir.mkdir(exist_ok=True)
    sub_dir = proj_dir / "projects"
    sub_dir.mkdir(exist_ok=True)
    storage.write_readme(rel, {}, dump_frontmatter({
            "id": "root" if rel == "" else f"proj_{name}",
            "type": "readme",
            "name": name,
            "summary": summary,
            "status": "active",
            "updated": "2026-07-23",
            "generated": "2026-07-23",
        }, "# placeholder"))


def _create_doc(storage: Storage, kb_root: Path,
                rel: str, summary: str, updated: str = "2026-07-23") -> None:
    """Helper: write a knowledge document with summary."""
    storage.write_document(rel, {
        "type": "knowledge",
        "summary": summary,
        "updated": updated,
    }, "# doc body")


# ══════════════════════════════════════════════════════════════

class TestRebuildEmpty:
    def test_rebuild_empty_root(self, gen: ReadmeGenerator,
                                storage: Storage, tmp_kb_root: Path) -> None:
        _create_project(storage, tmp_kb_root, "", "MyKnowledge", "test kb")
        result = gen.rebuild("")
        assert "# MyKnowledge" in result
        assert "## 核心文档" in result
        assert "## 子项目" in result
        assert "## 归档" in result
        assert "_暂无_" in result  # empty sections

    def test_rebuild_root_with_doc(self, gen: ReadmeGenerator,
                                   storage: Storage, tmp_kb_root: Path) -> None:
        _create_project(storage, tmp_kb_root, "", "MyKnowledge", "test kb")
        _create_doc(storage, tmp_kb_root,
                    "common-knowledge/test.md", "a test doc")
        result = gen.rebuild("")
        assert "a test doc" in result
        assert "common-knowledge/test.md" in result

    def test_rebuild_root_with_project(self, gen: ReadmeGenerator,
                                       storage: Storage,
                                       tmp_kb_root: Path) -> None:
        _create_project(storage, tmp_kb_root, "", "MyKnowledge", "test kb")
        _create_project(storage, tmp_kb_root,
                        "projects/p1", "P1", "project one")
        result = gen.rebuild("")
        assert "projects/p1" in result
        assert "project one" in result


class TestRebuildProject:
    def test_rebuild_project_with_docs(self, gen: ReadmeGenerator,
                                       storage: Storage,
                                       tmp_kb_root: Path) -> None:
        _create_project(storage, tmp_kb_root, "", "MyKnowledge", "")
        _create_project(storage, tmp_kb_root,
                        "projects/以旧换新", "以旧换新",
                        "换新政策知识库")
        _create_doc(storage, tmp_kb_root,
                    "projects/以旧换新/common-knowledge/补贴标准.md",
                    "A 品牌最高 500 元")

        result = gen.rebuild("projects/以旧换新", parent="root")
        assert "# 以旧换新" in result
        assert "补贴标准" in result
        assert "A 品牌最高 500 元" in result
        assert "parent: root" in result

    def test_project_with_subproject(self, gen: ReadmeGenerator,
                                     storage: Storage,
                                     tmp_kb_root: Path) -> None:
        _create_project(storage, tmp_kb_root, "", "MyKnowledge", "")
        _create_project(storage, tmp_kb_root,
                        "projects/parent", "Parent", "parent project")
        _create_project(storage, tmp_kb_root,
                        "projects/parent/projects/child", "Child",
                        "child project")

        result = gen.rebuild("projects/parent")
        assert "projects/parent/projects/child" in result
        assert "child project" in result


class TestRebuildFrontmatter:
    def test_frontmatter_fields(self, gen: ReadmeGenerator,
                                storage: Storage,
                                tmp_kb_root: Path) -> None:
        _create_project(storage, tmp_kb_root, "", "MyKnowledge",
                        "my knowledge base")
        gen.rebuild("")
        meta = storage.get_readme_meta("")
        assert meta.id == "root"
        assert meta.name == "MyKnowledge"
        assert meta.summary == "my knowledge base"
        assert meta.generated  # today

    def test_generated_is_iso_date(self, gen: ReadmeGenerator,
                                    storage: Storage,
                                    tmp_kb_root: Path) -> None:
        _create_project(storage, tmp_kb_root, "", "MyKnowledge",
                        "my kb")
        gen.rebuild("")
        meta = storage.get_readme_meta("")
        assert len(meta.generated) == 10  # yyyy-mm-dd
        assert len(meta.updated) == 10


class TestRebuildNoExistingReadme:
    def test_first_build_root(self, gen: ReadmeGenerator,
                              storage: Storage,
                              tmp_kb_root: Path) -> None:
        """Rebuild when no readme.md exists yet."""
        result = gen.rebuild("", name="MyNewKB",
                             summary="fresh start")
        assert "# MyNewKB" in result
        meta = storage.get_readme_meta("")
        assert meta.name == "MyNewKB"

    def test_first_build_project_inferred_name(self, gen: ReadmeGenerator,
                                                storage: Storage,
                                                tmp_kb_root: Path) -> None:
        (tmp_kb_root / "projects" / "my-project").mkdir(parents=True)
        (tmp_kb_root / "projects" / "my-project" / "common-knowledge").mkdir()
        (tmp_kb_root / "projects" / "my-project" / "projects").mkdir()
        result = gen.rebuild("projects/my-project", parent="root")
        # name inferred from directory
        assert "my-project" in result or "# my-project" in result
