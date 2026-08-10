"""编辑态 ↔ 导航切换：批 1 场景自动化（S1-S10 + S4b-e 原地保存补充）

把"手测常规方法"参数化为场景矩阵——每个场景一个测试函数，共享公共操作：
    open_doc → enter_edit(入口) → apply_mod(修改) → navigate/exit_inplace(退出)
    → assert_*(保存/残留/rename/高亮/toast/加载次数)

覆盖四类盲区（2026-08-09 复盘结论）：
  ① 过程断言（ApiTracker 加载/保存次数）  ② 周边 UI（侧栏树名/项目页卡片名）
  ③ 原地保存退出方式（S4b-e）           ④ 竞态注入（delay_route，S2-race）

运行：PYTHONPATH=. python -m pytest tests/frontend/test_edit_switch.py -v
前置：后端 8080 运行（.myknowledge_test 测试库）；测试文档自动创建/清理。
"""
import time
import urllib.parse

import pytest

from edit_switch_helpers import (
    DOC_MAIN, DOC_SAME, DOC_SUB, DOC_TARGET, NEW_TITLE, PROJ, SUB_PROJ,
    active_tree_doc, apply_mod, assert_backend_content, assert_backend_summary,
    attach_tracker, backend_doc, click_toc, delete_doc_from_edit, delay_route,
    enter_edit, exit_inplace, inject_lock, mock_409, navigate, open_doc,
    release_lock, shown_body, shown_summary, shown_title,
    toggle_project_chevron, toasts,
)

MARKER = "AUTO-MARKER-2026"


# ═══════════════════════════════════════════════════════════════════════
# 批 1：核心场景（手测已通过，固化为自动化）
# ═══════════════════════════════════════════════════════════════════════
class TestBatch1:
    def test_s1_basic_switch_none(self, static_server, test_docs, page):
        """S1 E1+M0→T1：A 零变化保存、B 渲染正确、高亮 B+父级"""
        open_doc(page, static_server, DOC_MAIN)
        tracker = attach_tracker(page)
        enter_edit(page, "body")                 # E1
        apply_mod(page, "none")                  # M0
        tracker.reset()
        navigate(page, "doc_same")               # T1
        assert shown_title(page) == "test-edit-auto-same"
        assert active_tree_doc(page) == DOC_SAME
        tracker.assert_document_loads(DOC_SAME, 1, label="S1 切到 same")
        tracker.assert_method_count("PUT", 1, "document", label="S1 保存")

    def test_s2_body_saved_no_residue(self, static_server, test_docs, page):
        """S2 E1+M1→T1：A 正文已保存；B 无 A 残留"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body")                  # M1 改正文
        navigate(page, "doc_same")
        assert_backend_content(DOC_MAIN, MARKER)          # A 已保存
        assert MARKER not in shown_body(page)              # B 无残留
        assert "Auto Same" in shown_body(page)

    def test_s3_rename(self, static_server, test_docs, page):
        """S3 E1+M2→T1：A 合法 rename；B 正常"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "title")                 # M2 改标题 → rename
        navigate(page, "doc_same")
        new_path = f"{PROJ}/common-knowledge/{NEW_TITLE}.md"
        st, _ = backend_doc(new_path)
        assert st == 200, f"rename 后新路径应存在: {new_path}"
        st_old, _ = backend_doc(DOC_MAIN)
        assert st_old != 200, "旧路径应不存在"
        # toast 生命周期 ~900ms，切走后可能已消失——收集到才校验文案
        if toasts(page):
            assert any("已重命名为" in t for t in toasts(page)), f"toast 异常: {toasts(page)}"
        assert shown_title(page) == "test-edit-auto-same"

    def test_s4_summary_saved_not_polluted(self, static_server, test_docs, page):
        """S4 E1+M3→T1：A 摘要已保存、不被 B 污染"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "summary")               # M3 改摘要
        navigate(page, "doc_same")
        assert_backend_summary(DOC_MAIN, "AUTO-新摘要")
        assert shown_summary(page) == "同项目摘要", f"B 摘要被污染: {shown_summary(page)!r}"

    def test_s4b_summary_inplace_no_rollback(self, static_server, test_docs, page):
        """S4b：改摘要 → 原地保存（不切走）→ 显示=后端（防回滚，1920998）"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "summary")
        exit_inplace(page)                       # 原地保存
        assert shown_summary(page) == "AUTO-新摘要"
        assert_backend_summary(DOC_MAIN, "AUTO-新摘要")

    def test_s4c_summary_multi_inplace(self, static_server, test_docs, page):
        """S4c：连续 3 次原地保存，每次显示=后端（防累积回滚）"""
        open_doc(page, static_server, DOC_MAIN)
        for i in range(1, 4):
            enter_edit(page, "body")
            page.fill(".viewer__summary-input", f"AUTO-摘要{i}")
            page.wait_for_timeout(150)
            exit_inplace(page)
            assert shown_summary(page) == f"AUTO-摘要{i}", f"第{i}次回滚"
            assert_backend_summary(DOC_MAIN, f"AUTO-摘要{i}")

    def test_s4d_body_inplace(self, static_server, test_docs, page):
        """S4d：改正文 → 原地保存 → 正文不回滚（htmlContent 快照）"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body")
        exit_inplace(page)
        assert MARKER in shown_body(page), "正文原地保存后回滚"
        assert_backend_content(DOC_MAIN, MARKER)

    def test_s4e_title_inplace_rename(self, static_server, test_docs, page):
        """S4e：改标题 → 原地保存（rename）→ 标题/hash 更新、刷新不 404"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "title")
        exit_inplace(page)
        assert shown_title(page) == NEW_TITLE
        cur = urllib.parse.unquote(page.evaluate("location.hash"))
        assert NEW_TITLE in cur, f"hash 未更新: {cur[:80]}"
        page.reload()
        page.wait_for_timeout(2000)
        assert shown_title(page) == NEW_TITLE, "刷新后标题不对（可能 404）"

    def test_s5_project_highlight(self, static_server, test_docs, page):
        """S5 E1+M0→T3：A 保存关编辑；项目页正常；高亮=项目行 active"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "none")
        navigate(page, "project")
        proj_active = page.locator(".sidebar-item--active .sidebar-item__name").inner_text() \
            if page.locator(".sidebar-item--active .sidebar-item__name").count() else ""
        assert "MyKnowledge" in proj_active, f"项目行未高亮: {proj_active!r}"

    def test_s6_dashboard_no_residue(self, static_server, test_docs, page):
        """S6 E1+M1→T5：A 保存；仪表盘正常；无高亮残留"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body")
        navigate(page, "dashboard")
        assert_backend_content(DOC_MAIN, MARKER)
        assert page.locator(".sidebar-tree__item--active").count() == 0, "仪表盘残留高亮"

    def test_s7_back_keeps_changes(self, static_server, test_docs, page):
        """S7 E1+M1→T8：back 回 A：修改保留、编辑已关"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body")
        navigate(page, "doc_same")
        navigate(page, "back")
        assert_backend_content(DOC_MAIN, MARKER)
        assert MARKER in shown_body(page), "back 回 A 修改丢失"
        assert page.evaluate("Alpine.store('app').currentView") == "view", "back 后仍在编辑态"

    def test_s8_cross_project(self, static_server, test_docs, page):
        """S8 E1+M0→T2：跨项目正常、target 高亮+父级"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "none")
        navigate(page, "doc_cross")
        assert shown_title(page) == "test-edit-auto-target"
        assert active_tree_doc(page) == DOC_TARGET

    def test_s9_quick_switch_no_residue(self, static_server, test_docs, page):
        """S9 E1+M1→T1→T2：快速连续切换：无残留、竞态安全"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body")
        navigate(page, "doc_same")      # A→same
        navigate(page, "doc_cross")     # same→target
        assert MARKER not in shown_body(page), "连续切换残留 main 内容"
        assert "Auto Target" in shown_body(page)
        assert_backend_content(DOC_MAIN, MARKER)

    def test_s10_ref_link(self, static_server, test_docs, page):
        """S10 E1+M0→T7：引用链接：A 保存、target 加载"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "none")
        exit_inplace(page)               # 退出编辑（E1+M0 保存）
        navigate(page, "ref")            # 点 ref 链接 → target
        page.wait_for_timeout(1500)
        assert shown_title(page) == "test-edit-auto-target", f"ref 跳转失败: {shown_title(page)!r}"

    def test_s2_race_delayed_save(self, static_server, test_docs, page):
        """竞态注入：保存响应晚于加载返回 → 内容残留（febf2b8 回归，修复前必现）"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body")
        delay_route(page, "PUT", "MyKnowledge", 1.2)  # 延迟保存 main 的响应
        navigate(page, "doc_cross")
        page.wait_for_timeout(2500)
        assert MARKER not in shown_body(page), "竞态残留 main 内容"
        assert "Auto Target" in shown_body(page)
        assert_backend_content(DOC_MAIN, MARKER)


# ═══════════════════════════════════════════════════════════════════════
# 简单冒烟：确认测试框架本身可用（跑批 1 前先跑这个）
# ═══════════════════════════════════════════════════════════════════════
class TestFramework:
    def test_fixtures_ready(self, static_server, test_docs, page):
        """fixtures（后端/静态服务/浏览器/测试文档）就绪"""
        open_doc(page, static_server, DOC_MAIN)
        assert shown_title(page) == "test-edit-auto-main"


# ═══════════════════════════════════════════════════════════════════════
# 新建文档：归属选择器（全量候选 + 无垃圾项 + 搜索触发）——逻辑检查，不靠肉眼
# ═══════════════════════════════════════════════════════════════════════
class TestNewDocParent:
    """归属下拉：候选全量数、垃圾项过滤、滚动加载、搜索触发（用户强调'逻辑检查'）"""

    EXPECTED_CANDIDATES = {
        "公共知识",
        "MyKnowledge 项目知识管理平台",
        "产品分发与部署",
        "前端设计与开发",
        "后端设计与开发",
        "Training 人员培训",
        "AEP（销售能力评估）项目学习报告",
    }
    RESERVED_BAD = {"archive", "common-knowledge", "projects", "readme.md"}

    def _open_picker(self, page, static_server):
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(2500)
        page.locator(".sidebar-new-btn").click()
        page.wait_for_selector("input[x-model='newDocName']", timeout=5000)
        page.wait_for_timeout(1500)  # 等 _ensureProjectTree + readme 摘要拉取

    def _scroll_picker_to_bottom(self, page):
        """滚动下拉到底，触发分页加载（+5/次），返回当前候选数"""
        page.locator("input[x-model='newDocParentName']").click()
        page.wait_for_timeout(400)
        lst = page.locator(".parent-picker__list")
        lst.hover()
        for _ in range(8):
            page.mouse.wheel(0, 300)
            page.wait_for_timeout(100)
        return page.locator(".parent-picker__item").count()

    def _candidate_labels(self, page):
        return [
            page.locator(".parent-picker__item").nth(i).locator(".parent-picker__label").inner_text().strip()
            for i in range(page.locator(".parent-picker__item").count())
        ]

    def test_candidates_full_set_no_garbage(self, static_server, test_docs, page):
        """滚动到底后候选 = 7 个项目（公共知识+6），无 archive/common-knowledge/projects 垃圾项"""
        self._open_picker(page, static_server)
        n = self._scroll_picker_to_bottom(page)
        labels = set(self._candidate_labels(page))
        assert n >= len(self.EXPECTED_CANDIDATES), f"候选应 ≥7，实际 {n}: {labels}"
        assert labels == self.EXPECTED_CANDIDATES, (
            f"候选集合不匹配\n  期望: {self.EXPECTED_CANDIDATES}\n  实际: {labels}")
        bad = labels & self.RESERVED_BAD
        assert not bad, f"候选含保留名垃圾项: {bad}"

    def test_candidate_summary_displayed(self, static_server, test_docs, page):
        """下拉项第二行显示项目摘要（非空），公共知识显示根 readme 摘要"""
        self._open_picker(page, static_server)
        page.locator("input[x-model='newDocParentName']").click()
        page.wait_for_timeout(500)
        n = page.locator(".parent-picker__item").count()
        assert n >= 5, f"点击打开应有浏览候选，实际 {n}"
        # 至少部分候选有摘要（readme summary）
        summaries = [
            page.locator(".parent-picker__item").nth(i).locator(".parent-picker__path").inner_text().strip()
            for i in range(n)
        ]
        non_empty = [s for s in summaries if s]
        assert non_empty, f"所有候选摘要都为空: {summaries}"
        # 公共知识候选（第一项）摘要 = 根 readme 摘要
        assert summaries[0], f"公共知识候选摘要应为根 readme 摘要: {summaries[0]!r}"

    def test_search_triggers_on_type(self, static_server, test_docs, page):
        """输入文字触发 kind=projects 搜索并更新候选（用户场景：输入'公共知识'/'MyKnowledge'）"""
        self._open_picker(page, static_server)
        requests = []
        page.on("request", lambda r: requests.append(r.url) if "/api/search" in r.url else None)
        # 用户场景：默认归属是"公共知识"（长度 4），输入同长度"公共知识"也应触发搜索
        inp = page.locator("input[x-model='newDocParentName']")
        assert inp.input_value() == "公共知识", f"默认归属应为公共知识: {inp.input_value()!r}"
        # 点击（不搜索，打开浏览）→ 输入"公共知识"
        inp.click()
        page.wait_for_timeout(300)
        inp.fill("公共知识")
        page.wait_for_timeout(1000)
        search_hits = [u for u in requests if urllib.parse.unquote(u).find("q=公共知识") >= 0]
        assert search_hits, f"输入'公共知识'应触发搜索请求，实际: {requests}"
        labels = self._candidate_labels(page)
        assert "公共知识" in labels, f"搜索结果应含公共知识: {labels}"
        # 再输入"MyKnowledge"（替换 → 也触发）
        requests.clear()
        inp.fill("MyKnowledge")
        page.wait_for_timeout(1000)
        search_hits2 = [u for u in requests if urllib.parse.unquote(u).find("q=MyKnowledge") >= 0]
        assert search_hits2, f"输入'MyKnowledge'应触发搜索请求，实际: {requests}"
        labels2 = self._candidate_labels(page)
        assert "MyKnowledge 项目知识管理平台" in labels2, f"搜索结果应含 MyKnowledge: {labels2}"

    def test_delete_also_triggers_search(self, static_server, test_docs, page):
        """删除文字也触发搜索（用户新需求：任何文本变动都该触发）"""
        self._open_picker(page, static_server)
        requests = []
        page.on("request", lambda r: requests.append(r.url) if "/api/search" in r.url else None)
        inp = page.locator("input[x-model='newDocParentName']")
        inp.click()
        page.wait_for_timeout(300)
        # 先输入完整词触发一次搜索
        inp.fill("MyKnowledge")
        page.wait_for_timeout(1000)
        n_before = len(requests)
        # 删除一部分 → 应再次触发搜索
        inp.fill("MyKnow")
        page.wait_for_timeout(1000)
        search_hits = [u for u in requests[n_before:] if urllib.parse.unquote(u).find("q=MyKnow") >= 0]
        assert search_hits, f"删除文字应触发搜索（用户新需求），新增请求: {requests[n_before:]}"
        # 删空 → 回浏览模式
        requests.clear()
        inp.fill("")
        page.wait_for_timeout(600)
        assert page.locator(".parent-picker__item").count() >= 5, "删空应回浏览候选"

    def test_no_duplicate_loads_on_reopen(self, static_server, test_docs, page):
        """多次开关弹窗不重复加载项目树（缓存守卫）；快速输入合并搜索请求（debounce 防重）"""
        reqs = []
        page.on("request", lambda r: reqs.append(r.url) if "/api/" in r.url and r.method == "GET" else None)
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(2500)
        page.locator(".sidebar-new-btn").click()
        page.wait_for_selector("input[x-model='newDocName']", timeout=5000)
        page.wait_for_timeout(1800)  # 等项目树 + readme 摘要拉取
        n1_list = len([u for u in reqs if "/list/" in u])
        n1_readme = len([u for u in reqs if "readme" in u])
        # 关闭再打开：缓存应生效（0 新 list/readme 请求）
        page.evaluate('Alpine.store("app").closeModal()')
        page.wait_for_timeout(400)
        page.locator(".sidebar-new-btn").click()
        page.wait_for_selector("input[x-model='newDocName']", timeout=5000)
        page.wait_for_timeout(1200)
        n2_list = len([u for u in reqs if "/list/" in u])
        n2_readme = len([u for u in reqs if "readme" in u])
        assert n2_list == n1_list, f"二次打开不应重新加载项目树: list {n1_list}→{n2_list}"
        assert n2_readme == n1_readme, f"二次打开不应重拉 readme 摘要: {n1_readme}→{n2_readme}"
        # 快速逐字输入：debounce 合并成 1 个搜索请求（只发最终词）
        search_urls = [u for u in reqs if "/api/search" in u]
        reqs.clear()
        inp = page.locator("input[x-model='newDocParentName']")
        inp.click()
        page.wait_for_timeout(200)
        for ch in "MyKnowledge":
            inp.type(ch, delay=50)  # 50ms < 300ms debounce
        page.wait_for_timeout(1500)
        search_now = [u for u in reqs if "/api/search" in u]
        assert len(search_now) == 1, f"快速输入应合并为 1 个搜索请求，实际 {len(search_now)}: {search_now}"
        final_q = urllib.parse.unquote(search_now[0].split("q=")[1].split("&")[0])
        assert final_q == "MyKnowledge", f"应只发最终词 MyKnowledge，实际 q={final_q}"

    def test_special_chars_no_injection(self, static_server, test_docs, page):
        """特殊字符搜索词无 XSS/正则注入（转义渲染 + 无弹窗 + 无 JS 错误）"""
        self._open_picker(page, static_server)
        dialogs = []
        page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        inp = page.locator("input[x-model='newDocParentName']")
        inp.click()
        page.wait_for_timeout(300)
        for evil in ["[abc", "(x|y)", "*wild", "a\\b",
                     "<script>alert(1)</script>", '&"><img src=x onerror=alert(2)>']:
            inp.fill(evil)
            page.wait_for_timeout(900)
            assert not dialogs, f"XSS 被执行: {dialogs}"
        # 最终无匹配 → 占位正常显示（说明搜索链路无 JS 崩溃）
        assert page.locator(".parent-picker__empty").is_visible(), "特殊字符应无匹配并显示占位"

    def test_click_without_change_does_not_search(self, static_server, test_docs, page):
        """点击输入框（内容未变）不触发搜索，只打开浏览候选"""
        self._open_picker(page, static_server)
        requests = []
        page.on("request", lambda r: requests.append(r.url) if "/api/search" in r.url else None)
        inp = page.locator("input[x-model='newDocParentName']")
        inp.click()
        page.wait_for_timeout(500)
        assert not requests, f"点击（内容未变）不应触发搜索: {requests}"
        assert page.locator(".parent-picker__item").count() >= 5, "点击应打开浏览候选"

    def test_no_match_shows_placeholder(self, static_server, test_docs, page):
        """输入无匹配 → 显示'未找到匹配项目'占位（不是空壳下拉）；有匹配/浏览时占位隐藏"""
        self._open_picker(page, static_server)
        inp = page.locator("input[x-model='newDocParentName']")
        inp.click()
        page.wait_for_timeout(300)
        empty = page.locator(".parent-picker__empty")
        # 无匹配 → 占位可见
        inp.fill("zzz不存在的项目")
        page.wait_for_timeout(1000)
        assert page.locator(".parent-picker__item").count() == 0, "无匹配不应有候选"
        assert empty.is_visible(), "无匹配应显示占位提示"
        assert "未找到匹配项目" in empty.inner_text()
        # 有匹配 → 占位隐藏
        inp.fill("Training")
        page.wait_for_timeout(1000)
        assert page.locator(".parent-picker__item").count() >= 1, "有匹配应有候选"
        assert not empty.is_visible(), "有匹配时占位应隐藏"
        # 删空回浏览 → 占位隐藏
        inp.fill("")
        page.wait_for_timeout(400)
        assert page.locator(".parent-picker__item").count() >= 5, "删空应回浏览候选"
        assert not empty.is_visible(), "浏览模式占位应隐藏"


# ═══════════════════════════════════════════════════════════════════════
# 创建后跳转编辑态（1f8b15b 三 bug 固化）——"两个必须补的空白"之一
# ① router 直达 #edit/ 并触发 enterEdit（编辑态真正打开，不靠点击）
# ② 标题/摘要输入框正确填充（修复'创建后摘要空'）
# ③ sidebar 刷新出现新文档行（修复'创建后侧栏无新文档'）
# ═══════════════════════════════════════════════════════════════════════
def _cleanup_new_doc(path):
    """删除创建测试的文档（DELETE + 清空垃圾箱）"""
    try:
        from conftest import api
        api("DELETE", f"/api/document/{urllib.parse.quote(path, safe='/')}")
        api("POST", "/api/trash/empty")
    except Exception:
        pass


class TestNewDocCreate:
    """新建文档 → 创建后跳转编辑态（创建流程端到端，用户要求'不靠肉眼'）"""

    def _open_new_modal(self, page, static_server):
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(2500)
        page.locator(".sidebar-new-btn").click()
        page.wait_for_selector("input[x-model='newDocName']", timeout=5000)
        page.wait_for_timeout(1200)  # 等 _ensureProjectTree + readme 摘要拉取

    def _fill_and_create(self, page, name, summary, parent_label):
        page.fill("input[x-model='newDocName']", name)
        page.fill("input[x-model='newDocSummary']", summary)
        inp = page.locator("input[x-model='newDocParentName']")
        inp.click()
        page.wait_for_timeout(300)
        inp.fill(parent_label)
        page.wait_for_timeout(1000)  # 等 kind=projects 搜索返回候选
        item = page.locator(".parent-picker__item", has_text=parent_label)
        assert item.count() >= 1, f"归属候选应匹配 {parent_label!r}"
        item.first.click()
        page.wait_for_timeout(300)
        page.get_by_role("button", name="创建文档").click()
        page.wait_for_selector(".viewer__title-input", timeout=10000)  # 等进入编辑态
        page.wait_for_timeout(1500)  # 等侧栏树自动展开/刷新

    def test_create_training_enters_edit_with_values(self, static_server, backend_running, page):
        """归属=Training：创建后直达编辑态、标题/摘要填充、sidebar 出现新文档"""
        name = f"test-create-{int(time.time() * 1000)}"
        summary = f"AUTO-创建摘要-{int(time.time())}"
        parent = "Training 人员培训"
        path = f"projects/{parent}/common-knowledge/{name}.md"
        try:
            self._open_new_modal(page, static_server)
            self._fill_and_create(page, name, summary, parent)
            # ① hash 直达 #edit/（router 直达，非点击进入）
            cur = urllib.parse.unquote(page.evaluate("location.hash"))
            assert cur.startswith("#edit/"), f"创建后应跳转 #edit/: {cur[:80]}"
            # ① 编辑态真正打开：enterEdit 生效（标题输入框可见）
            title_inp = page.locator(".viewer__title-input")
            assert title_inp.count() and title_inp.is_visible(), "创建后应进入编辑态（标题输入框可见）"
            # ② 标题/摘要输入框正确填充（不是空——修复点）
            assert title_inp.input_value().strip() == name, f"标题输入框: {title_inp.input_value()!r}"
            summ_inp = page.locator(".viewer__summary-input")
            assert summ_inp.input_value().strip() == summary, f"摘要输入框: {summ_inp.input_value()!r}"
            # ③ sidebar 树出现新文档行（修复点）
            row = page.locator(f'.sidebar-tree__item[data-doc-path="{path}"]')
            assert row.count() >= 1, "sidebar 未出现新文档行（refreshProjectTree/自动展开失效）"
            # API 对比：后端存在 + 摘要正确
            st, d = backend_doc(path)
            assert st == 200, f"后端应有新文档: {path}"
            assert (d or {}).get("summary") == summary, f"后端摘要: {(d or {}).get('summary')!r}"
        finally:
            _cleanup_new_doc(path)

    def test_create_default_parent_root(self, static_server, backend_running, page):
        """默认归属'公共知识'（根 readme）→ 创建到根 common-knowledge，直达编辑态"""
        name = f"test-create-root-{int(time.time() * 1000)}"
        summary = "AUTO-根摘要"
        path = f"common-knowledge/{name}.md"
        try:
            self._open_new_modal(page, static_server)
            # 不动归属输入（默认"公共知识" → value=common-knowledge）
            page.fill("input[x-model='newDocName']", name)
            page.fill("input[x-model='newDocSummary']", summary)
            page.get_by_role("button", name="创建文档").click()
            page.wait_for_selector(".viewer__title-input", timeout=10000)
            page.wait_for_timeout(1000)
            cur = urllib.parse.unquote(page.evaluate("location.hash"))
            assert cur.startswith("#edit/"), f"应跳转 #edit/: {cur[:80]}"
            title_inp = page.locator(".viewer__title-input")
            assert title_inp.count() and title_inp.is_visible(), "默认归属创建后应进入编辑态"
            assert title_inp.input_value().strip() == name
            summ_inp = page.locator(".viewer__summary-input")
            assert summ_inp.input_value().strip() == summary, f"摘要输入框: {summ_inp.input_value()!r}"
            st, d = backend_doc(path)
            assert st == 200, f"根 common-knowledge 应有新文档: {path}"
        finally:
            _cleanup_new_doc(path)


# ═══════════════════════════════════════════════════════════════════════
# 批 2：边界场景（S11-S20）——基建：子项目 fixture + TOC/chevron helper
# ═══════════════════════════════════════════════════════════════════════
class TestBatch2:
    """批 2：边界场景。复用批 1 的 enter_edit/apply_mod/navigate 公共操作。"""

    def test_s11_title_focus_switch_no_rename(self, static_server, test_docs, page):
        """S11 E2+M0→T1：标题输入框聚焦时切换——输入框值=污染源，必须不 rename"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "title")              # E2（标题框聚焦，值未改）
        apply_mod(page, "none")                # M0
        navigate(page, "doc_same")             # T1
        st, _ = backend_doc(DOC_MAIN)
        assert st == 200, "标题框聚焦切走不应 rename（原路径应存在）"
        assert shown_title(page) == "test-edit-auto-same"

    def test_s12_summary_focus_switch_not_polluted(self, static_server, test_docs, page):
        """S12 E3+M0→T1：摘要输入框聚焦时切换——summary 不被污染"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "summary")            # E3
        apply_mod(page, "none")                # M0
        navigate(page, "doc_same")             # T1
        assert shown_summary(page) == "同项目摘要", f"摘要被污染: {shown_summary(page)!r}"
        st, d = backend_doc(DOC_MAIN)
        assert st == 200 and (d or {}).get("summary") == "主文档摘要"

    def test_s13_subproject_page_highlight(self, static_server, subproject_docs, page):
        """S13 E1+M0→T4：子项目页正常 + 高亮（子项目行 active）"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "none")
        navigate(page, "subproject")           # T4
        # 子项目页渲染：子项目文档卡片出现
        cards = page.locator(".doc-card__title", has_text="test-edit-auto-sub")
        assert cards.count() >= 1, "子项目页应显示子项目文档卡片"
        # 高亮：子项目行 active-project（text+bg），顶层 Training 行非 active
        sub_active = page.locator(f'[data-sub-path="{SUB_PROJ}"].sidebar-tree__item--active-project')
        assert sub_active.count() == 1, f"子项目行应 active-project，实际 {sub_active.count()}"
        train_item = page.locator(".sidebar-project").filter(
            has=page.locator(".sidebar-item__name", has_text="Training 人员培训"))
        assert train_item.locator(".sidebar-item--active").count() == 0, "顶层行不应 active"

    def test_s14_trash_no_residue(self, static_server, test_docs, page):
        """S14 E1+M0→T6：垃圾箱正常进入、A 已保存关编辑"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "none")
        navigate(page, "trash")                # T6
        assert page.evaluate("Alpine.store('app').currentView") == "trash"
        assert page.locator(".sidebar-tree__item--active").count() == 0, "垃圾箱残留文档高亮"

    @pytest.mark.xfail(
        strict=True,
        reason="S15 已知历史 bug：rename 后历史栈未更新——_maybeRename 的 replaceState 在"
               "await 后判断 hash 已切走而跳过，back 回旧路径 #doc/旧名（后端 404），"
               "bfcache 恢复旧 DOM 显示旧标题。完整修复需后端 rename 映射（old→new）支持，待排期。",
    )
    def test_s15_rename_then_back(self, static_server, test_docs, page):
        """S15 E1+M2→T8：改标题后 back——rename 生效且路由/视图一致（历史 bug，当前 xfail）"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "title")               # M2 → rename（replaceState 改当前历史项为 #doc/新路径）
        navigate(page, "doc_same")             # 切走（新历史项）
        navigate(page, "back")                 # back → 回 rename 后的 A（历史项已被 replaceState 改写）
        page.wait_for_timeout(1500)
        title = shown_title(page)
        assert title == NEW_TITLE, f"back 后应显示 rename 后文档（新标题），实际: {title!r}"
        # 路由/视图一致：hash 指向新路径，后端新路径存在
        cur = urllib.parse.unquote(page.evaluate("location.hash"))
        assert NEW_TITLE in cur, f"hash 应指向 rename 后路径: {cur[:80]}"

    def test_s16_body_title_combo(self, static_server, test_docs, page):
        """S16 E1+M4→T1：改正文+标题——都保存 + rename"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body_title")          # M4
        navigate(page, "doc_same")             # T1
        new_path = f"{PROJ}/common-knowledge/{NEW_TITLE}.md"
        st, d = backend_doc(new_path)
        assert st == 200, "rename 后新路径应存在"
        assert MARKER in (d or {}).get("content", ""), "正文修改应保存"
        st_old, _ = backend_doc(DOC_MAIN)
        assert st_old != 200, "旧路径应不存在"
        assert shown_title(page) == "test-edit-auto-same"

    def test_s17_url_switch_saves(self, static_server, test_docs, page):
        """S17 E1+M1→T9：直接改 URL——A 保存、B 从外部链接加载正常"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body")
        navigate(page, "url")                  # T9：hash 直接改到 DOC_SAME
        assert_backend_content(DOC_MAIN, MARKER)
        assert shown_title(page) == "test-edit-auto-same"

    def test_s18_reenter_edit_loop(self, static_server, test_docs, page):
        """S18 E1+M0→A(再进)：同文档重复进出编辑（edit→view→edit）不异常"""
        open_doc(page, static_server, DOC_MAIN)
        for i in range(3):
            enter_edit(page, "body")
            apply_mod(page, "none")
            exit_inplace(page)
        assert page.evaluate("Alpine.store('app').currentView") == "view", "最终应回 view 态"
        assert shown_title(page) == "test-edit-auto-main"

    def test_s19_toc_click_keeps_edit(self, static_server, test_docs, page):
        """S19 编辑态点目录 TOC：同文档滚动跳转、不退出编辑、高亮不错乱"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        page.wait_for_selector("[data-toc-jump]", timeout=8000)
        n_toc = page.locator("[data-toc-jump]").count()
        assert n_toc >= 2, f"测试文档应有多级标题（H1/H2/H3），TOC 实际 {n_toc} 项"
        click_toc(page, 1)                     # 点"二级标题甲"
        assert page.locator(".viewer__title-input").is_visible(), "点 TOC 不应退出编辑"
        assert page.evaluate("Alpine.store('app').currentView") == "edit"

    def test_s20_chevron_keeps_edit(self, static_server, test_docs, page):
        """S20 编辑态点项目树 chevron：展开/收起、编辑状态保持、展开后高亮恢复"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        was, now = toggle_project_chevron(page, "MyKnowledge 项目知识管理平台")
        assert was != now, "chevron 应切换展开状态"
        assert page.locator(".viewer__title-input").is_visible(), "点 chevron 不应退出编辑"
        assert page.evaluate("Alpine.store('app').currentView") == "edit"
        # 再展开 → 高亮恢复当前文档
        was2, now2 = toggle_project_chevron(page, "MyKnowledge 项目知识管理平台")
        assert now2 == was, "再次点击应回到原展开状态"
        assert active_tree_doc(page) == DOC_MAIN, f"展开后高亮应恢复: {active_tree_doc(page)!r}"


# ═══════════════════════════════════════════════════════════════════════
# 批 3：异常/竞态场景（S21-S26）——注入 helper：inject_lock/mock_409/delete_doc_from_edit
# ═══════════════════════════════════════════════════════════════════════
class TestBatch3:
    """批 3：异常/竞态。S21/S23/S25 用注入 helper，S24 用 subproject_docs，S22/S26 现有 helper 直接拼。"""

    def test_s21_locked_blocks_switch(self, static_server, test_docs, page):
        """S21 isLocked 时切换应被阻止——不保存不切、内容不丢"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        # 改正文后【立即】锁注入——用快速路径（不能走 apply_mod：其 200ms 等待 + 全量
        # 回归 CPU 忙时，autosave 的 1s 定时器可能先于锁生效触发保存，测试不稳定）
        page.locator(".editor-shell .ProseMirror").click(position={"x": 300, "y": 300})
        page.keyboard.press("Control+End")
        page.keyboard.type(f"\n\n{MARKER}", delay=5)
        inject_lock(page)
        assert page.evaluate("Alpine.store('app').isLocked") is True, "锁注入未生效"
        # 尝试切走（侧栏点击）
        page.locator(f'.sidebar-tree__item[data-doc-path="{DOC_SAME}"]').click()
        page.wait_for_timeout(1500)
        # 锁定时编辑内容不应被保存/丢失：后端 A 不应有 MARKER（保存被锁阻止）
        st, d = backend_doc(DOC_MAIN)
        assert st == 200
        assert MARKER not in (d or {}).get("content", ""), "锁定时不应保存成功（编辑被锁保护）"
        release_lock(page)

    def test_s22_quick_roundtrip(self, static_server, test_docs, page):
        """S22 A→B→A 快速往返：A 第二次显示已保存内容；无 rename/污染"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body")
        navigate(page, "doc_same")     # A→B
        navigate(page, "back")         # B→A
        assert MARKER in shown_body(page), "back 回 A 修改丢失"
        assert shown_title(page) == "test-edit-auto-main"
        assert_backend_content(DOC_MAIN, MARKER)

    def test_s23_delete_from_edit(self, static_server, test_docs, page):
        """S23 编辑态点删除：按钮保留可见 → 自动退出编辑保存 → 确认删除进垃圾箱，无误 rename"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body")        # 有修改 → 退出编辑时应先保存
        delete_doc_from_edit(page, confirm=True)
        # 删除成功：后端 404 + 垃圾箱有该文档 + 无 rename 残留
        st, _ = backend_doc(DOC_MAIN)
        assert st != 200, "删除后原路径应不存在"
        # toast：已移入垃圾箱
        if toasts(page):
            assert any("垃圾箱" in t for t in toasts(page)), f"toast 异常: {toasts(page)}"

    def test_s24_deep_doc_auto_expand(self, static_server, subproject_docs, page):
        """S24 深层文档自动展开：进入子项目文档 → 树自动展开（Training→子项目）且高亮正确"""
        open_doc(page, static_server, DOC_SUB)
        page.wait_for_timeout(1200)    # 等自动展开链
        # Training 顶层展开 + 子项目行存在 + 当前文档行高亮
        assert page.evaluate(f"Alpine.store('app').isProjectExpanded('{SUB_PROJ}')") is True, \
            "进入深层文档应自动展开子项目"
        sub_row = page.locator(f'[data-sub-path="{SUB_PROJ}"]')
        assert sub_row.count() == 1, "子项目行应存在（树自动展开）"
        assert active_tree_doc(page) == DOC_SUB, f"高亮应为深层文档: {active_tree_doc(page)!r}"

    def test_s25_409_conflict_keeps_edit(self, static_server, test_docs, page):
        """S25 保存 409 冲突：弹 diff 模态、编辑内容不丢、保持编辑态"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body")
        mock_409(page)                 # PUT → 409
        exit_inplace(page)             # 触发保存 → 409
        assert page.locator("#conflict-modal").is_visible(), "409 应弹冲突 diff 模态"
        assert MARKER in shown_body(page), "409 后编辑内容不应丢失"
        assert page.evaluate("Alpine.store('app').currentView") == "edit", "冲突时应保持编辑态"

    def test_s26_five_rapid_switches(self, static_server, test_docs, page):
        """S26 连续 5 次快速切换：无累积残留、最终文档正确、A 已保存"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        apply_mod(page, "body")
        for i in range(5):
            navigate(page, "doc_same" if i % 2 == 0 else "doc_cross")
        # 最终文档正确 + 无残留
        assert MARKER not in shown_body(page), "快速切换后残留 main 内容"
        assert shown_title(page) in ("test-edit-auto-same", "test-edit-auto-target")
        assert_backend_content(DOC_MAIN, MARKER)
