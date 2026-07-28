"""Tests for MCP maintenance tools (validate_doc, read_diff, check_integrity)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.git_manager import GitManager
from backend.mcp_server import create_mcp_app, acquire_lock
from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage


@pytest.fixture
def app_with_git(storage: Storage, tmp_kb_root: Path):
    """App with gen + git enabled."""
    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
    template.write_text(shipped.read_text(), encoding="utf-8")

    gen = ReadmeGenerator(storage=storage, template_path=template)
    gen.rebuild("", name="TestKB", summary="test")

    acquire_lock(storage)  # create lock for write tools
    gm = GitManager(tmp_kb_root)
    gm.init()
    gm.commit("init")

    return create_mcp_app(storage, gen=gen, gm=gm)


def _tool_text(result) -> str:
    return result[0][0].text


class TestValidateDoc:
    def test_valid_doc(self, app_with_git, storage: Storage) -> None:
        storage.write_document("common-knowledge/good.md",
                               {"type": "knowledge", "summary": "ok"},
                               "# good")
        result = asyncio.run(app_with_git.call_tool(
            "maint__validate_doc", {"path": "common-knowledge/good.md"}))
        text = _tool_text(result)
        assert "✓" in text

    def test_missing_summary(self, app_with_git, storage: Storage) -> None:
        storage.write_document("common-knowledge/bad.md",
                               {"type": "knowledge"},
                               "# bad")
        result = asyncio.run(app_with_git.call_tool(
            "maint__validate_doc", {"path": "common-knowledge/bad.md"}))
        text = _tool_text(result)
        assert "⚠" in text
        assert "summary" in text

    def test_nonexistent(self, app_with_git) -> None:
        result = asyncio.run(app_with_git.call_tool(
            "maint__validate_doc", {"path": "common-knowledge/nope.md"}))
        text = _tool_text(result)
        assert "✗" in text

    def test_invalid_format(self, app_with_git) -> None:
        """Path without valid prefix should also return a controlled error."""
        result = asyncio.run(app_with_git.call_tool(
            "maint__validate_doc", {"path": "nope.md"}))
        text = _tool_text(result)
        # The error message contains recovery instructions
        assert "common-knowledge" in text or "projects" in text


class TestReadDiff:
    def test_with_checkpoint(self, app_with_git, storage: Storage,
                             tmp_kb_root: Path) -> None:
        gm = GitManager(tmp_kb_root)
        head = gm.get_head_hash()
        gm.write_checkpoint(head, tmp_kb_root / "agent-commit.txt")

        # Make a change
        storage.write_document("common-knowledge/new.md",
                               {"summary": "new"}, "# new")
        gm.commit("add doc")

        result = asyncio.run(app_with_git.call_tool(
            "maint__read_diff", {"from_hash": ""}))
        text = _tool_text(result)
        assert "new" in text or "add doc" in text

    def test_no_checkpoint(self, app_with_git) -> None:
        result = asyncio.run(app_with_git.call_tool(
            "maint__read_diff", {"from_hash": ""}))
        text = _tool_text(result)
        # Should either fail gracefully or show no-checkpoint message
        assert text
