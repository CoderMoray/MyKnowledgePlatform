"""Tests for S16 — ref 空格路径支持（扫描容错 + 写入规范化 + 写入时存在性校验）。

对照需求验证：
  1. %20 编码空格路径 ref → maint__check_refs 报 normal
  2. 空格原文 ref → 也报 normal（提取统一走链接语法 + 解码）
  3. 引用计数：被引用文档的 /refs 正确包含该引用且 resolved
  4. MCP 写入含空格路径 ref → 落盘 %20 编码
  5. MCP 写入 dead → 警告「不存在」；in_trash → 警告「垃圾箱」；外链 → 无校验提示
  6. ref:path::章节 → target 正确取路径部分
  8. 补充测试：空格路径 ref 分类 + MCP 写入编码 + 存在性校验警告 + rename 双 pattern 联动
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.main import (
    _extract_all_refs,
    check_ref_targets,
    normalize_ref_content,
)
from backend.storage import Storage
from backend.trash import ref_status


# ══════════════════════════════════════════════════════════════
#  Unit — _extract_all_refs：空格路径提取 + %20 解码
# ══════════════════════════════════════════════════════════════


class TestExtractRefsSpaces:
    def test_space_path_extracted(self):
        r = _extract_all_refs("[ref](ref:projects/X 项目/common-knowledge/a.md)")
        assert r == [("ref", "projects/X 项目/common-knowledge/a.md", "")]

    def test_pct20_path_decoded(self):
        r = _extract_all_refs("[ref](ref:projects/X%20项目/common-knowledge/a.md)")
        assert r == [("ref", "projects/X 项目/common-knowledge/a.md", "")]

    def test_pct20_with_section(self):
        r = _extract_all_refs("[标题](ref:projects/X%20项目/a.md::介绍)")
        assert r == [("ref", "projects/X 项目/a.md", "介绍")]

    def test_space_path_with_section(self):
        r = _extract_all_refs("[标题](ref:projects/X 项目/a.md::介绍)")
        assert r == [("ref", "projects/X 项目/a.md", "介绍")]

    def test_external_unchanged(self):
        r = _extract_all_refs("[x](https://a.com/foo bar)")
        assert r == [("external", "https://a.com/foo bar", "x")]


# ══════════════════════════════════════════════════════════════
#  Unit — normalize_ref_content：写入规范化（空格 → %20，幂等）
# ══════════════════════════════════════════════════════════════


class TestNormalizeRefContent:
    def test_space_to_pct20_in_ref(self):
        out = normalize_ref_content("[ref](ref:projects/X 项目/a.md)")
        assert out == "[ref](ref:projects/X%20项目/a.md)"

    def test_section_space_encoded(self):
        out = normalize_ref_content("[t](ref:projects/X 项目/a.md::我的 章节)")
        assert out == "[t](ref:projects/X%20项目/a.md::我的%20章节)"

    def test_idempotent(self):
        out = normalize_ref_content("[t](ref:projects/X%20项目/a.md)")
        assert out == "[t](ref:projects/X%20项目/a.md)"

    def test_plain_text_ref_untouched(self):
        # 非链接语法的 ref:（普通文本）不被规范化
        out = normalize_ref_content("详见 ref:projects/X 项目/a.md 的讨论")
        assert out == "详见 ref:projects/X 项目/a.md 的讨论"

    def test_external_link_untouched(self):
        out = normalize_ref_content("[x](https://a.com/foo bar)")
        assert out == "[x](https://a.com/foo bar)"

    def test_normal_text_untouched(self):
        out = normalize_ref_content("普通 文本 空格")
        assert out == "普通 文本 空格"


# ══════════════════════════════════════════════════════════════
#  Unit — ref_status：%20 / 空格路径分类
# ══════════════════════════════════════════════════════════════


class TestRefStatusSpaces:
    @staticmethod
    def _mk(storage, rel, body="# x"):
        p = storage.kb_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def test_pct20_normal(self, storage):
        self._mk(storage, "projects/X 项目/common-knowledge/a.md")
        assert ref_status(
            storage, "projects/X%20项目/common-knowledge/a.md") == "normal"

    def test_space_normal(self, storage):
        self._mk(storage, "projects/X 项目/common-knowledge/a.md")
        assert ref_status(
            storage, "projects/X 项目/common-knowledge/a.md") == "normal"

    def test_pct20_dead(self, storage):
        assert ref_status(storage, "projects/X%20项目/nope.md") == "dead"

    def test_pct20_in_trash(self, storage):
        from backend.trash import move_doc_to_trash
        self._mk(storage, "common-knowledge/被删.md")
        move_doc_to_trash(storage, "common-knowledge/被删.md")
        assert ref_status(storage, "common-knowledge/被删.md") == "in_trash"


# ══════════════════════════════════════════════════════════════
#  Unit — check_ref_targets：写入时存在性校验警告
# ══════════════════════════════════════════════════════════════


class TestCheckRefTargets:
    @staticmethod
    def _mk(storage, rel, body="# x"):
        p = storage.kb_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def test_normal_no_warning(self, storage):
        self._mk(storage, "common-knowledge/a.md")
        assert check_ref_targets(
            storage, "[x](ref:common-knowledge/a.md)") == []

    def test_dead_warns(self, storage):
        w = check_ref_targets(storage, "[x](ref:common-knowledge/不存在.md)")
        assert len(w) == 1 and "不存在" in w[0]

    def test_in_trash_warns(self, storage):
        from backend.trash import move_doc_to_trash
        self._mk(storage, "common-knowledge/被删.md")
        move_doc_to_trash(storage, "common-knowledge/被删.md")
        w = check_ref_targets(storage, "[x](ref:common-knowledge/被删.md)")
        assert len(w) == 1 and "垃圾箱" in w[0]

    def test_external_skipped(self, storage):
        assert check_ref_targets(storage, "[x](https://a.com)") == []

    def test_empty_target_warns(self, storage):
        w = check_ref_targets(storage, "[x](ref:)")
        assert len(w) == 1 and "为空" in w[0]

    def test_mixed_dead_and_normal(self, storage):
        self._mk(storage, "common-knowledge/ok.md")
        w = check_ref_targets(
            storage,
            "[a](ref:common-knowledge/ok.md) [b](ref:common-knowledge/dead.md)",
        )
        assert len(w) == 1 and "dead.md" in w[0]

    def test_pct20_target_resolves_normal(self, storage):
        self._mk(storage, "projects/X 项目/common-knowledge/a.md")
        assert check_ref_targets(
            storage, "[x](ref:projects/X%20项目/common-knowledge/a.md)") == []


# ══════════════════════════════════════════════════════════════
#  MCP 集成：写入规范化 + 校验警告 + maint__check_refs
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def app(storage: Storage, tmp_kb_root: Path):
    from backend.mcp_server import create_mcp_app
    from backend.readme_generator import ReadmeGenerator

    template = tmp_kb_root / "_templates" / "readme.md"
    template.parent.mkdir(parents=True, exist_ok=True)
    shipped = (Path(__file__).resolve().parent.parent
               / "backend" / "templates" / "readme.md")
    template.write_text(shipped.read_text(), encoding="utf-8")
    gen = ReadmeGenerator(storage=storage, template_path=template)
    gen.rebuild("", name="TestKB", summary="test kb")
    return create_mcp_app(storage, gen=gen)


def _tool_text(result) -> str:
    return result[0][0].text


class TestMCPWriteNormalize:
    def test_create_normalizes_ref_spaces(self, app, storage):
        asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/新.md",
            "content": "[ref](ref:projects/X 项目/common-knowledge/a.md)",
        }))
        _, body = storage.read_document("common-knowledge/新.md")
        assert "ref:projects/X%20项目/common-knowledge/a.md" in body

    def test_update_normalizes_ref_spaces(self, app, storage):
        asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/新.md", "content": "# x",
        }))
        asyncio.run(app.call_tool("write__update_document", {
            "path": "common-knowledge/新.md",
            "content": "[ref](ref:projects/X 项目/a.md)",
        }))
        _, body = storage.read_document("common-knowledge/新.md")
        assert "ref:projects/X%20项目/a.md" in body

    def test_create_warns_dead(self, app):
        result = asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/w.md",
            "content": "[x](ref:common-knowledge/不存在.md)",
        }))
        assert "不存在" in _tool_text(result)

    def test_create_warns_in_trash(self, app, storage):
        from backend.trash import move_doc_to_trash
        (storage.kb_root / "common-knowledge").mkdir(parents=True, exist_ok=True)
        (storage.kb_root / "common-knowledge" / "被删.md").write_text(
            "# x", encoding="utf-8")
        move_doc_to_trash(storage, "common-knowledge/被删.md")
        result = asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/w2.md",
            "content": "[x](ref:common-knowledge/被删.md)",
        }))
        assert "垃圾箱" in _tool_text(result)

    def test_create_external_no_warning(self, app):
        result = asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/w3.md",
            "content": "[x](https://example.com)",
        }))
        msg = _tool_text(result)
        assert "不存在" not in msg
        assert "垃圾箱" not in msg

    def test_create_empty_target_warns(self, app):
        result = asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/w4.md",
            "content": "[x](ref:)",
        }))
        assert "为空" in _tool_text(result)

    def test_check_refs_normal_with_spaces(self, app, storage):
        """验证 1+2：%20 编码与空格原文两种写法都报 normal。"""
        target = "projects/X 项目/common-knowledge/a.md"
        (storage.kb_root / target).parent.mkdir(parents=True, exist_ok=True)
        (storage.kb_root / target).write_text("# a", encoding="utf-8")
        asyncio.run(app.call_tool("write__create_document", {
            "path": "common-knowledge/cite.md",
            "content": (
                "[a](ref:projects/X%20项目/common-knowledge/a.md)\n"
                "[b](ref:projects/X 项目/common-knowledge/a.md)"
            ),
        }))
        result = asyncio.run(app.call_tool("maint__check_refs", {}))
        msg = _tool_text(result)
        assert "已死: 0" in msg
        assert "正常: 2" in msg


# ══════════════════════════════════════════════════════════════
#  REST 集成：写入规范化 + ref_warnings + /refs 端点
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def client(tmp_kb_root: Path):
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


class TestRESTNormalize:
    def test_create_normalizes_and_returns_warnings(self, client, tmp_kb_root):
        r = client.post("/api/document/common-knowledge/r1.md", json={
            "content": "[x](ref:common-knowledge/不存在.md) "
                       "[y](ref:projects/X 项目/a.md)",
            "summary": "s",
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert "ref_warnings" in body
        assert any("不存在" in w for w in body["ref_warnings"])
        _, doc = Storage(kb_root=tmp_kb_root).read_document(
            "common-knowledge/r1.md")
        assert "ref:projects/X%20项目/a.md" in doc

    def test_update_normalizes_and_returns_warnings(self, client, tmp_kb_root):
        client.post("/api/document/common-knowledge/r2.md", json={
            "content": "# old", "summary": "s"})
        r = client.put("/api/document/common-knowledge/r2.md", json={
            "content": "[x](ref:projects/X 项目/a.md)"})
        assert r.status_code == 200, r.text
        assert "ref_warnings" in r.json()
        _, doc = Storage(kb_root=tmp_kb_root).read_document(
            "common-knowledge/r2.md")
        assert "ref:projects/X%20项目/a.md" in doc


class TestRefsEndpointSpaces:
    def test_refs_endpoint_resolves_pct20(self, client, tmp_kb_root):
        """验证 3：被引用文档的 /refs 正确包含该引用且 resolved。"""
        target = "projects/X 项目/common-knowledge/a.md"
        p = tmp_kb_root / target
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# a", encoding="utf-8")
        client.post("/api/document/common-knowledge/引用者.md", json={
            "content": "[a](ref:projects/X%20项目/common-knowledge/a.md)",
            "summary": "s",
        })
        r = client.get("/api/document/common-knowledge/引用者.md/refs")
        assert r.status_code == 200, r.text
        refs = r.json()["refs"]
        assert any(
            x["path"] == "projects/X 项目/common-knowledge/a.md"
            and x["resolved"] is True
            for x in refs
        )


# ══════════════════════════════════════════════════════════════
#  rename 联动：空格路径文档 rename 后，%20 编码 ref 也被替换
# ══════════════════════════════════════════════════════════════


class TestRenameRefReplace:
    def test_rename_document_replaces_pct20_refs(self, storage):
        old = "projects/X 项目/common-knowledge/旧名.md"
        new = "projects/X 项目/common-knowledge/新名.md"
        p = storage.kb_root / old
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# old", encoding="utf-8")
        cite = "common-knowledge/cite.md"
        (storage.kb_root / cite).parent.mkdir(parents=True, exist_ok=True)
        (storage.kb_root / cite).write_text(
            "[a](ref:projects/X%20项目/common-knowledge/旧名.md)\n"
            "[b](ref:projects/X 项目/common-knowledge/旧名.md)",
            encoding="utf-8")

        from backend.mcp_server import rename_document
        msg = rename_document(storage, old, "新名.md")
        assert "已重命名" in msg

        text = (storage.kb_root / cite).read_text(encoding="utf-8")
        assert "ref:projects/X%20项目/common-knowledge/新名.md" in text
        assert "旧名.md" not in text

    def test_rename_project_replaces_pct20_refs(self, storage, tmp_kb_root):
        from backend.mcp_server import rename_project
        from backend.readme_generator import ReadmeGenerator

        template = tmp_kb_root / "_templates" / "readme.md"
        template.parent.mkdir(parents=True, exist_ok=True)
        shipped = (Path(__file__).resolve().parent.parent
                   / "backend" / "templates" / "readme.md")
        template.write_text(shipped.read_text(), encoding="utf-8")

        old = "projects/X 项目"
        old_doc = f"{old}/common-knowledge/a.md"
        (storage.kb_root / old_doc).parent.mkdir(parents=True, exist_ok=True)
        (storage.kb_root / old_doc).write_text("# a", encoding="utf-8")
        gen = ReadmeGenerator(storage=storage, template_path=template)
        gen.rebuild(old)  # 生成项目 readme（active 状态）

        cite = storage.kb_root / "common-knowledge/cite.md"
        cite.parent.mkdir(parents=True, exist_ok=True)
        cite.write_text(
            "[a](ref:projects/X%20项目/common-knowledge/a.md)",
            encoding="utf-8")

        msg = rename_project(storage, old, "Y 项目")
        assert "已重命名" in msg
        text = cite.read_text(encoding="utf-8")
        assert "ref:projects/Y%20项目/common-knowledge/a.md" in text
        assert "X%20项目" not in text
