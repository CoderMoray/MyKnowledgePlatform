"""Tests for backend/renames.py — rename mapping (S15).

Covers the acceptance criteria:
  1. rename 后 GET 旧路径 → 404 + detail=renamed + redirect_to=新路径；新路径 200
  2. 链式 rename（A→B→C）：GET A 的 redirect_to 应为 C
  3. rename 后删除文档 → GET 旧路径不再返回 renamed
  4. 正常不存在的路径 → not_found；被删除未 rename 的路径 → deleted
  6. 映射文件不影响知识库 git 状态
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.git_manager import GitManager
from backend.renames import (
    RENAMES_FILE,
    mapping_path,
    read_mapping,
    record_rename,
    remove_renames_for,
    resolve_rename,
)
from backend.storage import Storage


# ══════════════════════════════════════════════════════════════
#  Unit tests — mapping file mechanics
# ══════════════════════════════════════════════════════════════


class TestMappingFile:
    def test_writes_hidden_dotfile(self, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        record_rename(storage, "a.md", "b.md")
        assert mapping_path(tmp_kb_root).is_file()
        data = json.loads(mapping_path(tmp_kb_root).read_text(encoding="utf-8"))
        assert data == {"a.md": "b.md"}

    def test_dotfile_not_listed(self, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        record_rename(storage, "a.md", "b.md")
        names = [e.name for e in storage.list_children("")]
        assert RENAMES_FILE not in names

    def test_corrupt_file_reads_empty(self, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        mapping_path(tmp_kb_root).write_text("{not json", encoding="utf-8")
        assert read_mapping(storage) == {}

    def test_record_never_raises_on_corrupt_file(self, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        mapping_path(tmp_kb_root).write_text("{not json", encoding="utf-8")
        record_rename(storage, "a.md", "b.md")  # must not raise
        assert read_mapping(storage) == {"a.md": "b.md"}


class TestRecordRename:
    def test_simple_record(self, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        record_rename(storage, "a.md", "b.md")
        assert read_mapping(storage) == {"a.md": "b.md"}

    def test_folds_chain_on_write(self, tmp_kb_root: Path):
        """A→B then B→C: A is re-pointed directly to C."""
        storage = Storage(kb_root=tmp_kb_root)
        record_rename(storage, "a.md", "b.md")
        record_rename(storage, "b.md", "c.md")
        mapping = read_mapping(storage)
        assert mapping == {"a.md": "c.md", "b.md": "c.md"}


class TestResolveRename:
    def test_none_without_mapping(self, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        assert resolve_rename(storage, "x.md") is None

    def test_resolves_when_target_exists(self, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        (tmp_kb_root / "common-knowledge").mkdir(parents=True)
        (tmp_kb_root / "common-knowledge" / "b.md").write_text(
            "# b", encoding="utf-8")
        record_rename(storage, "common-knowledge/a.md",
                      "common-knowledge/b.md")
        assert resolve_rename(storage, "common-knowledge/a.md") == \
            "common-knowledge/b.md"

    def test_none_when_target_missing(self, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        record_rename(storage, "a.md", "b.md")  # b.md never created
        assert resolve_rename(storage, "a.md") is None

    def test_follows_chain_to_live_target(self, tmp_kb_root: Path):
        """A→B→C (unfolded, e.g. external edit) still resolves A→C."""
        storage = Storage(kb_root=tmp_kb_root)
        (tmp_kb_root / "c.md").write_text("# c", encoding="utf-8")
        record_rename(storage, "a.md", "b.md")
        # 手工构造未折叠的链（模拟外部编辑或旧版本文件）
        mapping = read_mapping(storage)
        mapping["b.md"] = "c.md"
        mapping_path(tmp_kb_root).write_text(
            json.dumps(mapping), encoding="utf-8")
        assert resolve_rename(storage, "a.md") == "c.md"

    def test_cycle_guard(self, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        mapping_path(tmp_kb_root).write_text(
            json.dumps({"a.md": "b.md", "b.md": "a.md"}), encoding="utf-8")
        assert resolve_rename(storage, "a.md") is None


class TestRemoveRenamesFor:
    def test_removes_key_and_value(self, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        # 手工构造未折叠的链：a→b、b→c；删除 b 后两条都失效
        mapping_path(tmp_kb_root).write_text(
            json.dumps({"a.md": "b.md", "b.md": "c.md"}), encoding="utf-8")
        remove_renames_for(storage, "b.md")
        assert read_mapping(storage) == {}

    def test_noop_when_no_match(self, tmp_kb_root: Path):
        storage = Storage(kb_root=tmp_kb_root)
        record_rename(storage, "a.md", "b.md")
        remove_renames_for(storage, "zzz.md")
        assert read_mapping(storage) == {"a.md": "b.md"}


# ══════════════════════════════════════════════════════════════
#  Integration tests — REST API
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def client(tmp_kb_root: Path):
    """FastAPI test client bound to a temp KB (same pattern as test_main)."""
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.main import get_storage as _orig_get_storage
    from backend.readme_generator import ReadmeGenerator

    storage = Storage(kb_root=tmp_kb_root)
    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    if not template.exists():
        template.write_text("# {name}\n\n{summary}", encoding="utf-8")
    gen = ReadmeGenerator(storage=storage, template_path=template)

    def _test_storage():
        return storage, gen

    import backend.main
    backend.main.get_storage = _test_storage
    yield TestClient(app)
    backend.main.get_storage = _orig_get_storage


def _create_doc(client, path: str, body: str = "# 内容") -> None:
    r = client.post(f"/api/document/{path}",
                    json={"content": body, "summary": "测试"})
    assert r.status_code == 201, r.text


def _rename(client, path: str, new_name: str):
    return client.put("/api/document/rename",
                      json={"path": path, "new_name": new_name})


class TestApiRenameRedirect:
    def test_rename_old_path_redirects_new_path_ok(self, client):
        _create_doc(client, "common-knowledge/旧名.md")
        r = _rename(client, "common-knowledge/旧名.md", "新名.md")
        assert r.status_code == 200, r.text

        # GET 旧路径 → 404 + renamed + redirect_to
        old = client.get("/api/document/common-knowledge/旧名.md")
        assert old.status_code == 404
        body = old.json()
        assert body["detail"]["detail"] == "renamed"
        assert body["detail"]["redirect_to"] == "common-knowledge/新名.md"

        # GET 新路径 → 200
        new = client.get("/api/document/common-knowledge/新名.md")
        assert new.status_code == 200

    def test_chained_rename_redirects_to_final(self, client):
        _create_doc(client, "common-knowledge/A.md")
        assert _rename(client, "common-knowledge/A.md", "B.md").status_code == 200
        assert _rename(client, "common-knowledge/B.md", "C.md").status_code == 200

        old = client.get("/api/document/common-knowledge/A.md")
        assert old.status_code == 404
        body = old.json()
        assert body["detail"]["detail"] == "renamed"
        assert body["detail"]["redirect_to"] == "common-knowledge/C.md"

    def test_rename_then_delete_old_path_no_redirect(self, client):
        _create_doc(client, "common-knowledge/A.md")
        assert _rename(client, "common-knowledge/A.md", "B.md").status_code == 200

        # 删除 B（新路径）→ 映射清理 → A 不再跳转
        r = client.delete("/api/document/common-knowledge/B.md")
        assert r.status_code == 200, r.text

        old = client.get("/api/document/common-knowledge/A.md")
        assert old.status_code == 404
        body = old.json()
        assert body["detail"]["detail"] != "renamed"
        assert "redirect_to" not in body["detail"]

    def test_never_existed_path_still_not_found(self, client):
        r = client.get("/api/document/common-knowledge/不存在.md")
        assert r.status_code == 404
        assert r.json()["detail"]["detail"] == "not_found"

    def test_deleted_without_rename_still_deleted(self, client, tmp_kb_root):
        """被删除但未 rename 的路径 → deleted（git 追踪后删除）"""
        _create_doc(client, "common-knowledge/被删.md")
        gm = GitManager(tmp_kb_root)
        gm.init()
        gm.commit("init")

        r = client.delete("/api/document/common-knowledge/被删.md")
        assert r.status_code == 200, r.text
        # REST 删除不 commit；_deleted_detail 依赖 git log，先提交一次模拟真实流程
        gm.commit("deleted")

        r = client.get("/api/document/common-knowledge/被删.md")
        assert r.status_code == 404
        body = r.json()
        assert body["detail"]["detail"] == "deleted"
        assert "deleted_at" in body["detail"]


class TestMCPRenameTool:
    def test_write__rename_document_records_mapping(self, tmp_kb_root: Path):
        """MCP 工具 write__rename_document 与 REST 共用底层，映射同样记录。"""
        import asyncio

        from backend.mcp_server import create_mcp_app
        from backend.readme_generator import ReadmeGenerator

        storage = Storage(kb_root=tmp_kb_root)
        template = tmp_kb_root / "_templates" / "readme.md"
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_text("# {name}\n\n{summary}", encoding="utf-8")
        gen = ReadmeGenerator(storage=storage, template_path=template)

        storage.write_document(
            "common-knowledge/旧名.md", {"summary": "s"}, "# x")
        app = create_mcp_app(storage, gen=gen)
        result = asyncio.run(app.call_tool(
            "write__rename_document",
            {"path": "common-knowledge/旧名.md", "new_name": "新名.md"}))
        assert "已重命名" in result[0][0].text
        assert read_mapping(storage) == {
            "common-knowledge/旧名.md": "common-knowledge/新名.md"}


class TestGitCleanliness:
    def test_mapping_file_does_not_affect_git_status(self, tmp_kb_root: Path):
        """验证 6：映射文件不进 git，rename 后 git status 干净。"""
        storage = Storage(kb_root=tmp_kb_root)
        (tmp_kb_root / "common-knowledge").mkdir(parents=True)
        storage.write_document(
            "common-knowledge/旧名.md",
            {"summary": "测试"}, "# 内容", auto_id=True)

        gm = GitManager(tmp_kb_root)
        gm.init()
        gm.commit("init")

        from backend.mcp_server import rename_document
        msg = rename_document(storage, "common-knowledge/旧名.md", "新名.md")
        assert "已重命名" in msg

        # 映射文件已生成且被 git 忽略
        assert mapping_path(tmp_kb_root).is_file()
        exclude = tmp_kb_root / ".git" / "info" / "exclude"
        assert exclude.exists()
        assert RENAMES_FILE in exclude.read_text(encoding="utf-8").splitlines()

        # 映射文件从未被 git 追踪、未出现在 status、文档树无未提交改动
        status = gm._run("status", "--porcelain")
        assert RENAMES_FILE not in status
        tracked = gm._run("ls-files")
        assert RENAMES_FILE not in tracked
        assert "common-knowledge/" not in status
