"""Tests for the trash index (方案 C): persistent index + in-process cache.

Covers:
- index generation: delete → index holds ``original_path → trash_path``
- ``ref_status`` three-state correctness (incl. project prefix match)
- index invalidation: restore / empty / gc → classification not misjudged
- fault tolerance: manual delete of ``trash_index.json`` → rebuild fallback
- stat fallback: index hit but disk file gone → ``dead`` (not stale ``in_trash``)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend.mcp_server import create_mcp_app, acquire_lock
from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage, dump_frontmatter
from backend.trash import (
    TRASH_INDEX, _get_trash_index, _invalidate_trash_index,
    _load_trash_index, _index_cache, gc_trash, move_doc_to_trash, ref_status,
)


@pytest.fixture
def app(storage: Storage, tmp_kb_root: Path):
    acquire_lock(storage)
    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
    template.write_text(shipped.read_text(), encoding="utf-8")
    gen = ReadmeGenerator(storage=storage, template_path=template)
    gen.rebuild("", name="TestKB", summary="test kb")
    # Fresh process cache per test — no cross-test contamination.
    _index_cache.clear()
    return create_mcp_app(storage, gen=gen)


def _tool_text(result) -> str:
    return result[0][0].text


def _mkdoc(storage: Storage, path: str, body: str = "# body") -> None:
    storage.write_document(path, {"summary": "s", "maintainer": "Me"},
                           body, auto_id=False)


def _mkproject(storage: Storage, path: str) -> None:
    (storage.kb_root / path / "common-knowledge").mkdir(parents=True)
    storage.write_readme(path, {}, dump_frontmatter(
        {"id": path.split("/")[-1], "name": path.split("/")[-1],
         "summary": "p"}, f"# {path.split('/')[-1]}"))


def _del_doc(app, path: str) -> str:
    return _tool_text(asyncio.run(app.call_tool("write__delete_document", {"path": path})))


def _del_proj(app, proj: str) -> str:
    return _tool_text(asyncio.run(app.call_tool("write__delete_project", {"project_rel": proj})))


def _restore_doc(app, trash_path: str) -> str:
    return _tool_text(asyncio.run(app.call_tool("write__restore_document", {"trash_path": trash_path})))


def _index_file(tmp_kb_root: Path) -> Path:
    return tmp_kb_root / TRASH_INDEX


# ══════════════════════════════════════════════════════════════
#  Index generation
# ══════════════════════════════════════════════════════════════


class TestIndexGeneration:
    def test_delete_doc_adds_index_entry(self, app, storage: Storage,
                                         tmp_kb_root: Path):
        _mkdoc(storage, "common-knowledge/x.md")
        _del_doc(app, "common-knowledge/x.md")
        # The delete invalidated the index → next read lazily rebuilds it.
        index = _get_trash_index(storage)
        assert "common-knowledge/x.md" in index
        entry = index["common-knowledge/x.md"]
        assert entry["type"] == "document"
        assert entry["trash_path"].startswith("trash/documents/")
        # And it was persisted to disk.
        assert _index_file(tmp_kb_root).exists()
        assert ref_status(storage, "common-knowledge/x.md") == "in_trash"

    def test_delete_project_adds_index_entry(self, app, storage: Storage,
                                             tmp_kb_root: Path):
        _mkproject(storage, "projects/P")
        _mkdoc(storage, "projects/P/common-knowledge/doc.md")
        _del_proj(app, "projects/P")
        index = _get_trash_index(storage)
        entry = index.get("projects/P")
        assert entry is not None
        assert entry["type"] == "project"
        assert entry["trash_path"].startswith("trash/projects/")
        # prefix match: a doc path inside the trashed project is in_trash
        assert ref_status(storage, "projects/P/common-knowledge/doc.md") == "in_trash"

    def test_index_cached_in_process(self, app, storage: Storage,
                                     tmp_kb_root: Path):
        """Module-level cache keyed by kb_root avoids re-reads."""
        _mkdoc(storage, "common-knowledge/x.md")
        _del_doc(app, "common-knowledge/x.md")
        _get_trash_index(storage)
        key = str(storage.kb_root)
        assert _index_cache.get(key) is not None
        # A second read hits the cache, not the disk.
        idx = _get_trash_index(storage)
        assert idx is _index_cache[key]


# ══════════════════════════════════════════════════════════════
#  ref_status three-state correctness
# ══════════════════════════════════════════════════════════════


class TestRefStatusThreeState:
    def test_normal(self, app, storage: Storage):
        _mkdoc(storage, "common-knowledge/x.md")
        assert ref_status(storage, "common-knowledge/x.md") == "normal"

    def test_in_trash_doc(self, app, storage: Storage):
        _mkdoc(storage, "common-knowledge/x.md")
        _del_doc(app, "common-knowledge/x.md")
        assert ref_status(storage, "common-knowledge/x.md") == "in_trash"

    def test_in_trash_project_prefix(self, app, storage: Storage,
                                     tmp_kb_root: Path):
        _mkproject(storage, "projects/P")
        _del_proj(app, "projects/P")
        assert ref_status(storage, "projects/P") == "in_trash"
        assert ref_status(storage, "projects/P/common-knowledge/doc.md") == "in_trash"
        # A sibling project under a different name must NOT match.
        assert ref_status(storage, "projects/P2/common-knowledge/doc.md") == "dead"

    def test_dead(self, storage: Storage):
        assert ref_status(storage, "common-knowledge/nope.md") == "dead"


# ══════════════════════════════════════════════════════════════
#  Index invalidation on write operations
# ══════════════════════════════════════════════════════════════


class TestInvalidation:
    def test_restore_invalidates_index(self, app, storage: Storage,
                                       tmp_kb_root: Path):
        _mkdoc(storage, "common-knowledge/x.md")
        _del_doc(app, "common-knowledge/x.md")
        assert ref_status(storage, "common-knowledge/x.md") == "in_trash"
        # Restore → index invalidated → next ref_status rebuilds → normal.
        trash = list((tmp_kb_root / "trash" / "documents").glob("*.md"))[0].name
        _restore_doc(app, f"trash/documents/{trash}")
        assert ref_status(storage, "common-knowledge/x.md") == "normal"

    def test_restore_project_then_doc(self, app, storage: Storage,
                                      tmp_kb_root: Path):
        _mkproject(storage, "projects/P")
        _mkdoc(storage, "projects/P/common-knowledge/x.md")
        _del_doc(app, "projects/P/common-knowledge/x.md")
        _del_proj(app, "projects/P")
        assert ref_status(storage, "projects/P/common-knowledge/x.md") == "in_trash"
        # Restore project first.
        _restore_proj(app, "trash/projects/P")
        assert ref_status(storage, "projects/P") == "normal"
        # Now restore the doc.
        trash = list((tmp_kb_root / "trash" / "documents").glob("*.md"))[0].name
        _restore_doc(app, f"trash/documents/{trash}")
        assert ref_status(storage, "projects/P/common-knowledge/x.md") == "normal"

    def test_gc_invalidates_index(self, storage: Storage, tmp_kb_root: Path):
        _mkdoc(storage, "common-knowledge/old.md")
        move_doc_to_trash(storage, "common-knowledge/old.md")
        assert ref_status(storage, "common-knowledge/old.md") == "in_trash"
        # Backdate deleted_at 31 days → GC purges.
        d = list((tmp_kb_root / "trash" / "documents").glob("*.md"))[0]
        meta, body = storage.read_document(f"trash/documents/{d.name}")
        meta["deleted_at"] = (datetime.now() - timedelta(days=31)).isoformat()
        storage.write_document(f"trash/documents/{d.name}", meta, body, auto_id=False)
        n = gc_trash(storage)
        assert n == 1
        # Index invalidated → next read rebuilds → old path now dead.
        assert ref_status(storage, "common-knowledge/old.md") == "dead"


# ══════════════════════════════════════════════════════════════
#  Fault tolerance
# ══════════════════════════════════════════════════════════════


class TestFaultTolerance:
    def test_manual_delete_of_index_rebuilds(self, app, storage: Storage,
                                             tmp_kb_root: Path):
        """Manually deleting trash_index.json must not break ref_status."""
        _mkdoc(storage, "common-knowledge/x.md")
        _del_doc(app, "common-knowledge/x.md")
        assert ref_status(storage, "common-knowledge/x.md") == "in_trash"
        assert _index_file(tmp_kb_root).exists()
        # Simulate an external/manual deletion of the index file + cache drop.
        _invalidate_trash_index(storage)
        _index_file(tmp_kb_root).unlink(missing_ok=True)
        assert not _index_file(tmp_kb_root).exists()
        # ref_status still correct — lazy rebuild from list_trash.
        assert ref_status(storage, "common-knowledge/x.md") == "in_trash"
        assert _index_file(tmp_kb_root).exists()  # index rebuilt + persisted

    def test_corrupt_index_rebuilds(self, storage: Storage, tmp_kb_root: Path):
        """A corrupt JSON index triggers a rebuild, not a crash."""
        _mkdoc(storage, "common-knowledge/x.md")
        move_doc_to_trash(storage, "common-knowledge/x.md")
        _index_file(tmp_kb_root).write_text("{ not valid json !!", encoding="utf-8")
        # _load returns None → _get rebuilds.
        assert _load_trash_index(storage) is None
        assert ref_status(storage, "common-knowledge/x.md") == "in_trash"
        assert _index_file(tmp_kb_root).exists()


# ══════════════════════════════════════════════════════════════
#  Stat fallback: index hit but disk gone
# ══════════════════════════════════════════════════════════════


class TestStatFallback:
    def test_index_hit_but_disk_file_gone_is_dead(self, storage: Storage,
                                                  tmp_kb_root: Path):
        """Index claims in_trash but the trash file was manually removed → dead."""
        _mkdoc(storage, "common-knowledge/x.md")
        move_doc_to_trash(storage, "common-knowledge/x.md")
        assert ref_status(storage, "common-knowledge/x.md") == "in_trash"
        # Now manually delete the actual trash file, leaving the index stale.
        trash = list((tmp_kb_root / "trash" / "documents").glob("*.md"))[0]
        trash.unlink()
        # Direct-hit branch: index hit but stat fallback fails → dead.
        assert ref_status(storage, "common-knowledge/x.md") == "dead"

    def test_project_prefix_but_disk_gone_is_dead(self, storage: Storage,
                                                  tmp_kb_root: Path):
        """Index says a project is in_trash but the dir was removed → dead."""
        import shutil
        from backend.trash import move_project_to_trash
        _mkproject(storage, "projects/Q")
        move_project_to_trash(storage, "projects/Q")
        assert ref_status(storage, "projects/Q") == "in_trash"
        # Manually remove the trashed project dir, leaving the index stale.
        shutil.rmtree(tmp_kb_root / "trash" / "projects" / "Q", ignore_errors=True)
        # Project prefix branch: index hit but stat fallback fails → dead.
        assert ref_status(storage, "projects/Q") == "dead"


def _restore_proj(app, trash_path: str) -> str:
    return _tool_text(asyncio.run(app.call_tool("write__restore_project", {"trash_path": trash_path})))
