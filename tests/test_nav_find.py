"""Tests for nav__find — full-text search (name + summary + body).

The tool now returns a dict (JSON-serialized by FastMCP into a TextContent).
We parse that JSON back to assert the frozen structure.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.mcp_server import create_mcp_app
from backend.storage import Storage


def _find_json(app, keyword: str) -> dict:
    """Invoke nav__find and parse the returned JSON dict."""
    result = asyncio.run(app.call_tool("nav__find", {"keyword": keyword}))
    text = result[0].text
    return json.loads(text)


@pytest.fixture
def search_storage(storage: Storage, tmp_kb_root: Path) -> Storage:
    """A KB with documents and a project, seeded for full-text search."""
    # documents (doc type)
    storage.write_document(
        "common-knowledge/门店周报.md",
        {"summary": "门店周报模板", "type": "knowledge"},
        "每周填写门店周报数据",
        auto_id=False,
    )
    storage.write_document(
        "common-knowledge/运营周报.md",
        {"summary": "运营数据汇总", "type": "knowledge"},
        "正文提及门店周报相关指标",
        auto_id=False,
    )
    storage.write_document(
        "common-knowledge/无关文档.md",
        {"summary": "完全不相关", "type": "knowledge"},
        "没有任何关键词",
        auto_id=False,
    )
    # a project (project type) via write_readme
    storage.write_readme(
        "projects/门店项目",
        {"name": "门店项目", "summary": "门店相关专项"},
        "# 门店项目\n\n项目正文含门店周报模板",
    )
    return storage


@pytest.fixture
def search_app(search_storage: Storage):
    return create_mcp_app(search_storage)


class TestNavFindStructure:
    def test_returns_dict_with_required_keys(self, search_app) -> None:
        data = _find_json(search_app, "门店周报")
        assert isinstance(data, dict)
        assert set(data.keys()) == {"query", "hint", "results", "total"}
        assert data["query"] == "门店周报"

    def test_body_match_flagged(self, search_app) -> None:
        data = _find_json(search_app, "数据")
        # 运营周报 body contains "数据" via summary too; assert some result has body
        any_body = any("body" in r["matched_in"] for r in data["results"])
        assert any_body

    def test_summary_match_flagged(self, search_app) -> None:
        data = _find_json(search_app, "模板")
        any_summary = any("summary" in r["matched_in"] for r in data["results"])
        assert any_summary

    def test_name_match_flagged(self, search_app) -> None:
        data = _find_json(search_app, "门店周报")
        any_name = any("name" in r["matched_in"] for r in data["results"])
        assert any_name

    def test_score_ordering_full_hit_before_body_only(self, search_app) -> None:
        data = _find_json(search_app, "门店周报")
        scores = [r["score"] for r in data["results"]]
        assert scores == sorted(scores, reverse=True)
        # 门店周报.md hits name+summary+body → 7; 运营周报 hits body only → 1
        names = [r["name"] for r in data["results"]]
        assert names.index("门店周报") < names.index("运营周报")

    def test_type_distinguishes_doc_and_project(self, search_app) -> None:
        data = _find_json(search_app, "门店")
        types = {r["name"]: r["type"] for r in data["results"]}
        assert types["门店周报"] == "doc"
        assert types["门店项目"] == "project"
        # project path must not contain readme.md
        proj = [r for r in data["results"] if r["type"] == "project"][0]
        assert not proj["path"].endswith("readme.md")
        assert proj["path"] == "projects/门店项目"

    def test_empty_result_hint_suggests_refinement(self, search_app) -> None:
        data = _find_json(search_app, "不存在的关键词xyz")
        assert data["total"] == 0
        assert data["results"] == []
        assert "缩短关键词" in data["hint"] or "同义词" in data["hint"]
        assert "nav__list_dir" in data["hint"]

    def test_limit_10_applies(self, storage: Storage) -> None:
        # Seed 12 docs all hitting the same keyword in body
        for i in range(12):
            storage.write_document(
                f"common-knowledge/doc_{i}.md",
                {"summary": f"summary {i}", "type": "knowledge"},
                "公共关键词出现在正文",
                auto_id=False,
            )
        app = create_mcp_app(storage)
        data = _find_json(app, "公共关键词")
        assert len(data["results"]) <= 10

    def test_root_readme_excluded(self, storage: Storage, tmp_kb_root: Path) -> None:
        """根 readme 命中时不应返回 path=''（nav__get_document('') 不可用）。"""
        # build root readme so it matches the keyword
        tmpl = tmp_kb_root / "_templates" / "readme.md"
        tmpl.parent.mkdir(parents=True, exist_ok=True)
        tmpl.write_text("# {{name}}\n\n{{summary}}", encoding="utf-8")
        from backend.readme_generator import ReadmeGenerator
        gen = ReadmeGenerator(storage=storage, template_path=tmpl)
        gen.rebuild("", name="TestKB", summary="门店测试摘要")

        app = create_mcp_app(storage)
        data = _find_json(app, "门店")
        assert data["total"] == 0, f"根 readme 不应作为结果: {data}"
        assert all(r["path"] for r in data["results"]), "所有返回 path 必须非空（可 feed to nav__get_document）"

    def test_layer_index_readme_excluded(self, search_app, storage: Storage) -> None:
        """文档路排除 readme.md 层索引（common-knowledge/readme.md 含关键词不返回）。"""
        storage.write_document(
            "common-knowledge/readme.md",
            {"summary": "门店层索引", "type": "knowledge"},
            "门店关键词在索引里",
            auto_id=False,
        )
        data = _find_json(search_app, "门店索引")
        assert not any(r["path"].endswith("readme.md") for r in data["results"])

    def test_case_insensitive(self, storage: Storage) -> None:
        storage.write_document(
            "common-knowledge/Alpha.md",
            {"summary": "beta summary", "type": "knowledge"},
            "body contains BETA word",
            auto_id=False,
        )
        app = create_mcp_app(storage)
        data = _find_json(app, "alpha")
        assert data["total"] == 1
        assert data["results"][0]["path"] == "common-knowledge/Alpha.md"
        assert "name" in data["results"][0]["matched_in"]

    def test_blank_keyword_returns_empty(self, search_app) -> None:
        data = _find_json(search_app, "")
        assert data["total"] == 0
        assert data["results"] == []
        data2 = _find_json(search_app, "   ")
        assert data2["total"] == 0
