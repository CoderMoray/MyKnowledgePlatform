"""MyKnowledge 前端 — 垃圾箱分页 + 彻底清空修复测试

覆盖：
1. 彻底清空：api.emptyTrash() 请求必须带 ?all=true（修复只 GC 30 天的 bug）
2. 分页加载：loadTrash() 读 {items,total,has_more}；第一页渲染 + trashHasMore 状态
3. 滚动加载：loadMoreTrash() 追加不覆盖 + 防重入/到底；IntersectionObserver 哨兵触发

用 page.route mock /api/trash 返回确定分页数据（不依赖真实垃圾箱内容，无副作用）。
复用 conftest fixtures：static_server / backend_running / page。

运行：PYTHONPATH=. python3 -m pytest tests/frontend/test_trash_pagination.py -q
"""

import json
from playwright.sync_api import expect

API = "http://127.0.0.1:8080"


def _trash_item(i):
    return {
        "type": "doc",
        "name": f"trash-page-{i}.md",
        "original_path": f"projects/X/common-knowledge/trash-page-{i}.md",
        "deleted_at": "2026-08-01T00:00:00",
        "trash_path": f".trash/trash-page-{i}.md",
    }


class TestTrashEmptyAllTrue:
    """彻底清空必须传 ?all=true（后端无参只 GC 30 天）"""

    def test_api_empty_trash_uses_all_true(self):
        """api.js 的 emptyTrash() 请求 URL 含 ?all=true（静态契约）"""
        js = __import__("pathlib").Path(
            __import__("pathlib").Path(__file__).resolve().parents[2],
            "frontend/js/api.js").read_text(encoding="utf-8")
        assert "empty?all=true" in js, "api.emptyTrash() 必须请求 /api/trash/empty?all=true"
        assert "/api/trash/empty?all=true" in js, "api.emptyTrash() 必须带 all=true"
        # 不应存在无参 empty（旧的只 GC 30 天调用）
        assert '"/api/trash/empty", { method: "POST" }' not in js, "不允许无参 emptyTrash"

    def test_empty_trash_sends_all_true(self, static_server, page, backend_running):
        """点击「彻底清空」后，浏览器实际请求 /api/trash/empty?all=true"""
        captured = {}
        page.route(f"{API}/api/trash**", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"items": [_trash_item(0)], "total": 1, "has_more": False})))

        def handle_empty(route):
            captured["url"] = route.request.url
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

        page.route(f"{API}/api/trash/empty**", handle_empty)

        page.goto(f"{static_server}#trash")
        page.wait_for_timeout(2500)
        page.locator("button", has_text="清空垃圾箱").click()
        page.wait_for_timeout(600)
        expect(page.locator(".modal", has_text="清空垃圾箱")).to_be_visible(timeout=3000)
        page.locator("button", has_text="彻底清空").click()
        page.wait_for_timeout(1200)
        assert "all=true" in captured.get("url", ""), f"彻底清空请求应含 all=true，实际: {captured.get('url')}"


class TestTrashPagination:
    """分页加载 + 滚动加载更多"""

    def _route_trash_pages(self, page, total=120):
        """mock /api/trash 分页：每页 50，共 total 条"""
        def handler(route):
            url = route.request.url
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(url).query)
            offset = int(q.get("offset", ["0"])[0])
            limit = int(q.get("limit", ["50"])[0])
            page_items = [_trash_item(i) for i in range(offset, min(offset + limit, total))]
            has_more = (offset + len(page_items)) < total
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"items": page_items, "total": total, "has_more": has_more}))

        page.route(f"{API}/api/trash?**", handler)

    def test_load_first_page_renders(self, static_server, page, backend_running):
        """打开 #trash 加载第一页 50 条；列表渲染 + 加载提示显示（total 120 > 50）"""
        self._route_trash_pages(page)
        page.goto(f"{static_server}#trash")
        page.wait_for_timeout(2500)
        expect(page.locator(".trash-item").first).to_be_attached(timeout=5000)
        count = page.locator(".trash-item").count()
        assert count == 50, f"第一页应 50 条，实际 {count}"
        # 未加载完（50 < 120）显示「加载中…」提示
        expect(page.locator(".trash-list", has_text="加载中…")).to_be_attached(timeout=3000)

    def test_load_more_appends(self, static_server, page, backend_running):
        """滚动到底触发 loadMoreTrash，追加 50 条（50 → 100），不重复"""
        self._route_trash_pages(page)
        page.goto(f"{static_server}#trash")
        page.wait_for_timeout(2500)
        expect(page.locator(".trash-item").first).to_be_attached(timeout=5000)
        assert page.locator(".trash-item").count() == 50
        # 滚动 content-panel 到底触发哨兵
        page.evaluate("document.querySelector('#content-panel').scrollTo(0, document.querySelector('#content-panel').scrollHeight)")
        page.wait_for_timeout(1500)
        count = page.locator(".trash-item").count()
        assert count >= 100, f"滚动加载后应 ≥100 条，实际 {count}"
        # trash_path 唯一天然去重：无重复条目（只取名称 span，排除 .trash-item__type 类型标签）
        names = page.evaluate(
            "Array.from(document.querySelectorAll('.trash-item__name > span:not(.trash-item__type)')).map(e=>e.textContent)")
        assert len(names) == len(set(names)), f"追加后不应有重复条目（{len(names)} 条）"

    def test_store_state_total_has_more(self):
        """store.js 具备 trashTotal/trashHasMore/loadMoreTrash 状态与方法"""
        js = __import__("pathlib").Path(
            __import__("pathlib").Path(__file__).resolve().parents[2],
            "frontend/js/store.js").read_text(encoding="utf-8")
        for sym in ["trashTotal", "trashHasMore", "loadMoreTrash", "trashItems.length", "has_more"]:
            assert sym in js, f"store 缺少分页符号: {sym}"


class TestTrashSelectDelete:
    """多选勾选 → 精准删除选中（body trash_paths；配合后端 /api/trash/empty 契约）"""

    def test_store_has_select_delete_api(self):
        """store/api 静态契约：selectedTrash 状态 + toggle/delete 方法 + deleteTrashItems 调 /api/trash/empty"""
        root = __import__("pathlib").Path(__file__).resolve().parents[2]
        api_js = (root / "frontend/js/api.js").read_text(encoding="utf-8")
        for sym in ["deleteTrashItems", '"/api/trash/empty"', "trash_paths"]:
            assert sym in api_js, f"api.js 缺少多选删除符号: {sym}"
        store_js = (root / "frontend/js/store.js").read_text(encoding="utf-8")
        for sym in ["selectedTrash", "toggleTrashSelect", "toggleTrashSelectAll",
                    "clearTrashSelection", "deleteSelectedTrash"]:
            assert sym in store_js, f"store.js 缺少多选删除符号: {sym}"
        # emptyTrashAction（清空全部）成功后也应清 selectedTrash
        idx = store_js.index("async emptyTrashAction()")
        assert "clearTrashSelection" in store_js[idx:idx + 800], \
            "emptyTrashAction 成功后应清 selectedTrash"

    def test_select_and_delete_selected(self, static_server, page, backend_running):
        """勾选 2 条 → 点「删除选中」→ 请求 body trash_paths 精准匹配 → toast → 刷新第一页（空态）"""
        items = [_trash_item(0), _trash_item(1), _trash_item(2)]
        trash_calls = {"n": 0}

        def handle_trash(route):
            trash_calls["n"] += 1
            body_items = items if trash_calls["n"] == 1 else []  # 删除后刷新返回空（模拟已删）
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"items": body_items, "total": len(body_items),
                                           "has_more": False}))

        page.route(f"{API}/api/trash?**", handle_trash)
        captured = {}

        def handle_delete(route):
            captured["body"] = route.request.post_data
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"status": "ok", "removed": 2}))

        page.route(f"{API}/api/trash/empty**", handle_delete)

        page.goto(f"{static_server}#trash")
        page.wait_for_timeout(2500)
        expect(page.locator(".trash-item").first).to_be_attached(timeout=5000)
        # 勾选第 1、2 条（行内勾选框，表头全选 checkbox 在 .trash-list__toolbar 内不算）
        cbs = page.locator(".trash-item input[type='checkbox']")
        cbs.nth(0).check()
        cbs.nth(1).check()
        # 「删除选中」按钮启用且计数显示 (2)
        btn = page.locator("button", has_text="删除选中")
        expect(btn).to_be_enabled(timeout=3000)
        expect(btn).to_contain_text("(2)")
        btn.click()
        # toast「已删除 2 项」（showToast 默认 duration 900ms，需点击后尽快断言）
        expect(page.locator(".toast", has_text="已删除 2 项")).to_be_visible(timeout=2000)
        # 请求 body trash_paths 精准匹配勾选项（不含未勾选的第 3 条）
        body = json.loads(captured.get("body") or "{}")
        assert set(body.get("trash_paths", [])) == {items[0]["trash_path"], items[1]["trash_path"]}, \
            f"trash_paths 应精准匹配勾选项，实际: {body.get('trash_paths')}"
        # 删除后刷新第一页 → 空状态（列表清空，选中态清除）
        expect(page.locator(".trash-item")).to_have_count(0, timeout=5000)

    def test_select_all_then_delete(self, static_server, page, backend_running):
        """表头全选勾选当前已加载全部 → 删除选中请求 trash_paths 含全部 3 条"""
        items = [_trash_item(0), _trash_item(1), _trash_item(2)]
        trash_calls = {"n": 0}

        def handle_trash(route):
            trash_calls["n"] += 1
            body_items = items if trash_calls["n"] == 1 else []
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"items": body_items, "total": len(body_items),
                                           "has_more": False}))

        page.route(f"{API}/api/trash?**", handle_trash)
        captured = {}

        def handle_delete(route):
            captured["body"] = route.request.post_data
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"status": "ok", "removed": 3}))

        page.route(f"{API}/api/trash/empty**", handle_delete)

        page.goto(f"{static_server}#trash")
        page.wait_for_timeout(2500)
        expect(page.locator(".trash-item").first).to_be_attached(timeout=5000)
        # 表头全选（toolbar 内的 checkbox）
        page.locator(".trash-list__select-all input[type='checkbox']").check()
        # 按钮计数 (3)
        btn = page.locator("button", has_text="删除选中")
        expect(btn).to_contain_text("(3)")
        # 行内勾选框应全部被选中（全选生效于已加载项）
        cbs = page.locator(".trash-item input[type='checkbox']")
        for i in range(3):
            assert cbs.nth(i).is_checked(), f"全选后第 {i} 行应被勾选"
        btn.click()
        expect(page.locator(".toast", has_text="已删除 3 项")).to_be_visible(timeout=2000)
        body = json.loads(captured.get("body") or "{}")
        assert set(body.get("trash_paths", [])) == {i["trash_path"] for i in items}, \
            f"全选删除应含全部已加载 trash_paths，实际: {body.get('trash_paths')}"
