"""Tests for the trash (recycle bin) mechanism.

Covers the full delete / restore / out-of-order / GC / ref-status matrix:
D1-D4, R1-R6, G1-G2, C1-C4 from the design doc.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.mcp_server import create_mcp_app, acquire_lock
from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage, dump_frontmatter


@pytest.fixture
def app(storage: Storage, tmp_kb_root: Path):
    acquire_lock(storage)
    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
    template.write_text(shipped.read_text(), encoding="utf-8")
    gen = ReadmeGenerator(storage=storage, template_path=template)
    gen.rebuild("", name="TestKB", summary="test kb")
    return create_mcp_app(storage, gen=gen)


def _tool_text(result) -> str:
    return result[0][0].text


def _mkdoc(storage: Storage, path: str, body: str = "# body") -> None:
    storage.write_document(path, {"summary": "s", "maintainer": "Me"},
                           body, auto_id=False)


def _del_doc(app, path: str) -> str:
    return _tool_text(asyncio.run(app.call_tool("write__delete_document", {"path": path})))


def _del_proj(app, proj: str) -> str:
    return _tool_text(asyncio.run(app.call_tool("write__delete_project", {"project_rel": proj})))


def _restore_doc(app, trash_path: str) -> str:
    return _tool_text(asyncio.run(app.call_tool("write__restore_document", {"trash_path": trash_path})))


def _restore_proj(app, trash_path: str) -> str:
    return _tool_text(asyncio.run(app.call_tool("write__restore_project", {"trash_path": trash_path})))


@pytest.fixture
def client_factory(tmp_kb_root: Path, storage: Storage):
    """Return (TestClient, storage, tmp_kb_root) with get_storage overridden."""
    import backend.main
    from backend.main import app as _app
    from backend.main import get_storage as _orig
    from fastapi.testclient import TestClient

    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
    if not template.exists():
        template.write_text(shipped.read_text(encoding="utf-8"), encoding="utf-8")
    gen = ReadmeGenerator(storage=storage, template_path=template)

    def _test_storage():
        return storage, gen

    backend.main.get_storage = _test_storage
    yield TestClient(_app), storage, tmp_kb_root
    backend.main.get_storage = _orig


# ══════════════════════════════════════════════════════════════
#  Delete
# ══════════════════════════════════════════════════════════════


class TestDelete:
    def test_d1_delete_doc_moves_to_trash(self, app, storage: Storage, tmp_kb_root: Path):
        _mkdoc(storage, "common-knowledge/x.md")
        text = _del_doc(app, "common-knowledge/x.md")
        assert "移入垃圾箱" in text
        assert not (tmp_kb_root / "common-knowledge" / "x.md").exists()
        # in trash/documents with stamps
        docs = list((tmp_kb_root / "trash" / "documents").glob("*.md"))
        assert len(docs) == 1
        meta, _ = storage.read_document(f"trash/documents/{docs[0].name}")
        assert meta["original_path"] == "common-knowledge/x.md"
        assert "deleted_at" in meta

    def test_d2_delete_project_moves_to_trash(self, app, storage: Storage, tmp_kb_root: Path):
        (tmp_kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True)
        storage.write_readme("projects/P", {}, dump_frontmatter(
            {"id": "P", "name": "P", "summary": "p"}, "# P"))
        _mkdoc(storage, "projects/P/common-knowledge/doc.md")
        text = _del_proj(app, "projects/P")
        assert "移入垃圾箱" in text
        assert not (tmp_kb_root / "projects" / "P").exists()
        assert (tmp_kb_root / "trash" / "projects" / "P").is_dir()
        # project readme stamped
        meta, _ = storage.read_document("trash/projects/P/readme.md")
        assert meta["original_path"] == "projects/P"
        assert "deleted_at" in meta

    def test_d3_delete_doc_then_project(self, app, storage: Storage, tmp_kb_root: Path):
        """Delete a doc inside P, then delete P itself."""
        (tmp_kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True)
        storage.write_readme("projects/P", {}, dump_frontmatter(
            {"id": "P", "name": "P", "summary": "p"}, "# P"))
        _mkdoc(storage, "projects/P/common-knowledge/x.md")
        _del_doc(app, "projects/P/common-knowledge/x.md")   # x → trash/documents
        _del_proj(app, "projects/P")                          # P → trash/projects
        # x's original_path still points into P (now trashed)
        docs = list((tmp_kb_root / "trash" / "documents").glob("*.md"))
        assert len(docs) == 1
        meta, _ = storage.read_document(f"trash/documents/{docs[0].name}")
        assert meta["original_path"] == "projects/P/common-knowledge/x.md"
        assert (tmp_kb_root / "trash" / "projects" / "P").is_dir()

    def test_d4_delete_nonexistent(self, app):
        # _validate_path raises a ToolError for non-existent files
        with pytest.raises(Exception):
            _del_doc(app, "common-knowledge/nope.md")


# ══════════════════════════════════════════════════════════════
#  Restore
# ══════════════════════════════════════════════════════════════


class TestRestore:
    def test_r1_restore_doc(self, app, storage: Storage, tmp_kb_root: Path):
        _mkdoc(storage, "common-knowledge/x.md")
        _del_doc(app, "common-knowledge/x.md")
        trash = list((tmp_kb_root / "trash" / "documents").glob("*.md"))[0].name
        text = _restore_doc(app, f"trash/documents/{trash}")
        assert "已恢复" in text
        assert (tmp_kb_root / "common-knowledge" / "x.md").is_file()
        assert not list((tmp_kb_root / "trash" / "documents").glob("*.md"))
        # stamps cleared
        meta, body = storage.read_document("common-knowledge/x.md")
        assert "original_path" not in meta
        assert "deleted_at" not in meta

    def test_r2_restore_project(self, app, storage: Storage, tmp_kb_root: Path):
        (tmp_kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True)
        storage.write_readme("projects/P", {}, dump_frontmatter(
            {"id": "P", "name": "P", "summary": "p"}, "# P"))
        _del_proj(app, "projects/P")
        text = _restore_proj(app, "trash/projects/P")
        assert "已恢复" in text
        assert (tmp_kb_root / "projects" / "P").is_dir()
        assert not (tmp_kb_root / "trash" / "projects" / "P").exists()
        # readme stamps cleared
        meta, _ = storage.read_document("projects/P/readme.md")
        assert "deleted_at" not in meta

    def test_r3_out_of_order_restore_doc_before_project_blocked(
            self, app, storage: Storage, tmp_kb_root: Path):
        """D3 scenario: delete doc inside P, then delete P, restore doc first → blocked."""
        (tmp_kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True)
        storage.write_readme("projects/P", {}, dump_frontmatter(
            {"id": "P", "name": "P", "summary": "p"}, "# P"))
        _mkdoc(storage, "projects/P/common-knowledge/x.md")
        _del_doc(app, "projects/P/common-knowledge/x.md")
        _del_proj(app, "projects/P")
        trash_doc = list((tmp_kb_root / "trash" / "documents").glob("*.md"))[0].name
        text = _restore_doc(app, f"trash/documents/{trash_doc}")
        assert "请先恢复项目" in text  # parent project still in trash
        # doc stays in trash
        assert list((tmp_kb_root / "trash" / "documents").glob("*.md"))

    def test_r4_out_of_order_restore_project_then_doc(
            self, app, storage: Storage, tmp_kb_root: Path):
        """Restore P first, then doc X → both succeed."""
        (tmp_kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True)
        storage.write_readme("projects/P", {}, dump_frontmatter(
            {"id": "P", "name": "P", "summary": "p"}, "# P"))
        _mkdoc(storage, "projects/P/common-knowledge/x.md")
        _del_doc(app, "projects/P/common-knowledge/x.md")
        _del_proj(app, "projects/P")
        # Restore project first
        text = _restore_proj(app, "trash/projects/P")
        assert "已恢复" in text
        assert (tmp_kb_root / "projects" / "P").is_dir()
        # Now restore the doc
        trash_doc = list((tmp_kb_root / "trash" / "documents").glob("*.md"))[0].name
        text2 = _restore_doc(app, f"trash/documents/{trash_doc}")
        assert "已恢复" in text2
        assert (tmp_kb_root / "projects" / "P" / "common-knowledge" / "x.md").is_file()

    def test_r5_restore_twice(self, app, storage: Storage, tmp_kb_root: Path):
        _mkdoc(storage, "common-knowledge/x.md")
        _del_doc(app, "common-knowledge/x.md")
        trash = list((tmp_kb_root / "trash" / "documents").glob("*.md"))[0].name
        _restore_doc(app, f"trash/documents/{trash}")
        text = _restore_doc(app, f"trash/documents/{trash}")
        # second restore: trash item no longer there → error, no crash
        assert "已恢复" not in text

    def test_r6_restore_conflict(self, app, storage: Storage, tmp_kb_root: Path):
        """Restore when target path already occupied → no overwrite."""
        _mkdoc(storage, "common-knowledge/x.md")
        _del_doc(app, "common-knowledge/x.md")
        trash = list((tmp_kb_root / "trash" / "documents").glob("*.md"))[0].name
        # Create a new file at the same original path
        _mkdoc(storage, "common-knowledge/x.md", "# newer")
        text = _restore_doc(app, f"trash/documents/{trash}")
        assert "目标路径已存在" in text
        # trashed doc not overwritten / stays in trash
        assert list((tmp_kb_root / "trash" / "documents").glob("*.md"))
        _, body = storage.read_document("common-knowledge/x.md")
        assert "# newer" in body


# ══════════════════════════════════════════════════════════════
#  GC
# ══════════════════════════════════════════════════════════════


class TestRestoreGuards:
    """恢复路径防护：original_path 是历史数据，恢复前必须重新校验。"""

    def test_restore_rejects_invalid_original_path(self, storage: Storage,
                                                  tmp_kb_root: Path):
        """历史脏数据（readme/非法层级）不得恢复到非法位置。"""
        from backend.trash import restore
        tdir = tmp_kb_root / "trash" / "documents"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "bad.md").write_text(
            "---\nid: bad\nsummary: s\ntype: knowledge\n"
            "original_path: projects/P/readme.md\ndeleted_at: 2026-01-01\n---\n# x",
            encoding="utf-8")
        with pytest.raises(ValueError, match="不合法"):
            restore(storage, "trash/documents/bad.md")

    def test_restore_rejects_orphan_doc_path(self, storage: Storage,
                                             tmp_kb_root: Path):
        """original_path 是 projects 层孤儿文档位置 → 拒绝。"""
        from backend.trash import restore
        tdir = tmp_kb_root / "trash" / "documents"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "bad2.md").write_text(
            "---\nid: bad2\nsummary: s\ntype: knowledge\n"
            "original_path: projects/P.md\ndeleted_at: 2026-01-01\n---\n# x",
            encoding="utf-8")
        with pytest.raises(ValueError):
            restore(storage, "trash/documents/bad2.md")


# ══════════════════════════════════════════════════════════════


class TestGC:
    def test_g1_purges_older_than_30_days(self, storage: Storage, tmp_kb_root: Path):
        from backend.trash import move_doc_to_trash, gc_trash
        _mkdoc(storage, "common-knowledge/old.md")
        move_doc_to_trash(storage, "common-knowledge/old.md")
        # Backdate deleted_at by 31 days
        from datetime import datetime, timedelta
        d = list((tmp_kb_root / "trash" / "documents").glob("*.md"))[0]
        meta, body = storage.read_document(f"trash/documents/{d.name}")
        meta["deleted_at"] = (datetime.now() - timedelta(days=31)).isoformat()
        storage.write_document(f"trash/documents/{d.name}", meta, body, auto_id=False)
        n = gc_trash(storage)
        assert n == 1
        assert not list((tmp_kb_root / "trash" / "documents").glob("*.md"))

    def test_g2_keeps_within_30_days(self, storage: Storage, tmp_kb_root: Path):
        from backend.trash import move_doc_to_trash, gc_trash
        _mkdoc(storage, "common-knowledge/fresh.md")
        move_doc_to_trash(storage, "common-knowledge/fresh.md")
        n = gc_trash(storage)
        assert n == 0
        assert (tmp_kb_root / "trash" / "documents").glob("*.md")


# ══════════════════════════════════════════════════════════════
#  Empty-all (user "clear trash" button) vs GC
# ══════════════════════════════════════════════════════════════


class TestEmptyAll:
    def test_empty_all_clears_fresh_items(self, storage: Storage,
                                          tmp_kb_root: Path):
        """empty_trash removes even <30-day fresh items (unlike gc_trash)."""
        from backend.trash import move_doc_to_trash, empty_trash
        _mkdoc(storage, "common-knowledge/fresh.md")
        move_doc_to_trash(storage, "common-knowledge/fresh.md")
        assert (tmp_kb_root / "trash" / "documents").glob("*.md")
        n = empty_trash(storage)
        assert n == 1
        assert not list((tmp_kb_root / "trash" / "documents").glob("*.md"))

    def test_empty_all_clears_projects_too(self, storage: Storage,
                                           tmp_kb_root: Path):
        """empty_trash removes trashed projects (directories) as well."""
        from backend.trash import move_project_to_trash, empty_trash
        from pathlib import Path as P
        _mkdoc(storage, "projects/P/common-knowledge/x.md")
        move_project_to_trash(storage, "projects/P")
        assert (tmp_kb_root / "trash" / "projects").exists()
        n = empty_trash(storage)
        assert n == 1
        assert not list((tmp_kb_root / "trash" / "projects").glob("*"))


# ══════════════════════════════════════════════════════════════
#  Pagination
# ══════════════════════════════════════════════════════════════


class TestTrashPagination:
    def test_page_default_limit_50(self, client_factory):
        """GET /api/trash defaults to limit=50 and reports total/has_more."""
        client, storage, tmp = client_factory
        from backend.trash import move_doc_to_trash
        # 120 fresh items in trash
        for i in range(120):
            _mkdoc(storage, f"common-knowledge/pg{i}.md")
            move_doc_to_trash(storage, f"common-knowledge/pg{i}.md")
        r = client.get("/api/trash")
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) == 50
        assert data["total"] == 120
        assert data["has_more"] is True

    def test_page_offset_limit(self, client_factory):
        """offset/limit slice correctly."""
        client, storage, tmp = client_factory
        from backend.trash import move_doc_to_trash
        for i in range(10):
            _mkdoc(storage, f"common-knowledge/pg{i}.md")
            move_doc_to_trash(storage, f"common-knowledge/pg{i}.md")
        r = client.get("/api/trash?offset=0&limit=4")
        data = r.json()
        assert len(data["items"]) == 4
        assert data["total"] == 10
        assert data["has_more"] is True
        r2 = client.get("/api/trash?offset=8&limit=4")
        data2 = r2.json()
        assert len(data2["items"]) == 2
        assert data2["has_more"] is False


# ══════════════════════════════════════════════════════════════
#  Precise delete (delete_trash_items / /api/trash/empty body)
# ══════════════════════════════════════════════════════════════


class TestDeleteTrashItems:
    def _mk_and_trash(self, storage: Storage, n: int):
        from backend.trash import move_doc_to_trash
        paths = []
        for i in range(n):
            p = f"common-knowledge/d{i}.md"
            _mkdoc(storage, p)
            move_doc_to_trash(storage, p)
            paths.append(p)
        return paths

    def test_single_doc_precise_delete(self, storage: Storage, tmp_kb_root: Path):
        """Deleting one trash doc removes only that item."""
        from backend.trash import move_doc_to_trash, delete_trash_items, list_trash
        p = "common-knowledge/a.md"
        _mkdoc(storage, p)
        tp = move_doc_to_trash(storage, p)
        # another item stays
        _mkdoc(storage, "common-knowledge/b.md")
        move_doc_to_trash(storage, "common-knowledge/b.md")
        n = delete_trash_items(storage, [tp])
        assert n == 1
        remaining = list_trash(storage)
        assert len(remaining) == 1
        assert remaining[0]["original_path"] == "common-knowledge/b.md"
        assert not (tmp_kb_root / tp).exists()

    def test_project_rmtree(self, storage: Storage, tmp_kb_root: Path):
        """Deleting a trashed project removes its whole tree."""
        from backend.trash import move_project_to_trash, delete_trash_items
        _mkdoc(storage, "projects/P/common-knowledge/x.md")
        storage.write_readme("projects/P", {}, dump_frontmatter(
            {"id": "P", "name": "P", "summary": "p"}, "# P"))
        tp = move_project_to_trash(storage, "projects/P")
        n = delete_trash_items(storage, [tp])
        assert n == 1
        assert not (tmp_kb_root / tp).exists()

    def test_mixed_existing_and_missing(self, storage: Storage):
        """Existing deleted, non-existent skipped; count = existing only."""
        from backend.trash import move_doc_to_trash, delete_trash_items
        _mkdoc(storage, "common-knowledge/a.md")
        tp = move_doc_to_trash(storage, "common-knowledge/a.md")
        n = delete_trash_items(storage, [tp, "trash/documents/ghost.md"])
        assert n == 1

    def test_illegal_path_rejected(self, storage: Storage):
        """Traversal / absolute / wrong-prefix paths raise ValueError."""
        from backend.trash import delete_trash_items
        for bad in ["../evil", "/etc/passwd", "common-knowledge/x.md",
                    "trash/other/x.md", "trash/documents/../../x"]:
            with pytest.raises(ValueError):
                delete_trash_items(storage, [bad])

    def test_backward_compat_no_body_gc(self, client_factory):
        """POST /api/trash/empty (no body) → GC: fresh items NOT purged."""
        client, storage, tmp = client_factory
        from backend.trash import move_doc_to_trash
        _mkdoc(storage, "common-knowledge/fresh.md")
        move_doc_to_trash(storage, "common-knowledge/fresh.md")
        r = client.post("/api/trash/empty")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "removed": 0}  # fresh kept by GC
        from backend.trash import list_trash
        assert len(list_trash(storage)) == 1

    def test_backward_compat_all_true(self, client_factory):
        """POST /api/trash/empty?all=true → clears everything."""
        client, storage, tmp = client_factory
        from backend.trash import move_doc_to_trash
        _mkdoc(storage, "common-knowledge/fresh.md")
        move_doc_to_trash(storage, "common-knowledge/fresh.md")
        r = client.post("/api/trash/empty?all=true")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "removed": 1}
        from backend.trash import list_trash
        assert len(list_trash(storage)) == 0

    def test_api_body_precise_delete(self, client_factory):
        """POST /api/trash/empty with body trash_paths → 200 + removed."""
        client, storage, tmp = client_factory
        from backend.trash import move_doc_to_trash, list_trash
        _mkdoc(storage, "common-knowledge/a.md")
        tp_a = move_doc_to_trash(storage, "common-knowledge/a.md")
        _mkdoc(storage, "common-knowledge/b.md")
        move_doc_to_trash(storage, "common-knowledge/b.md")
        r = client.post("/api/trash/empty", json={"trash_paths": [tp_a]})
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "removed": 1}
        remaining = list_trash(storage)
        assert len(remaining) == 1
        assert remaining[0]["original_path"] == "common-knowledge/b.md"

    def test_api_body_rejects_bad_path(self, client_factory):
        """API with an illegal trash_path → 400 ValueError."""
        client, storage, tmp = client_factory
        r = client.post("/api/trash/empty", json={"trash_paths": ["../evil"]})
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════
#  Ref status (dead-link check)
# ══════════════════════════════════════════════════════════════


class TestRefStatus:
    def _ref_status(self, storage: Storage, path: str) -> str:
        from backend.trash import ref_status
        return ref_status(storage, path)

    def test_c1_normal(self, app, storage: Storage):
        _mkdoc(storage, "common-knowledge/x.md")
        assert self._ref_status(storage, "common-knowledge/x.md") == "normal"

    def test_c2_in_trash_document(self, app, storage: Storage, tmp_kb_root: Path):
        _mkdoc(storage, "common-knowledge/x.md")
        _del_doc(app, "common-knowledge/x.md")
        assert self._ref_status(storage, "common-knowledge/x.md") == "in_trash"

    def test_c3_in_trash_project(self, app, storage: Storage, tmp_kb_root: Path):
        (tmp_kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True)
        storage.write_readme("projects/P", {}, dump_frontmatter(
            {"id": "P", "name": "P", "summary": "p"}, "# P"))
        _del_proj(app, "projects/P")
        # A doc path inside the trashed project is in_trash
        assert self._ref_status(storage, "projects/P/common-knowledge/doc.md") == "in_trash"
        assert self._ref_status(storage, "projects/P") == "in_trash"

    def test_c4_dead(self, storage: Storage):
        assert self._ref_status(storage, "common-knowledge/nope.md") == "dead"

    def test_ref_status_strips_section(self, storage: Storage, tmp_kb_root: Path):
        """ref:path::section — section suffix must not break status."""
        _mkdoc(storage, "common-knowledge/x.md")
        from backend.trash import ref_status
        assert ref_status(storage, "common-knowledge/x.md::标题") == "normal"
