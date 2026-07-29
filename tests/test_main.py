"""Tests for backend/main.py — REST API and shared utilities."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.storage import Storage


# ══════════════════════════════════════════════════════════════
#  _extract_all_refs — pure function tests
# ══════════════════════════════════════════════════════════════


def _test_extract(body: str) -> list[tuple[str, str, str]]:
    from backend.main import _extract_all_refs
    return _extract_all_refs(body)


class TestExtractAllRefs:
    """Unit tests for the shared ref + external link parser."""

    def test_no_links(self):
        assert _test_extract("纯文本") == []

    def test_only_ref_links(self):
        body = "[doc](ref:common-knowledge/doc.md)"
        result = _test_extract(body)
        assert len(result) == 1
        rtype, rpath, title = result[0]
        assert rtype == "ref"
        assert rpath == "common-knowledge/doc.md"
        # Without ::section, third element is empty string
        assert title == ""

    def test_ref_with_section(self):
        body = "[标题](ref:doc.md::介绍)"
        result = _test_extract(body)
        assert len(result) == 1
        assert result[0] == ("ref", "doc.md", "介绍")

    def test_external_link(self):
        body = "[Google](https://google.com)"
        result = _test_extract(body)
        assert len(result) == 1
        assert result[0][0] == "external"
        assert result[0][1] == "https://google.com"
        assert result[0][2] == "Google"

    def test_https_and_http_links(self):
        body = "[A](http://a.com) [B](https://b.com)"
        result = _test_extract(body)
        assert len(result) == 2
        assert all(r[0] == "external" for r in result)

    def test_mixed_refs_and_external(self):
        body = "[内部](ref:doc.md) [外部](https://example.com)"
        result = _test_extract(body)
        assert len(result) == 2
        rtype, rpath, title = result[0]
        assert rtype == "ref" and rpath == "doc.md" and title == ""
        assert result[1] == ("external", "https://example.com", "外部")

    def test_skip_code_block(self):
        """URLs inside ``` fenced code block should be ignored."""
        body = (
            "正文内容\n\n"
            "```\n"
            "[不应解析](https://ignored.com)\n"
            "```\n\n"
            "[应解析](ref:real.md)"
        )
        result = _test_extract(body)
        assert len(result) == 1
        assert result[0][1] == "real.md"

    def test_skip_inline_code(self):
        """URLs inside `inline code` should be ignored."""
        body = "看链接 `[不要解析](https://ignored.com)` 结束 [要解析](ref:real.md)"
        result = _test_extract(body)
        assert len(result) == 1
        assert result[0][1] == "real.md"

    def test_skip_image(self):
        """Image links ![alt](url) should not be treated as refs."""
        body = "![图片](https://image.com/logo.png) [文本链接](ref:doc.md)"
        result = _test_extract(body)
        assert len(result) == 1
        assert result[0][1] == "doc.md"

    def test_empty_link_text(self):
        """[ ](url) with empty text should be skipped."""
        body = "[](ref:nope.md)"
        result = _test_extract(body)
        assert result == []

    def test_link_with_parentheses_in_url(self):
        """URL containing parentheses should be fully captured."""
        body = "[Wiki](https://en.wikipedia.org/wiki/foo_(bar))"
        result = _test_extract(body)
        assert len(result) == 1
        assert result[0][1] == "https://en.wikipedia.org/wiki/foo_(bar)"

    def test_url_with_multiple_parentheses(self):
        """URL with multiple nested parentheses pairs."""
        body = "[Func](https://example.com/f(a(b)c)d)"
        result = _test_extract(body)
        assert len(result) == 1
        assert result[0][1] == "https://example.com/f(a(b)c)d"

    def test_ref_dedup(self):
        """Deduplication is the caller's responsibility - parser returns all."""
        body = "[A](ref:doc.md)[B](ref:doc.md)"
        result = _test_extract(body)
        assert len(result) == 2  # parser returns all, caller deduplicates


# ══════════════════════════════════════════════════════════════
#  REST API — /api/document/{path}/refs
# ══════════════════════════════════════════════════════════════


def _create_test_doc(storage: Storage, path: str, body: str) -> None:
    storage.write_document(path, {"summary": "test"}, body, auto_id=True)


@pytest.fixture
def client(tmp_kb_root: Path):
    """FastAPI test client."""
    from fastapi.testclient import TestClient
    from backend.main import app
    # Override the storage in the API
    from backend.main import get_storage as _orig_get_storage
    from backend.readme_generator import ReadmeGenerator

    storage = Storage(kb_root=tmp_kb_root)

    def _test_storage():
        template = tmp_kb_root / "_templates" / "readme.md"
        if not template.exists():
            template.parent.mkdir(parents=True, exist_ok=True)
            template.write_text("# {name}\n\n{summary}")
        gen = ReadmeGenerator(storage=storage, template_path=template)
        return storage, gen

    import backend.main
    backend.main.get_storage = _test_storage
    yield TestClient(app)
    backend.main.get_storage = _orig_get_storage


class TestApiDocumentRefs:
    """Test the /api/document/{path}/refs endpoint."""

    def test_refs_include_external_links(self, client, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        body = (
            "正文\n\n"
            "[内部引用](ref:common-knowledge/other.md)\n"
            "[外部链接](https://example.com)"
        )
        _create_test_doc(storage, "common-knowledge/main.md", body)
        _create_test_doc(storage, "common-knowledge/other.md", "other content")

        resp = client.get("/api/document/common-knowledge/main.md/refs")
        assert resp.status_code == 200
        data = resp.json()
        assert "refs" in data

        types = {r["type"] for r in data["refs"]}
        assert "ref" in types
        assert "external" in types

        ext = [r for r in data["refs"] if r["type"] == "external"]
        assert len(ext) == 1
        assert ext[0]["path"] == "https://example.com"
        assert ext[0]["resolved"] is True

    def test_refs_skip_inline_code_links(self, client, tmp_kb_root: Path):
        """Links inside inline code should not appear in refs."""
        storage = Storage(kb_root=tmp_kb_root)
        body = "`[内部](ref:doc.md)` `[外部](https://example.com)` [真实](ref:real.md)"
        _create_test_doc(storage, "main.md", body)
        _create_test_doc(storage, "real.md", "real content")

        resp = client.get("/api/document/main.md/refs")
        assert resp.status_code == 200
        data = resp.json()
        paths = {r["path"] for r in data["refs"]}
        assert "real.md" in paths
        assert "doc.md" not in paths
        assert "https://example.com" not in paths

    def test_refs_dedup_external_links(self, client, tmp_kb_root: Path):
        """Same external link used twice should appear only once."""
        storage = Storage(kb_root=tmp_kb_root)
        body = "[A](https://example.com) [B](https://example.com)"
        _create_test_doc(storage, "doc.md", body)

        resp = client.get("/api/document/doc.md/refs")
        data = resp.json()
        ext = [r for r in data["refs"] if r["type"] == "external"]
        assert len(ext) == 1

    def test_no_refs(self, client, tmp_kb_root: Path):
        """Document with no links should return empty refs."""
        storage = Storage(kb_root=tmp_kb_root)
        _create_test_doc(storage, "plain.md", "Just text, no links.")

        resp = client.get("/api/document/plain.md/refs")
        data = resp.json()
        assert data["refs"] == []

    def test_404(self, client):
        resp = client.get("/api/document/nope.md/refs")
        assert resp.status_code == 404


class TestApiExport:
    """Test the /api/export endpoint."""

    def test_export_single_project(self, client, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        (tmp_kb_root / "projects" / "TestProj" / "common-knowledge").mkdir(parents=True)
        from backend.storage import dump_frontmatter
        storage.write_readme("projects/TestProj", {}, dump_frontmatter(
            {"id": "tp", "name": "TestProj", "summary": "test"},
            "# Test Project",
        ))

        resp = client.post("/api/export", json={"projects": ["projects/TestProj"]})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"
        assert "filename=" in resp.headers.get("content-disposition", "")
        assert len(resp.content) > 0  # has data

    def test_export_multiple_projects(self, client, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        from backend.storage import dump_frontmatter
        for name in ["ProjA", "ProjB"]:
            (tmp_kb_root / "projects" / name / "common-knowledge").mkdir(parents=True)
            storage.write_readme(f"projects/{name}", {}, dump_frontmatter(
                {"id": name, "name": name, "summary": "t"},
                f"# {name}",
            ))

        resp = client.post("/api/export", json={"projects": ["projects/ProjA", "projects/ProjB"]})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert len(resp.content) > 0

    def test_export_nonexistent_project(self, client):
        resp = client.post("/api/export", json={"projects": ["projects/Nope"]})
        assert resp.status_code == 400
