"""Tests for backend/main.py — REST API and shared utilities."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.storage import Storage
from backend.mcp_server import _lock_file


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


class TestApiUpdateDocument:
    """Test PUT /api/document/{path} — update and no-op behavior."""

    def test_noop_save_does_not_change_maintainer(self, client, tmp_kb_root: Path):
        """Saving unchanged content should not update maintainer or updated."""
        from backend.storage import dump_frontmatter
        storage = Storage(kb_root=tmp_kb_root)

        doc_path = "common-knowledge/noop.md"
        body = "# original content\n\nno changes"
        meta = {"id": "noop", "summary": "original summary",
                "maintainer": "Original Author", "created": "2026-01-01",
                "updated": "2026-01-01"}
        storage.write_document(doc_path, meta, body, auto_id=False)

        # Read back, send PUT with exactly the same content
        resp = client.put(f"/api/document/{doc_path}", json={
            "content": body,
            "summary": "original summary",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("unchanged") is True, "should detect no-op"

        # Verify frontmatter was NOT modified
        new_meta, new_body = storage.read_document(doc_path)
        assert new_meta.get("maintainer") == "Original Author"
        assert new_meta.get("updated") == "2026-01-01"

    def test_update_changes_maintainer(self, client, tmp_kb_root: Path):
        """Actually changing content should update maintainer and updated."""
        storage = Storage(kb_root=tmp_kb_root)
        doc_path = "common-knowledge/change.md"
        body = "# old"
        from backend.mcp_server import _yaml_dump
        storage.write_document(doc_path, {"id": "chg", "summary": "old",
                                          "maintainer": "Old", "created": "2026-01-01",
                                          "updated": "2026-01-01"}, body, auto_id=False)

        resp = client.put(f"/api/document/{doc_path}", json={
            "content": "# new content",
            "summary": "new summary",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("unchanged") is False

        new_meta, new_body = storage.read_document(doc_path)
        assert "new content" in new_body
        assert new_meta.get("summary") == "new summary"
        assert new_meta.get("maintainer") != "Old"  # got updated

    def test_update_keep_old_body_when_empty(self, client, tmp_kb_root: Path):
        """Sending empty content should keep the existing body."""
        storage = Storage(kb_root=tmp_kb_root)
        doc_path = "common-knowledge/keep-body.md"
        body = "# existing body text"
        storage.write_document(doc_path, {"id": "kb", "summary": "s",
                                          "maintainer": "Me", "created": "2026-01-01",
                                          "updated": "2026-01-01"}, body, auto_id=False)

        resp = client.put(f"/api/document/{doc_path}", json={
            "content": "",
            "summary": "",
        })
        assert resp.status_code == 200
        data = resp.json()
        # content was "" so it kept old body, and summary also unchanged → no-op
        assert data.get("unchanged") is True


class TestOptimisticLock:
    """Test optimistic locking on GET/PUT /api/document/{path}."""

    def _make_doc(self, storage: Storage, path: str,
                  summary: str = "summary") -> str:
        from backend.main import _doc_version
        storage.write_document(path, {"id": path, "summary": summary,
                                      "maintainer": "Me",
                                      "created": "2026-01-01",
                                      "updated": "2026-01-01"},
                               "# body", auto_id=False)
        return _doc_version("# body", summary)

    def test_get_returns_version(self, client, tmp_kb_root: Path):
        from backend.main import _doc_version
        storage = Storage(kb_root=tmp_kb_root)
        self._make_doc(storage, "common-knowledge/v.md", "s")
        resp = client.get("/api/document/common-knowledge/v.md")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == _doc_version("# body", "s")
        assert data["summary"] == "s"

    def test_put_with_correct_version_succeeds(self, client, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        version = self._make_doc(storage, "common-knowledge/ok.md", "s")
        resp = client.put("/api/document/common-knowledge/ok.md", json={
            "content": "# new body",
            "summary": "s",
            "expected_version": version,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["unchanged"] is False
        from backend.main import _doc_version
        assert data["version"] == _doc_version("# new body", "s")

    def test_put_with_stale_version_conflict(self, client, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        version = self._make_doc(storage, "common-knowledge/stale.md", "s")

        # Simulate another session modifying the doc
        storage.write_document("common-knowledge/stale.md",
                               {"id": "stale", "summary": "s2",
                                "maintainer": "Other",
                                "created": "2026-01-01", "updated": "2026-01-02"},
                               "# changed by other", auto_id=False)

        resp = client.put("/api/document/common-knowledge/stale.md", json={
            "content": "# my edit",
            "summary": "s",
            "expected_version": version,  # stale
        })
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "conflict"
        assert "current_version" in data
        assert "content" in data
        assert "current_summary" in data
        assert data["current_summary"] == "s2"
        assert data["content"] == "# changed by other"

    def test_put_without_expected_version_still_works(self, client, tmp_kb_root: Path):
        """No expected_version → old behavior (force overwrite)."""
        storage = Storage(kb_root=tmp_kb_root)
        self._make_doc(storage, "common-knowledge/force.md", "s")
        resp = client.put("/api/document/common-knowledge/force.md", json={
            "content": "# overwritten",
            "summary": "new summary",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["unchanged"] is False
        _, body = storage.read_document("common-knowledge/force.md")
        assert "# overwritten" in body

    def test_conflict_409_precedes_validation_400(self, client, tmp_kb_root: Path):
        """409 (conflict) should take priority over 400 (dead ref validation)."""
        storage = Storage(kb_root=tmp_kb_root)
        version = self._make_doc(storage, "common-knowledge/prio.md", "s")
        # Modify elsewhere
        storage.write_document("common-knowledge/prio.md",
                               {"id": "prio", "summary": "s", "maintainer": "O",
                                "created": "2026-01-01", "updated": "2026-01-02"},
                               "# other", auto_id=False)
        # Stale version + dead ref (would 400 if not for conflict)
        resp = client.put("/api/document/common-knowledge/prio.md", json={
            "content": "# edit [dead](ref:common-knowledge/nope.md)",
            "summary": "s",
            "expected_version": version,
        })
        assert resp.status_code == 409


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


class TestApiRenameDocument:
    """Test PUT /api/document/rename (REST shell of rename_document)."""

    def _make(self, storage: Storage, path: str, body: str = "# body") -> None:
        storage.write_document(path, {"id": path, "summary": "s",
                                      "maintainer": "Me",
                                      "created": "2026-01-01",
                                      "updated": "2026-01-01"},
                               body, auto_id=False)

    def _rename(self, client, path: str, new_name: str):
        return client.put("/api/document/rename",
                          json={"path": path, "new_name": new_name})

    def test_file_moved(self, client, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        self._make(storage, "common-knowledge/old.md")
        resp = self._rename(client, "common-knowledge/old.md", "new.md")
        assert resp.status_code == 200
        assert (tmp_kb_root / "common-knowledge" / "new.md").is_file()
        assert not (tmp_kb_root / "common-knowledge" / "old.md").exists()
        meta, body = storage.read_document("common-knowledge/new.md")
        assert "# body" in body

    def test_ref_exact_replacement_no_false_positive(self, client, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        self._make(storage, "common-knowledge/old.md")
        # Referrer doc: exact ref (should replace), plain-text mention (should not),
        # prefix-similar ref (should not), unrelated ref (should not)
        referrer = (
            "[目标](ref:common-knowledge/old.md)\n"
            "正文里提到 common-knowledge/old.md 不是引用\n"
            "[子](ref:common-knowledge/old.md/sub.md)\n"
            "[无关](ref:common-knowledge/other.md)\n"
        )
        self._make(storage, "common-knowledge/referrer.md", referrer)
        self._make(storage, "common-knowledge/other.md", "other")

        resp = self._rename(client, "common-knowledge/old.md", "new.md")
        assert resp.status_code == 200

        content = storage.read_content("common-knowledge/referrer.md")
        assert "ref:common-knowledge/new.md" in content      # exact replaced
        assert "正文里提到 common-knowledge/old.md 不是引用" in content  # plain text kept
        assert "ref:common-knowledge/old.md/sub.md" in content  # prefix-similar kept
        assert "ref:common-knowledge/other.md" in content     # unrelated kept

    def test_rename_duplicate_400(self, client, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        self._make(storage, "common-knowledge/a.md")
        self._make(storage, "common-knowledge/b.md")
        resp = self._rename(client, "common-knowledge/a.md", "b.md")
        assert resp.status_code == 400
        # original unchanged
        assert (tmp_kb_root / "common-knowledge" / "a.md").is_file()
        # lock released even on error
        assert not _lock_file(tmp_kb_root).exists()

    def test_rename_nonexistent_400(self, client, tmp_kb_root: Path):
        resp = self._rename(client, "common-knowledge/nope.md", "new.md")
        assert resp.status_code == 400

    def test_lock_released_after_rename(self, client, tmp_kb_root: Path):
        """Frontend-reported bug: rename must not leave .lock behind."""
        storage = Storage(kb_root=tmp_kb_root)
        self._make(storage, "common-knowledge/lock.md")
        resp = self._rename(client, "common-knowledge/lock.md", "renamed.md")
        assert resp.status_code == 200
        # Lock MUST be released (frontend gets stuck read-only if left)
        assert not _lock_file(tmp_kb_root).exists()

    def test_lock_released_on_failure(self, client, tmp_kb_root: Path):
        """Lock released even when rename fails (finally guarantees it)."""
        storage = Storage(kb_root=tmp_kb_root)
        self._make(storage, "common-knowledge/fail.md")
        self._make(storage, "common-knowledge/taken.md")
        resp = self._rename(client, "common-knowledge/fail.md", "taken.md")
        assert resp.status_code == 400
        assert not _lock_file(tmp_kb_root).exists()

    def test_special_char_paths(self, client, tmp_kb_root: Path):
        """Chinese / spaces / parentheses in filenames."""
        storage = Storage(kb_root=tmp_kb_root)
        old = "common-knowledge/旧文档 (草稿).md"
        new = "common-knowledge/新文档 (正式).md"
        self._make(storage, old, "# 中文正文")
        resp = self._rename(client, old, "新文档 (正式).md")
        assert resp.status_code == 200
        assert (tmp_kb_root / "common-knowledge" / "新文档 (正式).md").is_file()
        assert not (tmp_kb_root / "common-knowledge" / "旧文档 (草稿).md").exists()

    def test_rebuild_generates_new_path(self, client, tmp_kb_root: Path):
        """Parent readme / project-status rebuilt without dead links."""
        from backend.readme_generator import ReadmeGenerator
        tmpl = tmp_kb_root / "_templates" / "readme.md"
        if not tmpl.exists():
            tmpl.parent.mkdir(parents=True, exist_ok=True)
            tmpl.write_text("# {name}\n\n{summary}")
        gen = ReadmeGenerator(storage=Storage(kb_root=tmp_kb_root), template_path=tmpl)
        gen.rebuild("", name="KB", summary="t")

        from backend.storage import dump_frontmatter
        storage = Storage(kb_root=tmp_kb_root)
        (tmp_kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True)
        storage.write_readme("projects/P", {"id": "P", "name": "P", "summary": "p"},
                             dump_frontmatter({"id": "P", "name": "P", "summary": "p"}, "# P"))
        self._make(storage, "projects/P/common-knowledge/doc.md")
        gen.rebuild("projects/P")

        resp = self._rename(client, "projects/P/common-knowledge/doc.md", "renamed.md")
        assert resp.status_code == 200
        # project readme references the new file, no dead link
        readme = storage.read_content("projects/P/readme.md")
        assert "renamed.md" in readme
        assert "doc.md" not in readme
