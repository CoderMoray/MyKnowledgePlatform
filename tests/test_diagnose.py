"""Tests for the GET /api/diagnose read-only structural diagnosis endpoint.

The endpoint shells out to ``backend.validator.validate_kb`` — the same
single source of truth used by the ``maint__knowledgebase_diagnose`` MCP tool.
These tests exercise the REST contract: JSON shape, field completeness,
problem detection, summary consistency, and strict read-only behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage


@pytest.fixture
def client(tmp_kb_root: Path):
    """FastAPI test client with the KB storage overridden to tmp_kb_root."""
    import backend.main
    from backend.main import app, get_storage as _orig_get_storage

    storage = Storage(kb_root=tmp_kb_root)

    def _test_storage():
        template = tmp_kb_root / "_templates" / "readme.md"
        if not template.exists():
            template.parent.mkdir(parents=True, exist_ok=True)
            template.write_text("# {name}\n\n{summary}")
        gen = ReadmeGenerator(storage=storage, template_path=template)
        return storage, gen

    backend.main.get_storage = _test_storage
    yield TestClient(app)
    backend.main.get_storage = _orig_get_storage


def _write_raw(storage: Storage, rel: str, content: str) -> None:
    """Write a file directly (bypasses auto-id injection for metadata tests)."""
    full = storage._abs(rel)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


def _healthy_doc(rel: str, body: str = "# hi") -> str:
    return f"---\nid: {rel.split('/')[-1]}\ncreated: '2026-01-01'\nsummary: 摘要\n---\n\n{body}"


def _write_template(tmp_kb_root: Path) -> Path:
    """Write the shipped readme template into the KB root (idempotent)."""
    template = tmp_kb_root / "_templates" / "readme.md"
    if not template.exists():
        template.parent.mkdir(parents=True, exist_ok=True)
        shipped = (Path(__file__).resolve().parent.parent
                   / "backend" / "templates" / "readme.md")
        template.write_text(shipped.read_text(encoding="utf-8"), encoding="utf-8")
    return template


def _rebuild_all(gen: ReadmeGenerator, storage: Storage) -> None:
    """Rebuild every layer + project-status (syncs the KB to a clean state)."""
    def _collect(container: str, out: list) -> None:
        for e in storage.list_children(container):
            if e.is_dir:
                layer = f"{container}/{e.name}"
                out.append(layer)
                if storage.path_exists(f"{layer}/projects"):
                    _collect(f"{layer}/projects", out)

    layers: list[str] = []
    _collect("projects", layers)
    _collect("archive", layers)
    for layer in sorted(layers, key=lambda p: p.count("/"), reverse=True):
        gen.rebuild(layer)
    gen.rebuild("")
    gen.rebuild_project_status()


def _snapshot(tmp_kb_root: Path) -> set[tuple[str, str]]:
    """Return ``{(relpath, mtime_ns)}`` for every file under the KB root."""
    out: set[tuple[str, str]] = set()
    for p in tmp_kb_root.rglob("*"):
        if p.is_file():
            out.add((str(p.relative_to(tmp_kb_root)), str(p.stat().st_mtime_ns)))
    return out


class TestDiagnoseHealthy:
    def test_healthy_kb_returns_empty_issues(self, client, tmp_kb_root: Path) -> None:
        """A properly built KB → 200, empty issues, correct summary."""
        storage = Storage(kb_root=tmp_kb_root)
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(
            parents=True, exist_ok=True)
        _write_raw(storage, "common-knowledge/root.md", _healthy_doc("root.md"))
        _write_raw(storage, "projects/P/common-knowledge/p.md", _healthy_doc("p.md"))
        _rebuild_all(ReadmeGenerator(storage=storage,
                                     template_path=_write_template(tmp_kb_root)),
                     storage)

        resp = client.get("/api/diagnose")
        assert resp.status_code == 200
        data = resp.json()
        assert "issues" in data and "summary" in data
        assert data["issues"] == []
        assert data["summary"]["total_issues"] == 0
        assert data["summary"]["total_files"] == 2
        assert data["summary"]["by_type"] == {}


class TestDiagnoseProblems:
    def test_problem_kb_reports_correct_types(self, client, tmp_kb_root: Path) -> None:
        """Orphan doc + missing frontmatter + stale readme + dead ref → issues."""
        storage = Storage(kb_root=tmp_kb_root)
        # healthy doc in ck
        _write_raw(storage, "common-knowledge/good.md", _healthy_doc("good.md"))
        # orphan doc directly at project layer (position) with NO frontmatter
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(
            parents=True, exist_ok=True)
        _write_raw(storage, "projects/P/note.md", "# no frontmatter here")
        # dead ref inside a healthy doc (ref)
        _write_raw(storage, "common-knowledge/deadref.md",
                   _healthy_doc("deadref.md", "# r\n[dead](ref:common-knowledge/nope.md)"))
        _rebuild_all(ReadmeGenerator(storage=storage,
                                     template_path=_write_template(tmp_kb_root)),
                     storage)
        # now add a healthy doc WITHOUT rebuilding → stale readme (index)
        _write_raw(storage, "common-knowledge/stale.md", _healthy_doc("stale.md"))

        resp = client.get("/api/diagnose")
        assert resp.status_code == 200
        data = resp.json()
        issues = data["issues"]
        assert issues, "problem KB must report at least one issue"

        # every issue must carry all six fields
        for issue in issues:
            for field in ("path", "type", "severity", "message", "action",
                          "needs_semantic"):
                assert field in issue, f"issue missing field: {field}"

        types = {i["type"] for i in issues}
        assert "position" in types       # projects/P/note.md orphan
        assert "metadata" in types       # no frontmatter
        assert "index" in types          # stale readme
        assert "ref" in types            # dead ref

        # summary consistency
        assert data["summary"]["total_issues"] == len(issues)
        by_type = data["summary"]["by_type"]
        assert sum(by_type.values()) == len(issues)


class TestDiagnoseReadOnly:
    def test_diagnose_does_not_mutate_kb(self, client, tmp_kb_root: Path) -> None:
        """KB content untouched → only the persisted result file is added.

        ``/api/diagnose`` deliberately persists its result to
        ``.diagnose-result.json`` (dot-prefixed → ignored by the validator),
        so that file is excluded from the KB-content comparison.
        """
        storage = Storage(kb_root=tmp_kb_root)
        _write_raw(storage, "common-knowledge/good.md", _healthy_doc("good.md"))
        _write_raw(storage, "common-knowledge/no_fm.md", "# no frontmatter")
        _rebuild_all(ReadmeGenerator(storage=storage,
                                     template_path=_write_template(tmp_kb_root)),
                     storage)

        before = {k for k in _snapshot(tmp_kb_root)
                  if not k[0].startswith(".diagnose-result.json")}
        resp = client.get("/api/diagnose")
        assert resp.status_code == 200
        assert resp.json()["issues"]  # sanity: we did find problems
        after = {k for k in _snapshot(tmp_kb_root)
                 if not k[0].startswith(".diagnose-result.json")}
        assert after == before, "diagnose must not alter any KB file"

    def test_diagnose_writes_result_file(self, client, tmp_kb_root: Path) -> None:
        """diagnose persists .diagnose-result.json with issues/summary/generated_at."""
        storage = Storage(kb_root=tmp_kb_root)
        _write_raw(storage, "common-knowledge/no_fm.md", "# no frontmatter")
        _rebuild_all(ReadmeGenerator(storage=storage,
                                     template_path=_write_template(tmp_kb_root)),
                     storage)

        resp = client.get("/api/diagnose")
        assert resp.status_code == 200

        result_file = tmp_kb_root / ".diagnose-result.json"
        assert result_file.exists()
        data = json.loads(result_file.read_text(encoding="utf-8"))
        assert "issues" in data and "summary" in data
        assert isinstance(data["generated_at"], str) and data["generated_at"]
        assert len(data["issues"]) == len(resp.json()["issues"])

        # no leftover temp file from the atomic write
        assert not (tmp_kb_root / ".diagnose-result.json.tmp").exists()


class TestDiagnoseSaved:
    def test_saved_absent_before_any_diagnose(self, client, tmp_kb_root: Path) -> None:
        """No prior run → {saved: False} (200, not 500)."""
        resp = client.get("/api/diagnose/saved")
        assert resp.status_code == 200
        assert resp.json() == {"saved": False}

    def test_saved_returns_last_result(self, client, tmp_kb_root: Path) -> None:
        """After a diagnose run, /saved returns the persisted result."""
        storage = Storage(kb_root=tmp_kb_root)
        _write_raw(storage, "common-knowledge/no_fm.md", "# no frontmatter")
        _rebuild_all(ReadmeGenerator(storage=storage,
                                     template_path=_write_template(tmp_kb_root)),
                     storage)

        run = client.get("/api/diagnose")
        assert run.status_code == 200

        resp = client.get("/api/diagnose/saved")
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert "issues" in data and "summary" in data
        assert isinstance(data["generated_at"], str) and data["generated_at"]
        assert len(data["issues"]) == len(run.json()["issues"])
        assert data["summary"]["total_issues"] == run.json()["summary"]["total_issues"]

    def test_saved_corrupt_file_returns_empty_state(
            self, client, tmp_kb_root: Path) -> None:
        """Corrupt/malformed result file → {saved: False} (200, not 500)."""
        result_file = tmp_kb_root / ".diagnose-result.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text("{ not valid json !!!", encoding="utf-8")

        resp = client.get("/api/diagnose/saved")
        assert resp.status_code == 200
        assert resp.json() == {"saved": False}

        # a non-dict JSON payload also yields empty state
        result_file.write_text("[1, 2, 3]", encoding="utf-8")
        resp = client.get("/api/diagnose/saved")
        assert resp.status_code == 200
        assert resp.json() == {"saved": False}
