"""文档卡片 hover 预览测试（H1-H5）——覆盖 hover 下拉区：正文预览/ref 链接/引用行/缓存失效/删除按钮。

场景矩阵（S1-S26）之后的独立功能：dashboard 公共知识 + 项目视图「知识」的文档卡片
hover 展开（摘要常显 + 正文预览 + 引用数 + 删除按钮）。

注意：fixture 用【无空格路径】文档（common-knowledge/hover-ref-*.md）——
含空格路径的 ref 链接 marked 不识别为链接、后端 ref 计数也不解码 %20（独立待办），
这里用无空格路径聚焦 hover 功能本身的验证。
"""
import sys
import urllib.parse

sys.path.insert(0, "/Users/chrismoray/Desktop/Moray/MyOpenSource/MyKnowledge_PlatForm/tests/frontend")

import pytest

from conftest import api, backend_doc  # noqa: E402 (同目录 conftest，与 helpers 同法)
from edit_switch_helpers import wait_for_backend  # noqa: E402 (rename 异步轮询，防批量跑时序)

MARKER = "HOVER-UPDATED-2026"
HOVER_A = "common-knowledge/hover-ref-a.md"
HOVER_B = "common-knowledge/hover-ref-b.md"
HOVER_C = "common-knowledge/hover-ref-c.md"


@pytest.fixture
def hover_docs(backend_running):
    """无空格路径的根公共知识文档：A↔B 互引，C 无引用（0 引用场景）"""
    docs = {
        HOVER_A: ("# Hover A\n\n引用 [B](ref:common-knowledge/hover-ref-b.md)\n\nA 正文第一段。\n\n## A 小标题\n\nA 小标题正文。", "hover A 摘要"),
        HOVER_B: ("# Hover B\n\n引用 [A](ref:common-knowledge/hover-ref-a.md)\n\nB 正文。", "hover B 摘要"),
        HOVER_C: ("# Hover C\n\nC 正文，无引用。", "hover C 摘要"),
    }
    for path, (content, summary) in docs.items():
        st, _ = backend_doc(path)
        if st != 200:
            api("POST", f"/api/document/{urllib.parse.quote(path, safe='/')}",
                {"content": content, "summary": summary})
    yield docs
    for path in docs:
        api("DELETE", f"/api/document/{urllib.parse.quote(path, safe='/')}")
    api("POST", "/api/trash/empty")


def _open_dashboard(page, static_url):
    page.goto(f"{static_url}#dashboard")
    page.wait_for_selector(".doc-card", timeout=15000)
    page.wait_for_timeout(1000)


def _hover_card_by_title(page, title_fragment):
    """按标题片段 hover 对应文档卡片（dashboard 公共知识区），返回卡片 locator"""
    for i in range(page.locator(".doc-card").count()):
        t = page.locator(".doc-card").nth(i).locator(".doc-card__title").inner_text()
        if title_fragment in t:
            card = page.locator(".doc-card").nth(i)
            card.hover()
            page.wait_for_timeout(1300)  # 等懒加载（连续 hover 时序敏感，留足时间）
            return card
    raise AssertionError(f"未找到标题含 {title_fragment!r} 的文档卡片")


class TestDocCardHover:
    """H1-H5：文档卡片 hover 预览"""

    def test_h1_preview_renders_parsed_lines(self, static_server, hover_docs, page):
        """H1 hover 卡片 → 正文预览渲染：markdown 解析后文本 + 分行保留"""
        _open_dashboard(page, static_server)
        card = _hover_card_by_title(page, "hover-ref-a")
        body = card.locator(".doc-card__preview__body")
        assert body.count() == 1, "hover 后应出现正文预览"
        text = body.inner_text()
        assert "A 正文第一段" in text, "markdown 正文应被解析进预览"
        assert "A 小标题" in text, "标题应被解析进预览"
        assert "\n" in text, "预览应保留分行（段落/标题各占一行）"

    def test_h2_ref_link_clickable(self, static_server, hover_docs, page):
        """H2 预览内 ref 引用渲染为可点击链接，点击跳转引用文档"""
        _open_dashboard(page, static_server)
        card = _hover_card_by_title(page, "hover-ref-a")
        link = card.locator(".doc-card__preview__body a.ref-link").first
        assert link.count() == 1, "正文里 [B](ref:) 应渲染为可点击引用"
        assert link.inner_text() == "B"
        link.click()
        page.wait_for_timeout(1000)
        after = urllib.parse.unquote(page.evaluate("location.hash"))
        assert "hover-ref-b" in after, f"点击引用应跳转目标文档: {after[:60]}"

    def test_h3_ref_count_conditional(self, static_server, hover_docs, page):
        """H3 引用行条件显示：被引用显示 N，0 引用不显示"""
        _open_dashboard(page, static_server)
        # hover-ref-a 被 hover-ref-b 引用 → 显示「被 1 篇文档引用」
        card = _hover_card_by_title(page, "hover-ref-a")
        refs = card.locator(".doc-card__preview__refs")
        assert refs.count() == 1, "被引用的文档应显示引用行"
        assert "被 1 篇" in refs.inner_text()
        # hover-ref-c 未被引用 → 不显示引用行
        page.mouse.move(5, 5)
        page.wait_for_timeout(400)
        card2 = _hover_card_by_title(page, "hover-ref-c")
        assert card2.locator(".doc-card__preview__refs").count() == 0, "0 引用不应显示引用行"

    def test_h4_preview_updates_after_save(self, static_server, hover_docs, page):
        """H4 编辑保存 → 返回主页 → hover 预览更新（d9659f1 回归：编辑保存→数据一致性）"""
        _open_dashboard(page, static_server)
        card = _hover_card_by_title(page, "hover-ref-a")
        before = card.locator(".doc-card__preview__body").inner_text()
        assert MARKER not in before
        # 模拟编辑保存：内容前加标记（必须开头，预览 200 字截断）
        st, d = backend_doc(HOVER_A)
        assert st == 200
        api("PUT", f"/api/document/{urllib.parse.quote(HOVER_A, safe='/')}",
            {"content": MARKER + "\n\n" + d["content"], "summary": d.get("summary", "")})
        # 返回主页刷新（loadDashboard 触发预览缓存失效）
        page.evaluate("Alpine.store('app').loadDashboard()")
        page.wait_for_timeout(1500)
        page.mouse.move(5, 5)
        page.wait_for_timeout(400)
        card = _hover_card_by_title(page, "hover-ref-a")
        after = card.locator(".doc-card__preview__body").inner_text()
        assert MARKER in after, "编辑保存后 hover 预览应更新为新内容"
        # 恢复内容（避免污染后续用例）
        api("PUT", f"/api/document/{urllib.parse.quote(HOVER_A, safe='/')}",
            {"content": d["content"], "summary": d.get("summary", "")})

    def test_h5_delete_button_opens_modal(self, static_server, hover_docs, page):
        """H5 hover 删除按钮出现 → 点击 → delete-doc 确认模态 → 取消关闭"""
        _open_dashboard(page, static_server)
        card = _hover_card_by_title(page, "hover-ref-a")
        del_btn = card.locator(".doc-card__del")
        assert del_btn.count() == 1, "hover 后应出现删除按钮"
        # 找卡片序号验证 opacity（hover 后应 1）
        for i in range(page.locator(".doc-card").count()):
            if "hover-ref-a" in page.locator(".doc-card").nth(i).locator(".doc-card__title").inner_text():
                idx = i
                break
        opacity = page.evaluate(
            f"getComputedStyle(document.querySelectorAll('.doc-card')[{idx}]"
            f".querySelector('.doc-card__del')).opacity")
        assert opacity == "1", f"hover 后删除按钮应可见（opacity=1），实际 {opacity}"
        del_btn.click()
        page.wait_for_timeout(700)
        modal = page.locator(".modal").filter(has_text="确认删除")
        assert modal.is_visible(), "点击删除应弹 delete-doc 确认模态"
        page.get_by_role("button", name="取消").first.click()
        page.wait_for_timeout(600)
        assert not page.locator(".modal").filter(has_text="确认删除").is_visible(), "取消后模态应关闭"

    def test_h5b_delete_modal_shows_doc_name(self, static_server, hover_docs, page):
        """H5b 卡片删除模态应显示文档名（回归：confirmDeleteCard 传 name 而模态读 title → 文档名空白）"""
        _open_dashboard(page, static_server)
        card = _hover_card_by_title(page, "hover-ref-a")
        card.locator(".doc-card__del").click()
        page.wait_for_timeout(700)
        modal = page.locator(".modal").filter(has_text="删除文档")
        assert modal.is_visible(), "点击删除应弹 delete-doc 确认模态"
        text = modal.inner_text()
        assert "hover-ref-a" in text, f"模态应显示文档名 hover-ref-a（不能空白），实际: {text!r}"
        # 收尾：取消关闭（不执行删除，避免污染 fixture 清理）
        page.get_by_role("button", name="取消").first.click()
        page.wait_for_timeout(600)
        assert not modal.is_visible(), "取消后模态应关闭"

    def test_h5c_delete_confirm_removes_card(self, static_server, hover_docs, page):
        """H5c 卡片删除确认 → 原地刷新不跳转：卡片从列表消失 + 后端 404 + 移入垃圾箱
        （回归：删除后设相同 hash 不触发 hashchange → 卡片残留）"""
        _open_dashboard(page, static_server)
        card = _hover_card_by_title(page, "hover-ref-a")
        card.locator(".doc-card__del").click()
        page.wait_for_timeout(700)
        modal = page.locator(".modal").filter(has_text="删除文档")
        assert modal.is_visible()
        modal.get_by_role("button", name="确认删除").click()
        # 原地刷新：删除 + loadDashboard 异步，等卡片从列表消失
        page.wait_for_timeout(1500)
        titles = [page.locator(".doc-card__title").nth(i).inner_text()
                  for i in range(page.locator(".doc-card").count())]
        assert not any("hover-ref-a" in t for t in titles), "确认删除后卡片应从列表消失（原地刷新）"
        assert any("hover-ref-b" in t for t in titles), "其余文档卡片应仍在列表中"
        # 后端：旧路径 404 + 垃圾箱有该文档（轮询防异步竞态）
        wait_for_backend(HOVER_A, 404)
        st, trash = api("GET", "/api/trash")
        assert st == 200 and "hover-ref-a" in str(trash), "删除的文档应在垃圾箱中"
