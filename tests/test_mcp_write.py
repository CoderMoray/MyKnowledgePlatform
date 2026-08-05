"""Tests for MCP write tools (create_document, update_document, update_project_meta)."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import pytest

from backend.mcp_server import create_mcp_app, acquire_lock
from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage, dump_frontmatter


@pytest.fixture
def app(storage: Storage, tmp_kb_root: Path):
    """FastMCP app with write-through enabled."""
    acquire_lock(storage)  # create lock so write tools pass
    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
    template.write_text(shipped.read_text(), encoding="utf-8")

    gen = ReadmeGenerator(storage=storage, template_path=template)
    gen.rebuild("", name="TestKB", summary="test kb")

    return create_mcp_app(storage, gen=gen)


def _tool_text(result) -> str:
    return result[0][0].text


class TestCreateDocument:
    def test_creates_file(self, app, storage: Storage) -> None:
        asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/test.md",
            "content": "# Hello",
            "summary": "test doc",
        }))
        meta, body = storage.read_document("common-knowledge/test.md")
        assert body == "# Hello"
        assert meta["summary"] == "test doc"

    def test_returns_id(self, app) -> None:
        result = asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/d.md",
            "content": "body",
        }))
        text = _tool_text(result)
        # New format: "✅ 已创建 ... → id: doc_20260729_xxxx"
        assert "id: doc_" in text

    def test_dry_run(self, app, storage: Storage) -> None:
        """dry_run=True should not create the file."""
        result = asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/dry-run-test.md",
            "content": "# Dry Run",
            "summary": "should not appear",
            "dry_run": True,
        }))
        text = _tool_text(result)
        assert "Dry-run" in text
        # File should NOT have been written
        assert not (storage.kb_root / "common-knowledge" / "dry-run-test.md").exists()

    def test_if_exists_error(self, app, storage: Storage) -> None:
        """if_exists='error' should raise when file exists."""
        path = "common-knowledge/exists-error.md"
        # First create
        asyncio.run(app.call_tool("write__create_document", {
            "path": path,
            "content": "# First",
        }))
        # Second attempt with if_exists='error'
        import pytest as _pt
        with _pt.raises(Exception):
            asyncio.run(app.call_tool("write__create_document", {
                "path": path,
                "content": "# Second",
                "if_exists": "error",
            }))

    def test_if_exists_skip(self, app, storage: Storage) -> None:
        """if_exists='skip' should not overwrite when file exists."""
        path = "common-knowledge/exists-skip.md"
        # First create
        asyncio.run(app.call_tool("write__create_document", {
            "path": path,
            "content": "# Original content",
        }))
        # Second attempt with if_exists='skip'
        result = asyncio.run(app.call_tool("write__create_document", {
            "path": path,
            "content": "# New content that should not appear",
            "if_exists": "skip",
        }))
        text = _tool_text(result)
        assert "跳过" in text
        # Verify file content was NOT overwritten
        meta, body = storage.read_document(path)
        assert "# Original content" in body

    def test_triggers_rebuild(self, app, storage: Storage) -> None:
        asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/d.md",
            "content": "body",
            "summary": "new doc",
        }))
        readme = storage.read_content("readme.md")
        assert "new doc" in readme
        assert "d.md" in readme


class TestUpdateDocument:
    def test_updates_body(self, app, storage: Storage) -> None:
        asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/d.md",
            "content": "# Old",
        }))
        asyncio.run(app.call_tool("write__update_document", {
            "path": "common-knowledge/d.md",
            "content": "# New",
        }))
        _, body = storage.read_document("common-knowledge/d.md")
        assert "# New" in body

    def test_updates_summary(self, app, storage: Storage) -> None:
        asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/d.md",
            "content": "body",
            "summary": "old summary",
        }))
        asyncio.run(app.call_tool("write__update_document", {
            "path": "common-knowledge/d.md",
            "summary": "new summary",
        }))
        meta, _ = storage.read_document("common-knowledge/d.md")
        assert meta["summary"] == "new summary"


class TestUpdateProjectMeta:
    def test_change_summary(self, app, storage: Storage) -> None:
        asyncio.run(app.call_tool("write__update_project_meta", {
            "project_rel": "",
            "summary": "updated root summary",
        }))
        meta = storage.get_readme_meta("")
        assert meta.summary == "updated root summary"

    def test_change_status(self, app, storage: Storage) -> None:
        asyncio.run(app.call_tool("write__update_project_meta", {
            "project_rel": "",
            "status": "completed",
        }))
        meta = storage.get_readme_meta("")
        assert meta.status == "completed"

    def test_name_persists(self, app, storage: Storage) -> None:
        asyncio.run(app.call_tool("write__update_project_meta", {
            "project_rel": "",
            "name": "Renamed",
        }))
        meta = storage.get_readme_meta("")
        assert meta.name == "Renamed"


class TestRebuildIndex:
    def test_rebuild_root(self, app, storage: Storage) -> None:
        result = asyncio.run(app.call_tool("maint__rebuild_index", {"project_rel": ""}))
        text = _tool_text(result)
        assert "root" in text or "已" in text

    def test_rename_project(self, app, storage: Storage,
                            tmp_kb_root: Path) -> None:
        """Rename a project with clean working tree."""
        from backend.readme_generator import ReadmeGenerator
        tmpl = tmp_kb_root / "_templates" / "readme.md"
        if not tmpl.exists():
            tmpl.parent.mkdir(parents=True, exist_ok=True)
            shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
            tmpl.write_text(shipped.read_text())

        gen = ReadmeGenerator(storage=storage, template_path=tmpl)
        gen.rebuild("", name="MyKB", summary="test")

        # Create a project with a doc
        (tmp_kb_root / "projects" / "OldName" / "common-knowledge").mkdir(parents=True)
        storage.write_readme("projects/OldName", {}, dump_frontmatter(
            {"id": "proj_old", "name": "OldName", "summary": "old"},
            "# OldName",
        ))

        # Doc with a ref INSIDE the project (should be replaced)
        storage.write_document(
            "projects/OldName/common-knowledge/doc.md",
            {"summary": "doc"},
            "内部引用 [机型清单](ref:projects/OldName/common-knowledge/机型清单.md)。",
            auto_id=False,
        )
        # External ref (should NOT be replaced)
        storage.write_document(
            "projects/OldName/common-knowledge/doc2.md",
            {"summary": "doc2"},
            "外部引用 [费率](ref:projects/金融分期/common-knowledge/费率.md)。",
            auto_id=False,
        )

        result = asyncio.run(app.call_tool(
            "write__rename_project",
            {"project_rel": "projects/OldName", "new_name": "NewName"},
        ))
        text = _tool_text(result)
        assert "已重命名" in text

        # Directory moved
        assert (tmp_kb_root / "projects" / "NewName").is_dir()
        assert not (tmp_kb_root / "projects" / "OldName").exists()

        # Readme updated
        meta = storage.get_readme_meta("projects/NewName")
        assert meta.name == "NewName"

        # Internal ref REPLACED
        doc1 = storage.read_content("projects/NewName/common-knowledge/doc.md")
        assert "ref:projects/NewName/common-knowledge/机型清单.md" in doc1
        assert "ref:projects/OldName/" not in doc1

        # External ref UNCHANGED
        doc2 = storage.read_content("projects/NewName/common-knowledge/doc2.md")
        assert "ref:projects/金融分期" in doc2

    def test_rename_rejects_dirty(self, app, storage: Storage,
                                  tmp_kb_root: Path) -> None:
        """Rename fails when project has uncommitted changes (with git init)."""
        from backend.git_manager import GitManager
        gm = GitManager(tmp_kb_root)
        gm.init()

        (tmp_kb_root / "projects" / "Dirty" / "common-knowledge").mkdir(parents=True)
        storage.write_readme("projects/Dirty", {}, dump_frontmatter(
            {"id": "dirty", "name": "Dirty", "summary": "dirty"},
            "# Dirty",
        ))
        gm.commit("setup")

        # Add a dirty file
        (tmp_kb_root / "projects" / "Dirty" / "common-knowledge" / "dirty.md").write_text(
            "dirty content"
        )

        result = asyncio.run(app.call_tool(
            "write__rename_project",
            {"project_rel": "projects/Dirty", "new_name": "Clean"},
        ))
        text = _tool_text(result)
        assert "未提交" in text or "处理" in text

    def test_rename_document(self, app, storage: Storage,
                             tmp_kb_root: Path) -> None:
        """Rename a document — file mv + ref replacement."""
        from backend.readme_generator import ReadmeGenerator
        tmpl = tmp_kb_root / "_templates" / "readme.md"
        if not tmpl.exists():
            tmpl.parent.mkdir(parents=True, exist_ok=True)
            shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
            tmpl.write_text(shipped.read_text())

        gen = ReadmeGenerator(storage=storage, template_path=tmpl)
        gen.rebuild("", name="MyKB", summary="test")

        storage.write_document(
            "common-knowledge/old.md",
            {"summary": "old"},
            "参考 [doc](ref:common-knowledge/old.md)。外部 [doc2](ref:common-knowledge/other.md)。",
            auto_id=False,
        )

        result = asyncio.run(app.call_tool(
            "write__rename_document",
            {"path": "common-knowledge/old.md", "new_name": "new.md"},
        ))
        text = _tool_text(result)
        assert "已重命名" in text

        # File moved
        assert (tmp_kb_root / "common-knowledge" / "new.md").is_file()
        assert not (tmp_kb_root / "common-knowledge" / "old.md").exists()

        # Ref to old path replaced
        content = storage.read_content("common-knowledge/new.md")
        assert "ref:common-knowledge/new.md" in content
        assert "ref:common-knowledge/old.md" not in content
        # External ref unchanged
        assert "ref:common-knowledge/other.md" in content

    def test_delete_document(self, app, storage: Storage) -> None:
        asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/to_delete.md",
            "content": "# delete me",
        }))
        assert (storage.kb_root / "common-knowledge" / "to_delete.md").exists()
        asyncio.run(app.call_tool("write__delete_document", {
            "path": "common-knowledge/to_delete.md",
        }))
        assert not (storage.kb_root / "common-knowledge" / "to_delete.md").exists()

    def test_rebuild_triggers_status(self, app, storage: Storage) -> None:
        asyncio.run(app.call_tool("maint__rebuild_index", {"project_rel": ""}))
        status_file = storage.kb_root / "project-status.md"
        assert status_file.is_file()

    def test_move_project(self, app, storage: Storage,
                           tmp_kb_root: Path) -> None:
        """Move a project to a different parent directory."""
        from backend.readme_generator import ReadmeGenerator
        tmpl = tmp_kb_root / "_templates" / "readme.md"
        if not tmpl.exists():
            tmpl.parent.mkdir(parents=True, exist_ok=True)
            shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
            tmpl.write_text(shipped.read_text())

        gen = ReadmeGenerator(storage=storage, template_path=tmpl)
        gen.rebuild("", name="MyKB", summary="test")

        # Create parent A with a sub-project Child
        (tmp_kb_root / "projects" / "ParentA" / "projects").mkdir(parents=True)
        storage.write_readme("projects/ParentA", {}, dump_frontmatter(
            {"id": "parent_a", "name": "ParentA", "summary": "parent a"},
            "# ParentA",
        ))
        gen.rebuild("projects/ParentA")

        # Create sub-project Child under ParentA
        (tmp_kb_root / "projects" / "ParentA" / "projects" / "Child" / "common-knowledge").mkdir(parents=True)
        storage.write_readme("projects/ParentA/projects/Child", {}, dump_frontmatter(
            {"id": "child", "name": "Child", "summary": "child project"},
            "# Child",
        ))
        gen.rebuild("projects/ParentA/projects/Child")

        # Create a doc in Child with a ref
        storage.write_document(
            "projects/ParentA/projects/Child/common-knowledge/doc.md",
            {"summary": "child doc"},
            "ref to self: [doc](ref:projects/ParentA/projects/Child/common-knowledge/doc.md)",
            auto_id=False,
        )

        # Create parent B
        (tmp_kb_root / "projects" / "ParentB" / "projects").mkdir(parents=True)
        storage.write_readme("projects/ParentB", {}, dump_frontmatter(
            {"id": "parent_b", "name": "ParentB", "summary": "parent b"},
            "# ParentB",
        ))
        gen.rebuild("projects/ParentB")

        # Move Child from ParentA to ParentB
        result = asyncio.run(app.call_tool(
            "write__move_project",
            {"project_rel": "projects/ParentA/projects/Child",
             "target_parent_rel": "projects/ParentB"},
        ))
        text = _tool_text(result)
        assert "已移动" in text

        # Directory moved to ParentB/projects/Child
        dest = tmp_kb_root / "projects" / "ParentB" / "projects" / "Child"
        assert dest.is_dir(), f"{dest} does not exist"
        assert not (tmp_kb_root / "projects" / "ParentA" / "projects" / "Child").exists()

        # It should appear in ParentB's readme
        parent_b_readme = storage.read_content("projects/ParentB/readme.md")
        assert "Child" in parent_b_readme

        # Move back to root level
        result2 = asyncio.run(app.call_tool(
            "write__move_project",
            {"project_rel": "projects/ParentB/projects/Child",
             "target_parent_rel": ""},
        ))
        text2 = _tool_text(result2)
        assert "已移动" in text2
        assert (tmp_kb_root / "projects" / "Child").is_dir()
        assert not (tmp_kb_root / "projects" / "ParentB" / "projects" / "Child").exists()

    def test_delete_project(self, app, storage: Storage,
                            tmp_kb_root: Path) -> None:
        """Delete a project directory via write__delete_project."""
        from backend.readme_generator import ReadmeGenerator

        # Ensure template and initial setup
        tmpl = tmp_kb_root / "_templates" / "readme.md"
        if not tmpl.exists():
            tmpl.parent.mkdir(parents=True, exist_ok=True)
            shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
            tmpl.write_text(shipped.read_text())
        gen = ReadmeGenerator(storage=storage, template_path=tmpl)
        gen.rebuild("", name="TestKB", summary="test")

        # Create a project with some content
        (tmp_kb_root / "projects" / "ToDelete" / "common-knowledge").mkdir(parents=True)
        storage.write_readme("projects/ToDelete", {}, dump_frontmatter(
            {"id": "td", "name": "ToDelete", "summary": "will be deleted"},
            "# ToDelete",
        ))
        storage.write_document(
            "projects/ToDelete/common-knowledge/doc.md",
            {"summary": "will be deleted too"},
            "# Doc to delete",
        )
        gen.rebuild("projects/ToDelete")

        # Confirm it exists
        assert (tmp_kb_root / "projects" / "ToDelete").is_dir()

        # Delete it via MCP → moves to trash
        result = asyncio.run(app.call_tool(
            "write__delete_project",
            {"project_rel": "projects/ToDelete"},
        ))
        text = _tool_text(result)
        assert "已移入垃圾箱" in text

        # Should no longer exist at original path, but live in trash
        assert not (tmp_kb_root / "projects" / "ToDelete").exists()
        assert (tmp_kb_root / "trash" / "projects" / "ToDelete").is_dir()

        # Parent readme should have been rebuilt
        root_readme = storage.read_content("readme.md")
        assert "ToDelete" not in root_readme


class TestCheckIntegrity:
    def test_runs_without_error(self, app) -> None:
        result = asyncio.run(app.call_tool("maint__check_integrity", {}))
        text = _tool_text(result)
        assert text  # non-empty response
