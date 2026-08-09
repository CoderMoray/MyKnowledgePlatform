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

    def test_update_updates_updated_keeps_created(self, app, storage: Storage) -> None:
        """AI update must refresh `updated` but keep `created` unchanged."""
        from datetime import date
        asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/d.md",
            "content": "# Old",
        }))
        before, _ = storage.read_document("common-knowledge/d.md")
        created = before.get("created")
        assert created, "创建时应有 created 字段"

        asyncio.run(app.call_tool("write__update_document", {
            "path": "common-knowledge/d.md",
            "content": "# New",
        }))
        after, _ = storage.read_document("common-knowledge/d.md")
        assert after["updated"] == date.today().isoformat()
        assert after["created"] == created  # created 永不改变


class TestValidatePathReadme:
    """readme.md 是系统管理的层索引，不能作为知识文档路径。"""

    @staticmethod
    def _validate(path: str) -> None:
        from backend.mcp_server import _validate_path
        _validate_path(path, kind="file")

    def test_reject_readme_as_document(self) -> None:
        # 结构合法但 basename 是 readme.md → 拒绝
        for p in [
            "projects/测试1/readme.md",
            "projects/测试1/projects/测试1.1/readme.md",
            "common-knowledge/readme.md",
            "archive/旧项目/readme.md",
        ]:
            with pytest.raises(ValueError, match="readme"):
                self._validate(p)

    def test_allow_normal_documents(self) -> None:
        # 普通知识文档不受 readme 规则误伤
        self._validate("projects/测试1/projects/测试1.1/common-knowledge/方案.md")
        self._validate("common-knowledge/术语表.md")
        self._validate("archive/旧项目/common-knowledge/归档.md")


class TestValidatePathTree:
    """项目树结构校验：项目层下只允许 common-knowledge/projects/archive。"""

    @staticmethod
    def _validate(path: str, kind: str = "file") -> None:
        from backend.mcp_server import _validate_path
        _validate_path(path, kind=kind)

    def test_reject_misplaced_subproject(self) -> None:
        # 子项目直接挂在项目下（而非 projects/ 下）
        for p in [
            "projects/测试1/测试1.1/readme.md",
            "projects/测试1/测试1.1/common-knowledge/x.md",
        ]:
            with pytest.raises(ValueError, match="下一级只能是"):
                self._validate(p)

    def test_reject_doc_directly_under_project(self) -> None:
        with pytest.raises(ValueError, match="下一级只能是"):
            self._validate("projects/测试1/xxx.md")

    def test_reject_misplaced_subproject_dir(self) -> None:
        with pytest.raises(ValueError, match="下一级只能是"):
            self._validate("projects/测试1/测试1.1", kind="dir")

    def test_reject_dir_under_common_knowledge(self) -> None:
        # dir 路径：common-knowledge/ 是文档目录不是项目容器，后面不能跟内容
        with pytest.raises(ValueError, match="不是项目容器"):
            self._validate("projects/测试1/common-knowledge/测试1.1",
                           kind="dir")

    def test_reject_doc_in_projects_layer(self) -> None:
        # 文档必须放 common-knowledge/ 下——projects/archive 层下直接落 .md 是孤儿
        for p in ["projects/测试1.md",
                  "projects/测试1/projects/测试1.1.md",
                  "archive/旧.md"]:
            with pytest.raises(ValueError, match="common-knowledge"):
                self._validate(p)

    def test_allow_correct_tree(self) -> None:
        self._validate("projects/测试1/common-knowledge/x.md")
        self._validate("projects/测试1/projects/测试1.1/common-knowledge/x.md")
        self._validate("projects/测试1/projects/测试1.1", kind="dir")
        self._validate("archive/旧项目/common-knowledge/x.md")
        self._validate("projects/测试1", kind="dir")  # 项目本身合法


class TestValidatePathBounds:
    """路径长度闸门：单段 ≤255 字节（NAME_MAX）、段数 ≤64；总长交给 OS。"""

    @staticmethod
    def _validate(path: str, kind: str = "file") -> None:
        from backend.mcp_server import _validate_path
        _validate_path(path, kind=kind)

    def test_reject_too_many_segments(self) -> None:
        # projects/P + (projects/Q) * 40 → 82 段 > 64
        p = "projects/P" + "/projects/Q" * 40
        with pytest.raises(ValueError, match="段数超过上限"):
            self._validate(p)

    def test_reject_segment_over_name_max(self) -> None:
        # "文"×100 = 300 字节 > 255 字节
        seg = "文" * 100
        with pytest.raises(ValueError, match="255"):
            self._validate(f"common-knowledge/{seg}.md")

    def test_allow_long_but_reasonable(self) -> None:
        # 单段 60 字节、共 9 段——远超真实使用但仍合法
        seg = "项目" * 10  # 60 字节
        self._validate(
            f"projects/{seg}/projects/{seg}/common-knowledge/文档.md")
        # 33 段（< 64）的深嵌套也放行
        deep = "projects/P" + "/projects/Q" * 15  # 2 + 30 = 32 段
        self._validate(f"{deep}/common-knowledge/x.md")


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

    def test_top_level_project_does_not_create_projects_readme(
            self, app, storage: Storage, tmp_kb_root: Path) -> None:
        """Updating a top-level project must not create projects/readme.md."""
        p = tmp_kb_root / "projects" / "P"
        (p / "common-knowledge").mkdir(parents=True, exist_ok=True)
        (p / "readme.md").write_text(
            "---\nid: P\nname: P\nsummary: p\nstatus: active\n---\n\n# P",
            encoding="utf-8",
        )
        asyncio.run(app.call_tool("write__update_project_meta", {
            "project_rel": "projects/P",
            "summary": "updated",
        }))
        assert not (tmp_kb_root / "projects" / "readme.md").exists()


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
