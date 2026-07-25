"""Tests for backend/storage.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.storage import (
    parse_frontmatter,
    dump_frontmatter,
    generate_doc_id,
    DirEntry,
    DocEntry,
    ProjectEntry,
    Storage,
)


# ══════════════════════════════════════════════════════════════
#  Frontmatter (stateless helpers)
# ══════════════════════════════════════════════════════════════

class TestParseFrontmatter:
    def test_with_frontmatter(self) -> None:
        text = "---\nkey: value\n---\n\nbody text"
        meta, body = parse_frontmatter(text)
        assert meta == {"key": "value"}
        assert body == "body text"

    def test_no_frontmatter(self) -> None:
        meta, body = parse_frontmatter("just body")
        assert meta == {}
        assert body == "just body"

    def test_empty_body(self) -> None:
        meta, body = parse_frontmatter("---\nk: v\n---\n")
        assert meta == {"k": "v"}
        assert body == ""

    def test_malformed_yaml_returns_empty(self) -> None:
        text = "---\n: invalid yaml\n---\nbody"
        meta, body = parse_frontmatter(text)
        # yaml.safe_load returns a string on this input, not a dict
        assert isinstance(meta, dict)
        assert meta == {}
        assert body == "body"

    def test_multiline_yaml(self) -> None:
        text = "---\nk1: v1\nk2: v2\n---\n\nbody"
        meta, body = parse_frontmatter(text)
        assert meta == {"k1": "v1", "k2": "v2"}
        assert body == "body"


class TestDumpFrontmatter:
    def test_roundtrip(self) -> None:
        original_meta = {"k1": "v1", "k2": "v2"}
        original_body = "some content"
        dumped = dump_frontmatter(original_meta, original_body)
        meta, body = parse_frontmatter(dumped)
        assert meta == original_meta
        assert body == original_body

    def test_empty_meta(self) -> None:
        dumped = dump_frontmatter({}, "body")
        meta, body = parse_frontmatter(dumped)
        assert meta == {}
        assert body == "body"


class TestGenerateDocId:
    def test_format(self) -> None:
        doc_id = generate_doc_id()
        assert doc_id.startswith("doc_")
        parts = doc_id.split("_")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # yyyymmdd
        assert len(parts[2]) == 6  # hex

    def test_unique(self) -> None:
        ids = {generate_doc_id() for _ in range(100)}
        assert len(ids) == 100


# ══════════════════════════════════════════════════════════════
#  Storage (needs a temp KB root)
# ══════════════════════════════════════════════════════════════

class TestStorageWriteRead:
    def test_write_and_read(self, storage: Storage, tmp_kb_root: Path) -> None:
        meta = {"type": "knowledge", "summary": "test doc"}
        body = "# Hello\n\nworld"
        written = storage.write_document("common-knowledge/test.md", meta, body)
        assert "id" in written  # auto-generated
        assert written["summary"] == "test doc"

        read_meta, read_body = storage.read_document("common-knowledge/test.md")
        assert read_meta["id"] == written["id"]
        assert read_meta["summary"] == "test doc"
        assert "# Hello" in read_body

    def test_write_without_auto_id(self, storage: Storage) -> None:
        meta = {"id": "custom_id_001"}
        written = storage.write_document("test.md", meta, "body", auto_id=False)
        assert written["id"] == "custom_id_001"

    def test_write_adds_updated(self, storage: Storage) -> None:
        meta = {"type": "knowledge"}
        written = storage.write_document("test.md", meta, "body")
        assert "updated" in written

    def test_read_non_existent_raises(self, storage: Storage) -> None:
        with pytest.raises(FileNotFoundError):
            storage.read_document("nonexistent.md")


class TestStorageListChildren:
    def test_empty_root(self, storage: Storage, tmp_kb_root: Path) -> None:
        entries = storage.list_children("")
        assert entries == []

    def test_lists_dirs_and_files(self, storage: Storage, tmp_kb_root: Path) -> None:
        (tmp_kb_root / "projects").mkdir()
        (tmp_kb_root / "a_file.md").write_text("# file")
        entries = storage.list_children("")
        names = [e.name for e in entries]
        assert "a_file.md" in names
        assert "projects" in names

    def test_hides_dotfiles(self, storage: Storage, tmp_kb_root: Path) -> None:
        (tmp_kb_root / ".git").mkdir()
        (tmp_kb_root / "visible.md").write_text("content")
        entries = storage.list_children("")
        names = [e.name for e in entries]
        assert ".git" not in names
        assert "visible.md" in names


class TestStorageGetEntries:
    def test_get_doc_entries(self, storage: Storage, tmp_kb_root: Path) -> None:
        projects = tmp_kb_root / "projects" / "testproj"
        (projects / "common-knowledge").mkdir(parents=True)
        doc = projects / "common-knowledge" / "doc1.md"
        doc.write_text(
            "---\nsummary: test summary\nupdated: 2026-07-23\n---\n\nbody"
        )
        entries = storage.get_doc_entries("projects/testproj")
        assert len(entries) == 1
        assert entries[0].summary == "test summary"

    def test_get_project_entries(self, storage: Storage, tmp_kb_root: Path) -> None:
        projects = tmp_kb_root / "projects" / "parent"
        (projects / "projects" / "child").mkdir(parents=True)
        child_readme = projects / "projects" / "child" / "readme.md"
        child_readme.write_text(
            "---\nid: child\nname: ChildProj\nsummary: child summary\n---\n\nbody"
        )
        entries = storage.get_project_entries("projects/parent")
        assert len(entries) == 1
        assert entries[0].name == "ChildProj"
        assert entries[0].summary == "child summary"

    def test_get_archive_entries(self, storage: Storage, tmp_kb_root: Path) -> None:
        arch = tmp_kb_root / "archive" / "oldproj"
        arch.mkdir(parents=True)
        (arch / "readme.md").write_text(
            "---\nid: old\nname: OldProj\nsummary: old summary\n---\n\nbody"
        )
        entries = storage.get_archive_entries("")
        assert len(entries) == 1
        assert entries[0].name == "OldProj"


class TestStorageFrontmatterRoundtrip:
    def test_readme_meta(self, storage: Storage, tmp_kb_root: Path) -> None:
        proj = tmp_kb_root / "projects" / "p1"
        proj.mkdir(parents=True)
        (proj / "readme.md").write_text(
            "---\nid: p1\nname: Project1\nsummary: p1 summary\nstatus: active\n---\n\nbody"
        )
        rm = storage.get_readme_meta("projects/p1")
        assert rm.id == "p1"
        assert rm.name == "Project1"
        assert rm.summary == "p1 summary"
        assert rm.status == "active"


class TestDirEntryDataClass:
    def test_create(self) -> None:
        e = DirEntry(name="foo.md", is_dir=False, modified="2026-07-23")
        assert e.name == "foo.md"
        assert not e.is_dir

    def test_create_doc_entry(self) -> None:
        e = DocEntry(path="ck/test.md", summary="s", updated="2026-07-23")
        assert e.path == "ck/test.md"

    def test_create_project_entry(self) -> None:
        e = ProjectEntry(path="projects/p1/", name="P1", summary="s")
        assert e.name == "P1"
