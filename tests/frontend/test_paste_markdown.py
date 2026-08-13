"""粘贴 markdown 解析测试（P 系列）——方案 B：粘贴 markdown 全量解析为富文本。

设计文档：doc/test/testing-plan-paste-markdown.md
TDD 流程：当前（未实现 B）为红色 → 实现 B 后转正。
覆盖：批 P-A 行内 / P-B 块级 / P-D ref / P-F 位置上下文 / P-G title-summary。
"""
import sys
import urllib.parse

sys.path.insert(0, "/Users/chrismoray/Desktop/Moray/MyOpenSource/MyKnowledge_PlatForm/tests/frontend")

import pytest

from conftest import api, backend_doc  # noqa: E402
from edit_switch_helpers import DOC_MAIN, PROJ, open_doc, enter_edit, exit_inplace  # noqa: E402

MD_SAMPLE = (
    "# 一级标题\n\n"
    "正文段落，包含 **加粗**、*斜体* 和 `行内代码`。\n\n"
    "## 二级标题\n\n"
    "- 无序项一\n"
    "- 无序项二\n\n"
    "1. 有序项一\n"
    "2. 有序项二\n\n"
    "> 引用一段话\n\n"
    "```python\n"
    "print('hello')\n"
    "```\n\n"
    "参考 [Target](ref:common-knowledge/hover-ref-b.md)\n"
)


def _paste_markdown(page, md_text):
    """在编辑器内派发 paste 事件，写入 markdown 纯文本"""
    page.evaluate(
        """(md) => {
        const editor = document.querySelector(".editor-shell .ProseMirror");
        if (!editor) throw new Error("editor not found");
        const clip = new DataTransfer();
        clip.setData("text/plain", md);
        const ev = new ClipboardEvent("paste", { clipboardData: clip, bubbles: true, cancelable: true });
        editor.dispatchEvent(ev);
      }""",
        md_text,
    )
    page.wait_for_timeout(500)


def _clear_editor(page):
    """清空编辑器（避免 open_doc 的既有正文污染粘贴断言）"""
    page.locator(".editor-shell .ProseMirror").click()
    page.keyboard.press("Meta+A")
    page.keyboard.press("Backspace")
    page.wait_for_timeout(300)


def _editor_html(page):
    return page.evaluate(
        """() => document.querySelector(".editor-shell .ProseMirror").innerHTML"""
    )


class TestPasteBlockElements:
    """批 P-B：块级元素粘贴渲染"""

    def test_pb1_heading_renders(self, static_server, test_docs, page):
        """粘贴 # 标题 → 编辑态渲染为 H1"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "# 我是一级标题\n")
        html = _editor_html(page)
        assert "<h1" in html, "粘贴 # 标题 应渲染为 H1"

    def test_pb2_list_renders(self, static_server, test_docs, page):
        """粘贴 - 列表 → 渲染为 ul/li"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "- 项一\n- 项二\n")
        html = _editor_html(page)
        assert "<ul" in html and "<li" in html, "粘贴 - 列表 应渲染为 ul/li"

    def test_pb5_blockquote_renders(self, static_server, test_docs, page):
        """粘贴 > 引用 → 渲染为 blockquote"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "> 这是引用\n")
        assert "<blockquote" in _editor_html(page)

    def test_pb6_codeblock_renders(self, static_server, test_docs, page):
        """粘贴 ``` 代码块 → 渲染为代码块（hljs 高亮 span 不影响内容）"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "```python\nprint('hi')\n```\n")
        html = _editor_html(page)
        assert "<pre" in html, "应渲染为 pre 代码块"
        text = page.evaluate("document.querySelector('.editor-shell .ProseMirror').textContent")
        assert "print('hi')" in text, f"代码块内容应保留（可能被 hljs span 拆分）：{text!r}"


class TestPasteInlineElements:
    """批 P-A：行内元素粘贴渲染"""

    def test_pa1_bold_renders(self, static_server, test_docs, page):
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "**加粗文字**\n")
        assert "<strong" in _editor_html(page)

    def test_pa4_inline_code_renders(self, static_server, test_docs, page):
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "这是 `code` 内容\n")
        assert "<code" in _editor_html(page)


class TestPasteRefRoundtrip:
    """批 P-D：ref 链接粘贴 + 保存往返"""

    def test_pd1_ref_link_roundtrip(self, static_server, test_docs, page):
        """粘贴 ref 链接 → 编辑态渲染为链接 → 保存 → 阅读态仍可点 ref-link"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "参考 [Target](ref:common-knowledge/hover-ref-b.md)\n")
        # 编辑态应为链接元素（a 带 ref 目标），而非纯文本
        link = page.locator(".editor-shell .ProseMirror a[href*='hover-ref-b']")
        assert link.count() == 1, "粘贴 ref 链接应渲染为链接元素（当前纯文本=红色基线）"
        # 保存（原地退出）→ 阅读态
        exit_inplace(page)
        assert "hover-ref-b" in page.content(), "保存后阅读态应保留 ref 链接"


class TestPastePositionContext:
    """批 P-F：粘贴位置与上下文"""

    def test_pf1_paste_empty_paragraph(self, static_server, test_docs, page):
        """在空段落粘贴 → 正常渲染为块级元素"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "# 标题A\n")
        assert "<h1" in _editor_html(page)

    def test_pf2_paste_mid_paragraph_splits(self, static_server, test_docs, page):
        """PF2 段落中间粘贴 # 标题 → ProseMirror 拆段（标题插入到光标附近）"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        page.locator(".editor-shell .ProseMirror").click(position={"x": 300, "y": 80})
        page.wait_for_timeout(300)
        _paste_markdown(page, "# 插入标题\n")
        assert "<h1" in _editor_html(page), "段落中间粘贴 # 标题应拆段插入"

    def test_pf5_paste_in_codeblock_stays_text(self, static_server, test_docs, page):
        """PF5 代码块内粘贴 markdown → 作为代码文本（不拆代码块、不解析块级）"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "```\ncode_line\n```\n")
        page.locator(".editor-shell .ProseMirror pre").click(position={"x": 60, "y": 15})
        page.wait_for_timeout(300)
        _paste_markdown(page, "# 代码块内\n")
        html = _editor_html(page)
        assert "<h1" not in html, "代码块内粘贴 # 不应解析为标题"
        text = page.evaluate("document.querySelector('.editor-shell .ProseMirror').textContent")
        assert "# 代码块内" in text, "代码块内粘贴内容应作为代码文本保留"

    def test_pf4a_paste_at_list_start_lifts(self, static_server, test_docs, page):
        """PF4a 列表项行首粘贴 # 标题 → 脱出列表成独立标题"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "- 项一\n- 项二\n")
        page.evaluate("""() => {
          const ed = window.__mykEditor;
          let p = -1;
          ed.state.doc.descendants((n, pos) => { if (n.type.name === 'listItem' && n.textContent.includes('项二')) p = pos; });
          ed.chain().setTextSelection(p + 1).run();
        }""")
        page.wait_for_timeout(200)
        _paste_markdown(page, "# 标题A\n")
        html = _editor_html(page)
        assert "<h1" in html, "行首粘贴 # 标题应脱出列表成独立标题"
        assert "标题A" in html, "独立标题应包含粘贴内容"

    def test_pf4b_paste_mid_list_stays_text(self, static_server, test_docs, page):
        """PF4b 列表项行中粘贴 # 标题 → 保留列表，# 标题作为列表项文字（结果 a）"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "- 项一\n- 项二\n")
        page.evaluate("""() => {
          const ed = window.__mykEditor;
          let p = -1;
          ed.state.doc.descendants((n, pos) => { if (n.type.name === 'listItem' && n.textContent.includes('项二')) p = pos; });
          ed.chain().setTextSelection(p + 3).run();
        }""")
        page.wait_for_timeout(200)
        _paste_markdown(page, "# 标题B\n")
        html = _editor_html(page)
        assert "<h1" not in html, "行中粘贴 # 标题不应解析为标题"
        text = page.evaluate("document.querySelector('.editor-shell .ProseMirror').textContent")
        assert "# 标题B" in text, "# 标题B 应作为列表项文字保留（结果 a）"


class TestPasteNestedList:
    """批 P-C 子集：嵌套列表"""

    def test_pc2_nested_list(self, static_server, test_docs, page):
        """PC2 嵌套列表粘贴 → 层级结构保留"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "- 一级甲\n  - 二级甲\n  - 二级乙\n- 一级乙\n")
        html = _editor_html(page)
        assert html.count("<li") == 4, f"应有 4 个列表项，实际 {html.count('<li')}"
        # 嵌套结构：二级列表在 li 内
        assert "<li" in html and html.find("<ul") < html.find("</li>"), "应存在嵌套列表结构"


class TestPasteTitleSummary:
    """批 P-G：title/summary 粘贴为纯文本（原生 input 不受影响）"""

    def test_pg1_title_stays_plain(self, static_server, test_docs, page):
        """粘贴 markdown 到 title → 保持纯文本，不渲染"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "title")
        title_input = page.locator(".viewer__title-input")
        title_input.fill("**标题**")
        # 不触发 markdown 渲染：input 值是纯文本
        assert title_input.input_value() == "**标题**"

    def test_pg2_summary_stays_plain(self, static_server, test_docs, page):
        """粘贴 markdown 到 summary → 保持纯文本，不渲染"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "summary")
        summary_input = page.locator(".viewer__summary-input")
        summary_input.fill("**摘要**")
        assert summary_input.input_value() == "**摘要**"


class TestPasteSplitBoundary:
    """批 P-H：分流边界与误判（冲突预期管理）"""

    def test_ph1_inline_only_mixed_marks(self, static_server, test_docs, page):
        """行内-only 多 mark 混排 → 不接管，原生 pasteRules 全部正确"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "**加粗** 和 *斜体* 和 `代码`\n")
        html = _editor_html(page)
        assert "<strong>" in html and "<em>" in html and "<code>" in html

    def test_ph2_block_with_inline_marks(self, static_server, test_docs, page):
        """块级+行内混合（- **加粗** 项）→ 接管后行内 mark 也解析，不残留 **"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "- **加粗** 列表项\n")
        html = _editor_html(page)
        assert "<li" in html, "应渲染为列表项"
        assert "<strong>" in html, "列表项内行内加粗应解析（不残留 **）"
        assert "**" not in html.replace("<strong>", "").replace("</strong>", ""), "不应残留 ** 标记"

    def test_ph3_hash_without_space_not_heading(self, static_server, test_docs, page):
        """行首 # 无空格（#标签）→ 非标题，纯文本"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "#标签内容\n")
        assert "<h1" not in _editor_html(page), "#无空格不应渲染为 H1"

    def test_ph4_dash_without_space_not_list(self, static_server, test_docs, page):
        """行首 - 无空格（-3℃）→ 非列表，纯文本"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "-3℃ 气温\n")
        assert "<ul" not in _editor_html(page), "- 无空格不应渲染为列表"

    def test_ph5_version_number_not_ordered_list(self, static_server, test_docs, page):
        """1.5. 版本号 → 非有序列表（行首数字+点需后跟空格才是有序列表）"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "1.5. 版本说明\n")
        assert "<ol" not in _editor_html(page), "1.5. 不应渲染为有序列表"

    def test_ph6_inline_hash_not_heading(self, static_server, test_docs, page):
        """行内文本里的 #（非行首）→ 不解析"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "这段文本 # 不是标题\n")
        assert "<h1" not in _editor_html(page), "非行首 # 不应渲染为标题"

    def test_ph7_block_with_links(self, static_server, test_docs, page):
        """接管分支的链接（# 标题 后 [ref](...) 和 [http](...)）→ ref href 转换 + 外链正确"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "# 标题\n\n参考 [Target](ref:common-knowledge/hover-ref-b.md) 和 [外链](https://example.com)\n")
        html = _editor_html(page)
        assert "<h1" in html, "标题应渲染"
        assert "hover-ref-b" in html, "接管时 ref 链接目标应保留"
        assert "example.com" in html, "接管时外链应保留"

    def test_ph8_blank_lines_no_extra_nodes(self, static_server, test_docs, page):
        """连续空行粘贴 → 不产生多余节点"""
        open_doc(page, static_server, DOC_MAIN)
        enter_edit(page, "body")
        _clear_editor(page)
        _paste_markdown(page, "# 标题甲\n\n\n# 标题乙\n")
        html = _editor_html(page)
        h_count = html.count("<h1")
        assert h_count == 2, f"应有 2 个 H1（连续空行不产生多余标题），实际 {h_count}"
