"""Tests for backend/mcp_server.py — MCP tool functions.

Tools are async (FastMCP convention).  We call them via ``asyncio.run()``
in synchronous tests.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.mcp_server import create_mcp_app
from backend.storage import Storage


@pytest.fixture
def storage_with_data(storage: Storage, tmp_kb_root: Path) -> Storage:
    """A storage with a minimal KB tree (root readme + one doc)."""
    from backend.readme_generator import ReadmeGenerator
    tmpl = tmp_kb_root / "_templates" / "readme.md"
    if not tmpl.parent.exists():
        tmpl.parent.mkdir(parents=True)
        # fallback to shipped template
        shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
        tmpl.write_text(shipped.read_text())

    gen = ReadmeGenerator(storage=storage, template_path=tmpl)
    gen.rebuild("", name="TestKB", summary="test")

    storage.write_document("common-knowledge/doc1.md",
                           {"type": "knowledge", "summary": "doc summary"},
                           "# Doc body",
                           auto_id=False)
    gen.rebuild("")  # update root readme with new doc entry
    return storage


@pytest.fixture
def app(storage_with_data: Storage):
    """FastMCP app bound to the test KB."""
    return create_mcp_app(storage_with_data)


# ══════════════════════════════════════════════════════════════

def _tool_text(result) -> str:
    """Extract text from FastMCP ``call_tool`` return value.

    ``call_tool`` returns ``(list[TextContent], dict)``.
    ``result[0]`` is the list of ``TextContent`` objects.
    """
    return result[0][0].text


class TestReadReadme:
    def test_read_root(self, app) -> None:
        result = asyncio.run(app.call_tool("nav__read_readme", {"project_rel": ""}))
        text = _tool_text(result)
        assert "TestKB" in text       # from frontmatter
        assert "## 结构说明" in text   # from body

    def test_read_nonexistent_returns_error(self, app) -> None:
        with pytest.raises(Exception):
            asyncio.run(app.call_tool("nav__read_readme", {"project_rel": "projects/nope"}))


class TestListDir:
    def test_list_root(self, app) -> None:
        result = asyncio.run(app.call_tool("nav__list_dir", {"project_rel": ""}))
        text = _tool_text(result)
        assert "common-knowledge" in text

    def test_list_empty_dir(self, app) -> None:
        result = asyncio.run(app.call_tool("nav__list_dir", {"project_rel": "projects"}))
        text = _tool_text(result)
        assert "空目录" in text


class TestGetDocument:
    def test_get_existing(self, app) -> None:
        result = asyncio.run(app.call_tool("nav__get_document", {"path": "common-knowledge/doc1.md"}))
        text = _tool_text(result)
        assert "Doc body" in text
        assert "doc summary" in text  # from frontmatter

    def test_get_nonexistent_returns_error(self, app) -> None:
        with pytest.raises(Exception):
            asyncio.run(app.call_tool("nav__get_document", {"path": "no-such-file.md"}))


class TestGetDocumentWithRefs:
    def test_no_refs(self, app, storage: Storage) -> None:
        storage.write_document(
            "main.md",
            {"summary": "main", "type": "knowledge"},
            "# Main body", auto_id=False,
        )
        result = asyncio.run(app.call_tool(
            "nav__get_document_with_refs", {"path": "main.md"}))
        text = _tool_text(result)
        assert "Main body" in text
        assert "参考文献" not in text

    def test_inline_ref_whole_doc(self, app, storage: Storage) -> None:
        storage.write_document(
            "ref.md",
            {"summary": "ref doc", "type": "knowledge"},
            "# Referenced", auto_id=False,
        )
        storage.write_document(
            "main.md",
            {"summary": "main", "type": "knowledge"},
            "详见[文档](ref:ref.md)。", auto_id=False,
        )
        result = asyncio.run(app.call_tool(
            "nav__get_document_with_refs", {"path": "main.md"}))
        text = _tool_text(result)
        assert "参考文献" in text
        assert "Referenced" in text

    def test_inline_ref_with_section(self, app, storage: Storage) -> None:
        storage.write_document(
            "ref.md",
            {"summary": "ref doc", "type": "knowledge"},
            "# Other\n\nother content\n\n## Section A\n\nsection body\n\n## Section B\n\nb body",
            auto_id=False,
        )
        storage.write_document(
            "main.md",
            {"summary": "main", "type": "knowledge"},
            "参考[具体段落](ref:ref.md::Section A)。", auto_id=False,
        )
        result = asyncio.run(app.call_tool(
            "nav__get_document_with_refs", {"path": "main.md"}))
        text = _tool_text(result)
        assert "section body" in text
        assert "other content" not in text  # not in extracted section

    def test_broken_ref(self, app, storage: Storage) -> None:
        storage.write_document(
            "main.md",
            {"summary": "main", "type": "knowledge"},
            "见[不存在](ref:nope.md)。", auto_id=False,
        )
        result = asyncio.run(app.call_tool(
            "nav__get_document_with_refs", {"path": "main.md"}))
        text = _tool_text(result)
        assert "不存在" in text

    def test_no_circular(self, app, storage: Storage) -> None:
        storage.write_document(
            "a.md",
            {"summary": "a", "type": "knowledge"},
            "见[b](ref:b.md)。", auto_id=False,
        )
        storage.write_document(
            "b.md",
            {"summary": "b", "type": "knowledge"},
            "见[a](ref:a.md)。", auto_id=False,
        )
        result = asyncio.run(app.call_tool(
            "nav__get_document_with_refs", {"path": "a.md"}))
        text = _tool_text(result)
        assert "[1]" in text
        assert text.count("[1]") == 1

    def test_refs_fallback(self, app, storage: Storage,
                           tmp_kb_root: Path) -> None:
        """_refs/ is checked before original path."""
        # Create a project with a doc that refs an external file
        proj_dir = tmp_kb_root / "projects" / "TestRefs"
        proj_dir.mkdir(parents=True)
        (proj_dir / "common-knowledge").mkdir()

        # Write a doc that refs external content
        storage.write_document(
            "projects/TestRefs/common-knowledge/main.md",
            {"summary": "main", "type": "knowledge"},
            "详见[外部](ref:common-knowledge/external.md)。",
            auto_id=False,
        )

        # External file doesn't exist at original path, but exists in _refs/
        refs_dir = proj_dir / "_refs" / "common-knowledge"
        refs_dir.mkdir(parents=True)
        (refs_dir / "external.md").write_text(
            "---\nsummary: external\n---\n\n# External content",
            encoding="utf-8",
        )

        result = asyncio.run(app.call_tool(
            "nav__get_document_with_refs",
            {"path": "projects/TestRefs/common-knowledge/main.md"}))
        text = _tool_text(result)
        assert "External content" in text

    def test_includes_external_links(self, app, storage: Storage) -> None:
        storage.write_document(
            "main.md",
            {"summary": "main", "type": "knowledge"},
            "内链[文档](ref:ref.md) 外链[Google](https://google.com)",
            auto_id=False,
        )
        storage.write_document(
            "ref.md",
            {"summary": "ref", "type": "knowledge"},
            "# Ref doc", auto_id=False,
        )
        result = asyncio.run(app.call_tool(
            "nav__get_document_with_refs", {"path": "main.md"}))
        text = _tool_text(result)
        assert "内链" in text
        assert "Google" in text
        assert "https://google.com" in text
        assert "Ref doc" in text  # ref resolved
        assert "参考文献" in text
