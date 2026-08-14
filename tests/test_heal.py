"""Tests for phase-B heal functionality.

Covers the shared ``move_document`` kernel, the ``maint__move_document`` MCP
tool, and the REST endpoints ``POST /api/heal/move`` and ``POST /api/heal/rebuild``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.mcp_server import (
    acquire_lock,
    create_mcp_app,
    move_document,
)
from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage
from backend.validator import validate_kb


# ── fixtures ───────────────────────────────────────────────────

@pytest.fixture
def gen(storage: Storage, tmp_kb_root: Path) -> ReadmeGenerator:
    """A ReadmeGenerator with the shipped template + initial root readme."""
    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
    template.write_text(shipped.read_text(encoding="utf-8"), encoding="utf-8")
    g = ReadmeGenerator(storage=storage, template_path=template)
    g.rebuild("", name="TestKB", summary="test")
    return g


@pytest.fixture
def app(storage: Storage, gen: ReadmeGenerator):
    """FastMCP app bound to the test KB (with write lock)."""
    acquire_lock(storage)
    return create_mcp_app(storage, gen=gen)


@pytest.fixture
def client(tmp_kb_root: Path, storage: Storage):
    """FastAPI test client with the KB storage overridden to tmp_kb_root."""
    import backend.main
    from backend.main import app as _app
    from backend.main import get_storage as _orig

    def _test_storage():
        template = tmp_kb_root / "_templates" / "readme.md"
        if not template.exists():
            template.parent.mkdir(parents=True, exist_ok=True)
            template.write_text("# {name}\n\n{summary}")
        gen = ReadmeGenerator(storage=storage, template_path=template)
        return storage, gen

    backend.main.get_storage = _test_storage
    yield TestClient(_app)
    backend.main.get_storage = _orig


# ── helpers ────────────────────────────────────────────────────

def _write_raw(storage: Storage, rel: str, content: str) -> None:
    """Write a file directly (bypasses auto-id injection)."""
    full = storage._abs(rel)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


def _healthy_doc(name: str, body: str = "# hi") -> str:
    return f"---\nid: {name}\ncreated: '2026-01-01'\nsummary: 摘要\n---\n\n{body}"


def _mk_orphan(storage: Storage, project: str, name: str) -> str:
    """Create an orphan doc at ``projects/{project}/{name}`` (not under ck)."""
    rel = f"projects/{project}/{name}"
    _write_raw(storage, rel, _healthy_doc(name))
    return rel


def _mk_ck(storage: Storage, project: str) -> None:
    (storage.kb_root / "projects" / project / "common-knowledge").mkdir(
        parents=True, exist_ok=True)


# ── move_document (shared kernel) ──────────────────────────────

class TestMoveDocument:
    def test_cross_dir_move_success(self, storage: Storage, gen) -> None:
        _mk_ck(storage, "P")
        src = _mk_orphan(storage, "P", "x.md")
        dst = "projects/P/common-knowledge/x.md"
        result = move_document(storage, src, dst)
        assert "已移动" in result
        assert not (storage.kb_root / src).exists()
        assert (storage.kb_root / dst).exists()
        # validator no longer reports the orphan as position
        gen.rebuild("projects/P", parent="")
        gen.rebuild("")
        gen.rebuild_project_status()
        report = validate_kb(storage, gen)
        assert not [i for i in report.issues
                    if i.type == "position" and dst in i.path]

    def test_ref_links_replaced(self, storage: Storage, gen) -> None:
        _mk_ck(storage, "P")
        src = _mk_orphan(storage, "P", "x.md")
        # a doc referencing the orphan
        storage.write_document(
            "common-knowledge/ref.md",
            {"summary": "s"},
            f"[链接](ref:projects/P/x.md)\n# ref")
        dst = "projects/P/common-knowledge/x.md"
        move_document(storage, src, dst)
        _, body = storage.read_document("common-knowledge/ref.md")
        assert f"ref:projects/P/common-knowledge/x.md" in body
        assert "ref:projects/P/x.md" not in body

    def test_target_exists_raises(self, storage: Storage, gen) -> None:
        _mk_ck(storage, "P")
        src = _mk_orphan(storage, "P", "x.md")
        # pre-create the target
        _write_raw(storage, "projects/P/common-knowledge/x.md", _healthy_doc("x.md"))
        with pytest.raises(FileExistsError):
            move_document(storage, src, "projects/P/common-knowledge/x.md")

    def test_illegal_target_rejected(self, storage: Storage, gen) -> None:
        _mk_ck(storage, "P")
        src = _mk_orphan(storage, "P", "x.md")
        # destination basename is readme.md → rejected
        with pytest.raises(ValueError, match="readme"):
            move_document(storage, src, "projects/P/common-knowledge/readme.md")
        # traversal / absolute target → rejected
        with pytest.raises(ValueError):
            move_document(storage, src, "/etc/x.md")
        with pytest.raises(ValueError):
            move_document(storage, src, "../evil/x.md")

    def test_same_path_rejected(self, storage: Storage, gen) -> None:
        _mk_ck(storage, "P")
        src = _mk_orphan(storage, "P", "x.md")
        with pytest.raises(ValueError, match="无需移动"):
            move_document(storage, src, src)

    def test_missing_source_raises(self, storage: Storage, gen) -> None:
        _mk_ck(storage, "P")
        with pytest.raises(FileNotFoundError):
            move_document(storage, "projects/P/ghost.md",
                          "projects/P/common-knowledge/ghost.md")


# ── precise git commit (unrelated files stay uncommitted) ──────

class TestPreciseCommit:
    def test_move_does_not_sweep_unrelated_dirty_file(
            self, storage: Storage, gen, tmp_kb_root: Path) -> None:
        """move_document commits only its involved files, not an unrelated dirty file."""
        from backend.git_manager import GitManager
        gm = GitManager(tmp_kb_root)
        gm.init()
        gm.commit("init")

        _mk_ck(storage, "P")
        src = _mk_orphan(storage, "P", "x.md")
        dst = "projects/P/common-knowledge/x.md"
        # unrelated dirty file, present but not part of the move
        unrelated = tmp_kb_root / "common-knowledge" / "unrelated.md"
        unrelated.parent.mkdir(parents=True, exist_ok=True)
        unrelated.write_text("# unrelated", encoding="utf-8")

        move_document(storage, src, dst)

        # the unrelated file must still be uncommitted after the move commit
        assert gm.has_uncommitted_changes()
        # use -uall so git lists each untracked file explicitly (no dir collapsing)
        status = gm._run("status", "--porcelain", "--untracked-files=all")
        assert "common-knowledge/unrelated.md" in status
        # the moved doc + rebuilt indexes were committed (not dirty)
        assert "projects/P/common-knowledge/x.md" not in status
        assert "projects/P/readme.md" not in status
        assert "readme.md" not in status


class TestMaintMoveDocument:
    def test_mcp_default_peer_target(self, app, storage: Storage, gen) -> None:
        _mk_ck(storage, "P")
        src = _mk_orphan(storage, "P", "y.md")
        result = asyncio.run(app.call_tool("maint__move_document",
                                           {"path": src}))
        text = result[0][0].text
        assert "已移动" in text
        assert not (storage.kb_root / src).exists()
        assert (storage.kb_root / "projects" / "P" / "common-knowledge" / "y.md").exists()

    def test_mcp_explicit_target(self, app, storage: Storage, gen) -> None:
        _mk_ck(storage, "P")
        src = _mk_orphan(storage, "P", "z.md")
        result = asyncio.run(app.call_tool(
            "maint__move_document",
            {"path": src, "target_rel": "projects/P/common-knowledge"}))
        assert "已移动" in result[0][0].text


# ── REST: /api/heal/move ───────────────────────────────────────

class TestHealMoveREST:
    def test_batch_success(self, client, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        _mk_ck(storage, "P")
        _mk_ck(storage, "Q")
        src1 = _mk_orphan(storage, "P", "a.md")
        src2 = _mk_orphan(storage, "Q", "b.md")
        resp = client.post("/api/heal/move", json={
            "paths": [src1, src2],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["moved"]) == 2
        assert "projects/P/common-knowledge/a.md" in data["moved"]
        assert "projects/Q/common-knowledge/b.md" in data["moved"]
        assert data["failed"] == []

    def test_partial_failure_marked(self, client, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        _mk_ck(storage, "P")
        src = _mk_orphan(storage, "P", "ok.md")
        resp = client.post("/api/heal/move", json={
            "paths": [src, "projects/P/nonexistent.md"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["moved"]) == 1
        assert data["moved"][0] == "projects/P/common-knowledge/ok.md"
        assert len(data["failed"]) == 1
        assert data["failed"][0]["path"] == "projects/P/nonexistent.md"
        assert "error" in data["failed"][0]

    def test_explicit_target_rel(self, client, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        _mk_ck(storage, "P")
        src = _mk_orphan(storage, "P", "c.md")
        resp = client.post("/api/heal/move", json={
            "paths": [src],
            "target_rel": "projects/P/common-knowledge",
        })
        assert resp.status_code == 200
        assert resp.json()["moved"] == ["projects/P/common-knowledge/c.md"]


# ── REST: /api/heal/rebuild ────────────────────────────────────

class TestHealRebuildREST:
    def test_rebuild_specified_layers(self, client, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        _mk_ck(storage, "P")
        _write_raw(storage, "projects/P/common-knowledge/p.md", _healthy_doc("p.md"))
        # stale: add a doc without rebuilding
        _write_raw(storage, "projects/P/common-knowledge/stale.md", _healthy_doc("stale.md"))

        resp = client.post("/api/heal/rebuild", json={
            "layers": ["projects/P"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "projects/P" in data["rebuilt"]
        assert data["project_status"] is True

    def test_rebuild_all_recurses(self, client, tmp_kb_root: Path) -> None:
        storage = Storage(kb_root=tmp_kb_root)
        _mk_ck(storage, "P")
        (storage.kb_root / "projects" / "P" / "projects" / "C" / "common-knowledge").mkdir(
            parents=True, exist_ok=True)
        _write_raw(storage, "projects/P/common-knowledge/p.md", _healthy_doc("p.md"))
        _write_raw(storage, "projects/P/projects/C/common-knowledge/c.md", _healthy_doc("c.md"))

        resp = client.post("/api/heal/rebuild", json={"all": True})
        assert resp.status_code == 200
        rebuilt = resp.json()["rebuilt"]
        assert "projects/P" in rebuilt
        assert "projects/P/projects/C" in rebuilt
        assert "" in rebuilt  # root readme rebuilt
        assert resp.json()["project_status"] is True

    def test_rebuild_refreshes_project_status(self, client, tmp_kb_root: Path) -> None:
        """After orphaning a project, rebuild syncs project-status.md."""
        import shutil
        storage = Storage(kb_root=tmp_kb_root)
        _mk_ck(storage, "P")
        _write_raw(storage, "projects/P/common-knowledge/p.md", _healthy_doc("p.md"))
        # initial full build
        from backend.readme_generator import ReadmeGenerator
        template = tmp_kb_root / "_templates" / "readme.md"
        template.parent.mkdir(parents=True, exist_ok=True)
        shipped = (Path(__file__).resolve().parent.parent
                   / "backend" / "templates" / "readme.md")
        template.write_text(shipped.read_text(encoding="utf-8"), encoding="utf-8")
        gen = ReadmeGenerator(storage=storage, template_path=template)
        gen.rebuild("projects/P", parent="")
        gen.rebuild("")
        gen.rebuild_project_status()
        # remove the project dir → project-status now stale
        shutil.rmtree(str(storage.kb_root / "projects" / "P"))

        resp = client.post("/api/heal/rebuild", json={"all": True})
        assert resp.status_code == 200
        assert resp.json()["project_status"] is True
