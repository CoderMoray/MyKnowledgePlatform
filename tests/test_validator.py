"""Tests for backend.validator.validate_kb (KB structural diagnosis).

Pure read-only: every scenario asserts that validate_kb reports the expected
issues without ever writing / committing / mutating the working tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.git_manager import GitManager
from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage
from backend.validator import validate_kb


@pytest.fixture
def gen(storage: Storage, tmp_kb_root: Path) -> ReadmeGenerator:
    """A ReadmeGenerator bound to the temporary KB with the shipped template."""
    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
    template.write_text(shipped.read_text(), encoding="utf-8")
    g = ReadmeGenerator(storage=storage, template_path=template)
    g.rebuild("", name="TestKB", summary="test")
    g.rebuild_project_status()
    return g


def _rebuild_all(gen: ReadmeGenerator, storage: Storage) -> None:
    """Rebuild every layer + project-status (syncs the KB to a clean state).

    Project layers are rebuilt before the root readme (the root references
    project summaries), so the rebuilt root is always in sync.
    """
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
    # deepest layers first, so a parent project reads its subprojects' readmes
    for layer in sorted(layers, key=lambda p: p.count("/"), reverse=True):
        gen.rebuild(layer)
    gen.rebuild("")
    gen.rebuild_project_status()


def _write_raw(storage: Storage, rel: str, content: str) -> None:
    """Write a file directly (bypasses auto-id injection for metadata tests)."""
    full = storage._abs(rel)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


def _healthy_doc(rel: str, body: str = "# hi") -> str:
    return f"---\nid: {rel.split('/')[-1]}\ncreated: '2026-01-01'\nsummary: 摘要\n---\n\n{body}"


class TestPosition:
    def test_orphan_doc_at_project_layer(self, storage: Storage, gen) -> None:
        """projects/P/x.md (not under common-knowledge/) → position issue."""
        from backend.storage import Storage as _S
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "projects/P/note.md", _healthy_doc("note.md"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        pos = [i for i in report.issues if i.type == "position"]
        assert any("projects/P/note.md" in i.path for i in pos)
        assert all(i.action == "move_to_peer_ck" for i in pos)

    def test_orphan_doc_at_root(self, storage: Storage, gen) -> None:
        """rootdoc.md (directly at root) → position issue."""
        _write_raw(storage, "rootdoc.md", _healthy_doc("rootdoc.md"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        pos = [i for i in report.issues if i.type == "position"]
        assert any("rootdoc.md" in i.path for i in pos)


class TestMetadata:
    def test_no_frontmatter(self, storage: Storage, gen) -> None:
        _write_raw(storage, "common-knowledge/no_fm.md", "# no frontmatter")
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        meta = [i for i in report.issues if i.type == "metadata"]
        assert any("no_fm.md" in i.path for i in meta)

    def test_missing_id(self, storage: Storage, gen) -> None:
        _write_raw(
            storage, "common-knowledge/no_id.md",
            "---\ncreated: '2026-01-01'\nsummary: 摘要\n---\n# hi")
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        meta = [i for i in report.issues if i.type == "metadata"]
        assert any("no_id.md" in i.path for i in meta)

    def test_missing_created(self, storage: Storage, gen) -> None:
        _write_raw(
            storage, "common-knowledge/no_created.md",
            "---\nid: no_created\nsummary: 摘要\n---\n# hi")
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        meta = [i for i in report.issues if i.type == "metadata"]
        assert any("no_created.md" in i.path for i in meta)

    def test_missing_summary_is_semantic(self, storage: Storage, gen) -> None:
        _write_raw(
            storage, "common-knowledge/no_summary.md",
            "---\nid: no_summary\ncreated: '2026-01-01'\n---\n# hi")
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        meta = [i for i in report.issues if i.type == "metadata"
                and "no_summary.md" in i.path]
        assert meta
        assert meta[0].needs_semantic is True


class TestIndex:
    def test_stale_readme_reported_then_clean(self, storage: Storage, gen) -> None:
        # healthy structure, fully rebuilt → no index issue
        _write_raw(
            storage, "common-knowledge/ok.md",
            _healthy_doc("ok.md"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        assert not [i for i in report.issues if i.type == "index"]

        # add a healthy file but DON'T rebuild → readme now stale
        _write_raw(
            storage, "common-knowledge/stale.md",
            _healthy_doc("stale.md"))
        report = validate_kb(storage, gen)
        idx = [i for i in report.issues if i.type == "index"]
        assert idx
        assert all(i.action == "rebuild_index" for i in idx)

        # rebuild → no index issue again
        gen.rebuild("")
        report = validate_kb(storage, gen)
        assert not [i for i in report.issues if i.type == "index"]

    def test_stale_project_status(self, storage: Storage, gen) -> None:
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        _write_raw(
            storage, "projects/P/common-knowledge/ok.md", _healthy_doc("ok.md"))
        gen.rebuild("projects/P", parent="root")
        gen.rebuild("")
        gen.rebuild_project_status()
        report = validate_kb(storage, gen)
        assert not [i for i in report.issues if i.type == "index"]

        # remove the project (orphan the dir) but don't rebuild status
        import shutil
        shutil.rmtree(str(storage.kb_root / "projects" / "P"))
        report = validate_kb(storage, gen)
        idx = [i for i in report.issues if i.type == "index"]
        assert any("project-status.md" in i.path for i in idx)


class TestRef:
    def test_dead_ref(self, storage: Storage, gen) -> None:
        _write_raw(
            storage, "common-knowledge/withref.md",
            _healthy_doc("withref.md", "# r\n[dead](ref:common-knowledge/nothere.md)"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        refs = [i for i in report.issues if i.type == "ref"]
        assert refs
        assert "nothere.md" in refs[0].message


class TestIllegal:
    def test_empty_ck_dir(self, storage: Storage, gen) -> None:
        (storage.kb_root / "common-knowledge").mkdir(parents=True, exist_ok=True)
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        illegal = [i for i in report.issues if i.type == "illegal"]
        assert any("common-knowledge" in i.path for i in illegal)

    def test_ck_nested_dir(self, storage: Storage, gen) -> None:
        (storage.kb_root / "common-knowledge" / "sub").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "common-knowledge/sub/x.md", _healthy_doc("x.md"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        illegal = [i for i in report.issues if i.type == "illegal"]
        assert any("common-knowledge/sub" in i.path for i in illegal)


class TestMultiIssue:
    def test_one_file_multiple_issues(self, storage: Storage, gen) -> None:
        """A doc that's both orphaned AND missing frontmatter → 2 issues."""
        _write_raw(storage, "projects/P/bad.md", "# no frontmatter")
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        for_that_path = [i for i in report.issues
                         if i.path == "projects/P/bad.md"]
        assert len(for_that_path) >= 2
        types = {i.type for i in for_that_path}
        assert "position" in types
        assert "metadata" in types


class TestCleanKb:
    def test_clean_kb_no_issues(self, storage: Storage, gen) -> None:
        # build a realistic healthy tree: root + one project + one subproject
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        (storage.kb_root / "projects" / "P" / "projects" / "C" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "common-knowledge/root.md", _healthy_doc("root.md"))
        _write_raw(storage, "projects/P/common-knowledge/p.md", _healthy_doc("p.md"))
        _write_raw(storage, "projects/P/projects/C/common-knowledge/c.md", _healthy_doc("c.md"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        assert report.issues == []
        assert report.summary["total_issues"] == 0


class TestDryRunNoSideEffects:
    def test_rebuild_dry_run_is_read_only(self, storage: Storage, gen,
                                          tmp_kb_root: Path) -> None:
        # build a project so dry_run exercises the project-layer path
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "projects/P/common-knowledge/p.md", _healthy_doc("p.md"))
        gen.rebuild("projects/P", parent="root")
        gen.rebuild("")
        gen.rebuild_project_status()

        gm = GitManager(tmp_kb_root)
        gm.init()
        gm.commit("baseline")
        assert gm.worktree_status() == []

        # dry_run must not create dirs / write files / mutate the worktree
        gen.rebuild("projects/P", dry_run=True)
        gen.rebuild("", dry_run=True)
        gen.rebuild_project_status(dry_run=True)

        assert gm.worktree_status() == []
        assert not (storage.kb_root / "projects" / "Q").exists()  # no mkdir

    def test_rebuild_dry_run_returns_content(self, storage: Storage, gen) -> None:
        content = gen.rebuild("", dry_run=True)
        assert isinstance(content, str)
        assert content.strip()
        assert "#" in content  # markdown content


class TestSystem:
    """B1: type == 'system' coverage (readme/project-status missing or misplaced)."""

    def test_missing_root_readme(self, storage: Storage, gen) -> None:
        (storage.kb_root / "readme.md").unlink()
        report = validate_kb(storage, gen)
        sys_issues = [i for i in report.issues if i.type == "system"]
        assert any("readme.md" in i.path for i in sys_issues)

    def test_missing_project_readme(self, storage: Storage, gen) -> None:
        # build a project layer but don't create its readme
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "projects/P/common-knowledge/ok.md", _healthy_doc("ok.md"))
        gen.rebuild("")  # root exists, project readme intentionally absent
        report = validate_kb(storage, gen)
        sys_issues = [i for i in report.issues if i.type == "system"]
        assert any("projects/P/readme.md" in i.path for i in sys_issues)

    def test_missing_project_status(self, storage: Storage, gen) -> None:
        (storage.kb_root / "project-status.md").unlink()
        report = validate_kb(storage, gen)
        sys_issues = [i for i in report.issues if i.type == "system"]
        assert any("project-status.md" in i.path for i in sys_issues)

    def test_project_status_misplaced(self, storage: Storage, gen) -> None:
        # project-status.md inside a project layer → position error (system)
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "projects/P/project-status.md", "# project-status")
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        sys_issues = [i for i in report.issues if i.type == "system"]
        assert any("projects/P/project-status.md" in i.path for i in sys_issues)


class TestIllegalDirs:
    """B2 + B3: illegal dirs at project/root layers."""

    def test_non_container_dir_under_project(self, storage: Storage, gen) -> None:
        # projects/P/xxx_dir/ → not a container → illegal
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        (storage.kb_root / "projects" / "P" / "xxx_dir").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "projects/P/xxx_dir/inside.md", _healthy_doc("inside.md"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        illegal = [i for i in report.issues if i.type == "illegal"]
        assert any("projects/P/xxx_dir" in i.path for i in illegal)

    def test_non_container_dir_at_root(self, storage: Storage, gen) -> None:
        # root/weird_dir/ → not a container → illegal
        (storage.kb_root / "weird_dir").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "weird_dir/note.md", _healthy_doc("note.md"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        illegal = [i for i in report.issues if i.type == "illegal"]
        assert any("weird_dir" in i.path for i in illegal)


class TestIllegalFiles:
    """B4: non-.md files at various layers."""

    def test_non_md_in_kb_structure(self, storage: Storage, gen) -> None:
        # a .png directly under a project layer
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "projects/P/logo.png", "PNG")
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        illegal = [i for i in report.issues if i.type == "illegal"]
        assert any("projects/P/logo.png" in i.path for i in illegal)

    def test_non_md_in_common_knowledge(self, storage: Storage, gen) -> None:
        # a non-.md file inside common-knowledge/
        _write_raw(storage, "common-knowledge/asset.png", "PNG")
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        illegal = [i for i in report.issues if i.type == "illegal"]
        assert any("common-knowledge/asset.png" in i.path for i in illegal)


class TestRefHealthy:
    """B5: healthy refs must not be flagged; _refs/ resolution works."""

    def test_healthy_ref_not_flagged(self, storage: Storage, gen) -> None:
        _write_raw(storage, "common-knowledge/source.md",
                   _healthy_doc("source.md", "# s\n[ok](ref:common-knowledge/target.md)"))
        _write_raw(storage, "common-knowledge/target.md", _healthy_doc("target.md"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        refs = [i for i in report.issues if i.type == "ref"]
        assert not refs

    def test_ref_resolved_via_refs_dir(self, storage: Storage, gen) -> None:
        """A project doc refs an external path that lives in its _refs/ → healthy."""
        (storage.kb_root / "projects" / "P" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        (storage.kb_root / "projects" / "P" / "_refs").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "projects/P/common-knowledge/x.md",
                   _healthy_doc("x.md", "# x\n[ext](ref:ext_context.md)"))
        # target not in KB proper, but present in the project's _refs/ context
        _write_raw(storage, "projects/P/_refs/ext_context.md", _healthy_doc("ext_context.md"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        refs = [i for i in report.issues if i.type == "ref"]
        assert not refs


class TestArchiveLayer:
    """B6: archive/ recursive structure validation."""

    def test_clean_archive_project_no_issues(self, storage: Storage, gen) -> None:
        (storage.kb_root / "archive" / "A" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "archive/A/common-knowledge/ok.md", _healthy_doc("ok.md"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        assert not [i for i in report.issues if i.type in ("position", "illegal")]

    def test_orphan_doc_in_archive_project(self, storage: Storage, gen) -> None:
        (storage.kb_root / "archive" / "A" / "common-knowledge").mkdir(parents=True, exist_ok=True)
        _write_raw(storage, "archive/A/bad.md", _healthy_doc("bad.md"))
        _rebuild_all(gen, storage)
        report = validate_kb(storage, gen)
        pos = [i for i in report.issues if i.type == "position"]
        assert any("archive/A/bad.md" in i.path for i in pos)
