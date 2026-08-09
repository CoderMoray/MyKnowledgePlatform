"""Tests for share.py — publish + import_share."""

from __future__ import annotations

from pathlib import Path

import pytest

import shutil

from backend.readme_generator import ReadmeGenerator
from backend.share import publish, import_share
from backend.storage import Storage, dump_frontmatter


def _clone_project(src_storage: Storage, dst_storage: Storage,
                   project_rel: str) -> None:
    """Copy a project from *src_storage* to *dst_storage*."""
    src_dir = src_storage.kb_root / project_rel
    dst_dir = dst_storage.kb_root / project_rel
    dst_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(src_dir), str(dst_dir))





@pytest.fixture
def storage_with_project(storage: Storage, tmp_kb_root: Path) -> Storage:
    """KB with a project that has one doc."""
    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
    template.write_text(shipped.read_text(), encoding="utf-8")

    gen = ReadmeGenerator(storage=storage, template_path=template)
    gen.rebuild("", name="TestKB", summary="test kb", status="active")

    proj_dir = tmp_kb_root / "projects" / "TestProject"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "common-knowledge").mkdir()
    (proj_dir / "projects").mkdir()

    body = dump_frontmatter(
        {"id": "proj_test", "name": "TestProject", "summary": "a test project",
         "status": "active"},
        "# Test",
    )
    storage.write_readme("projects/TestProject", {}, body)
    storage.write_document(
        "projects/TestProject/common-knowledge/doc.md",
        {"summary": "test doc"}, "# doc body",
    )
    return storage


class TestPublish:
    def test_creates_mkpkg(self, storage_with_project: Storage,
                           tmp_kb_root: Path) -> None:
        result = publish(storage_with_project, "projects/TestProject")
        pkg = Path(result)
        assert pkg.exists()
        assert pkg.suffix == ".mkpkg"
        assert "TestProject" in pkg.name

    def test_package_contains_data(self, storage_with_project: Storage,
                                   tmp_kb_root: Path) -> None:
        result = publish(storage_with_project, "projects/TestProject")
        pkg = Path(result)
        assert pkg.stat().st_size > 100  # non-trivial

    def test_nonexistent_project(self, storage: Storage,
                                 tmp_kb_root: Path) -> None:
        # 路径校验层（storage 存在性检查）先于打包拒绝
        with pytest.raises((ValueError, FileNotFoundError)):
            publish(storage, "projects/nope")


class TestImportShare:
    def test_import_roundtrip(self, storage_with_project: Storage,
                              tmp_kb_root: Path) -> None:
        # Publish
        pkg_path = publish(storage_with_project, "projects/TestProject")

        # Create a second KB and import into it
        kb2 = tmp_kb_root / "_imported"
        kb2.mkdir()
        storage2 = Storage(kb_root=kb2)
        from backend.config import set_identity
        set_identity("test@example.com", "TestUser")

        msg = import_share(storage2, pkg_path)
        assert "TestProject" in msg

        # Verify files exist
        dest = kb2 / "projects" / "TestProject"
        assert dest.is_dir()
        assert (dest / "readme.md").is_file()
        assert (dest / "common-knowledge" / "doc.md").is_file()

    def test_import_different_identity(self, storage_with_project: Storage,
                                       tmp_kb_root: Path) -> None:
        """Import works regardless of the importer's identity."""
        pkg_path = publish(storage_with_project, "projects/TestProject")

        from backend.config import set_identity
        set_identity("other@test.com", "Other")
        msg = import_share(
            Storage(kb_root=tmp_kb_root / "kb2"),
            pkg_path,
        )
        assert "TestProject" in msg

    def test_merge_identical(self, storage_with_project: Storage,
                             tmp_kb_root: Path) -> None:
        """Re-import same project → all skip, no conflicts."""
        pkg_path = publish(storage_with_project, "projects/TestProject")

        # Import a second time into the same KB
        msg = import_share(storage_with_project, pkg_path)
        assert "无变化" in msg
        assert "新增" not in msg

    def test_merge_new_file(self, storage_with_project: Storage,
                            tmp_kb_root: Path) -> None:
        """Import adds a new file not in local → detected as added."""
        from backend.config import set_identity
        set_identity("test@example.com", "TestUser")

        # Create target KB that has the project WITHOUT the new file
        kb_tgt = tmp_kb_root / "target"
        kb_tgt.mkdir()
        st_tgt = Storage(kb_root=kb_tgt)
        _clone_project(storage_with_project, st_tgt, "projects/TestProject")

        # Create a new package that includes ONE EXTRA file
        storage_with_project.write_document(
            "projects/TestProject/common-knowledge/new_file.md",
            {"summary": "new"}, "# New content",
        )
        pkg = publish(storage_with_project, "projects/TestProject")

        # Import into target — new_file.md should be detected as "added"
        msg = import_share(st_tgt, pkg)
        assert "新增" in msg
        assert "new_file" in msg

    def test_merge_deleted_detected(self, storage_with_project: Storage,
                                    tmp_kb_root: Path) -> None:
        """Local file not in import → reported as deleted."""
        storage_with_project.write_document(
            "projects/TestProject/common-knowledge/local.md",
            {"summary": "local"}, "# local",
        )
        pkg_path = publish(storage_with_project, "projects/TestProject")

        # Delete the local file and re-import
        (tmp_kb_root / "projects/TestProject/common-knowledge/local.md").unlink()
        # Re-create it for the merge detection
        storage_with_project.write_document(
            "projects/TestProject/common-knowledge/another.md",
            {"summary": "another"}, "# another",
        )
        pkg_path2 = publish(storage_with_project, "projects/TestProject")

        # Remove the new one too, keep only original
        (tmp_kb_root / "projects/TestProject/common-knowledge/another.md").unlink()
        storage_with_project.write_document(
            "projects/TestProject/common-knowledge/local.md",
            {"summary": "local"}, "# local",
        )

        msg = import_share(storage_with_project, pkg_path)
        assert "本地有但导入包中无" in msg

    @staticmethod
    def _malicious_pkg(name: str) -> bytes:
        """Build a decryptable .mkpkg whose manifest claims *name*."""
        import io, json, struct, tarfile
        from backend.share import _derive_key, _encrypt
        manifest = {
            "name": name,
            "project_id": "x" * 40,
            "exported_at": "2026-01-01",
            "author_nickname": "Evil",
            "author_email_hash": "h" * 12,
        }
        key = _derive_key(manifest)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo(f"{name}/readme.md")
            data = b"# evil"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        encrypted = _encrypt(buf.getvalue(), key)
        manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        return struct.pack(">I", len(manifest_bytes)) + manifest_bytes + encrypted

    def test_import_rejects_malicious_project_name(
            self, tmp_kb_root: Path) -> None:
        """包内项目名是不可信输入：穿越/空名/含斜杠在解包前即被拒绝。"""
        kb = tmp_kb_root / "kb"
        kb.mkdir()
        storage = Storage(kb_root=kb)
        for bad in ["../evil", "", "P/common-knowledge"]:
            pkg = tmp_kb_root / "evil.mkpkg"
            pkg.write_bytes(self._malicious_pkg(bad))
            with pytest.raises(ValueError, match="拒绝导入"):
                import_share(storage, str(pkg))

    def test_publish_rejects_bad_project_rel(self, storage: Storage,
                                             tmp_kb_root: Path) -> None:
        from backend.share import publish
        with pytest.raises(ValueError):
            publish(storage, "common-knowledge/xx")

    def test_find_external_refs_ignores_traversal(self,
                                                  storage: Storage) -> None:
        """_find_external_refs 必须忽略穿越 ref，防止把 KB 外文件打进分享包。"""
        from backend.share import _find_external_refs
        storage.write_document(
            "projects/TestProject/common-knowledge/a.md",
            {"summary": "s"},
            "# a\n\n[恶意](ref:../../../../etc/passwd)\n[恶意2](ref:../secret.md)")
        refs = _find_external_refs(storage.kb_root, "projects/TestProject")
        assert refs == {}

    def test_find_external_refs_keeps_legal(self, storage: Storage) -> None:
        """合法的 KB 内外部 ref 仍被收录为上下文。"""
        from backend.share import _find_external_refs
        storage.write_document("common-knowledge/术语表.md",
                               {"summary": "t"}, "# 术语表")
        storage.write_document(
            "projects/TestProject/common-knowledge/a.md",
            {"summary": "s"},
            "# a\n\n[合法](ref:common-knowledge/术语表.md)")
        refs = _find_external_refs(storage.kb_root, "projects/TestProject")
        assert "common-knowledge/术语表.md" in refs

    def test_import_sanitizes_author_nick(self, tmp_kb_root: Path) -> None:
        """冲突文件名的昵称部分必须清洗路径分隔符，防层级污染。"""
        import io, json, struct, tarfile
        from backend.share import (_derive_key, _encrypt, import_share)
        kb = tmp_kb_root / "kb"
        kb.mkdir()
        storage = Storage(kb_root=kb)
        storage.write_document("projects/P/common-knowledge/a.md",
                               {"summary": "s", "maintainer": "A"}, "# a")
        # 包内同文件 maintainer=B（冲突），昵称含路径分隔符
        manifest = {"name": "P", "project_id": "x" * 40,
                    "exported_at": "2026-01-01",
                    "author_nickname": "../EVIL", "author_email_hash": "h" * 12}
        key = _derive_key(manifest)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            body = b"---\nid: a\nsummary: s\nmaintainer: B\n---\n# changed"
            info = tarfile.TarInfo("P/common-knowledge/a.md")
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
        enc = _encrypt(buf.getvalue(), key)
        mb = json.dumps(manifest).encode("utf-8")
        pkg = tmp_kb_root / "evil.mkpkg"
        pkg.write_bytes(struct.pack(">I", len(mb)) + mb + enc)

        report = import_share(storage, str(pkg))
        # 冲突文件已生成（昵称 ../EVIL 清洗为 .._EVIL，路径分隔符不生效），无穿越
        conflict = kb / "projects" / "P" / "common-knowledge" / "a（来自.._EVIL）.md"
        assert conflict.exists()
        assert not (kb.parent / "EVIL.md").exists()

    def test_publish_with_context(self, storage_with_project: Storage,
                                   tmp_kb_root: Path) -> None:
        """publish --with-context includes external refs in _refs/."""
        from backend.config import set_identity
        set_identity("test@example.com", "TestUser")

        # Create an external doc at root common-knowledge
        storage_with_project.write_document(
            "common-knowledge/external_ref.md",
            {"summary": "external"}, "# External ref doc",
        )
        # Add a ref to it from the project
        storage_with_project.write_document(
            "projects/TestProject/common-knowledge/main.md",
            {"summary": "main"},
            "See [ext](ref:common-knowledge/external_ref.md).",
            auto_id=False,
        )

        pkg_path = publish(storage_with_project, "projects/TestProject",
                           with_context=True)

        # Import into a fresh KB and check _refs/ exists
        from backend.storage import Storage
        kb2 = tmp_kb_root / "imported"
        kb2.mkdir()
        st2 = Storage(kb_root=kb2)
        msg = import_share(st2, pkg_path)
        assert "已导入" in msg

        refs_dir = kb2 / "projects" / "TestProject" / "_refs"
        assert refs_dir.is_dir()
        ref_file = refs_dir / "common-knowledge" / "external_ref.md"
        assert ref_file.is_file()
        assert "External" in ref_file.read_text()

    def test_merge_conflict_different_maintainer(
            self, storage_with_project: Storage,
            tmp_kb_root: Path) -> None:
        """Content differs + different maintainer → conflict."""
        pkg_path = publish(storage_with_project, "projects/TestProject")

        # Modify local file with different maintainer
        doc_path = "projects/TestProject/common-knowledge/doc.md"
        storage_with_project.write_document(
            doc_path,
            {"summary": "doc", "maintainer": "Local <local@test.com>"},
            "# Local edit", auto_id=False,
        )

        msg = import_share(storage_with_project, pkg_path)
        assert "冲突" in msg

    def test_import_with_explicit_email(self, storage_with_project: Storage,
                                        tmp_kb_root: Path) -> None:
        pkg_path = publish(storage_with_project, "projects/TestProject")

        from backend.config import set_identity
        # First set identity unchanged, import with explicit email
        set_identity("other@test.com", "Other")
        msg = import_share(
            Storage(kb_root=tmp_kb_root / "kb3"),
            pkg_path,
            sharer_email="test@example.com",
        )
        assert "TestProject" in msg
