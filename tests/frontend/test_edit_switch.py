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
import urllib.parse

import pytest

from edit_switch_helpers import (
    DOC_MAIN, DOC_SAME, DOC_TARGET, NEW_TITLE, PROJ,
    active_tree_doc, apply_mod, assert_backend_content, assert_backend_summary,
    attach_tracker, backend_doc, delay_route, enter_edit, exit_inplace,
    navigate, open_doc, shown_body, shown_summary, shown_title, toasts,
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
