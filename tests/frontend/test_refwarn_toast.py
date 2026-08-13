"""保存后引用异常提示（ref_warnings toast）测试——S16 前端消费。

后端 PUT/POST 返回结构化 ref_warnings [{type, ref_path, display_text}]，
前端保存成功后 showRefWarningsToast 提示（少时逐条、多时计数汇总）。
"""
import sys

sys.path.insert(0, "/Users/chrismoray/Desktop/Moray/MyOpenSource/MyKnowledge_PlatForm/tests/frontend")


def _toasts(page):
    return page.evaluate("() => Array.from(document.querySelectorAll('.toast')).map(t => t.textContent)")


class TestRefWarningsToast:
    """ref_warnings toast 文案规则"""

    def test_single_dead(self, static_server, test_docs, page):
        """单个死链 → 逐条文案"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(1200)
        page.evaluate("""() => showRefWarningsToast([{type:'dead', ref_path:'a.md', display_text:'A文档'}])""")
        toasts = _toasts(page)
        assert any("「A文档」引用目标不存在" in t for t in toasts), f"单个死链应逐条提示: {toasts}"

    def test_mixed_two(self, static_server, test_docs, page):
        """死链+垃圾箱 → 混合逐条"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(1200)
        page.evaluate("""() => showRefWarningsToast([
          {type:'dead', ref_path:'a.md', display_text:'A文档'},
          {type:'in_trash', ref_path:'b.md', display_text:'B文档'}])""")
        toasts = _toasts(page)
        assert any("「A文档」引用目标不存在" in t and "「B文档」在垃圾箱（可恢复）" in t for t in toasts), \
            f"混合应逐条并列: {toasts}"

    def test_many_counts(self, static_server, test_docs, page):
        """超过 3 个 → 计数汇总"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(1200)
        page.evaluate("""() => showRefWarningsToast([
          {type:'dead', ref_path:'1', display_text:'一'}, {type:'dead', ref_path:'2', display_text:'二'},
          {type:'dead', ref_path:'3', display_text:'三'}, {type:'in_trash', ref_path:'4', display_text:'四'}])""")
        toasts = _toasts(page)
        assert any("4 个引用异常（3 死链 + 1 在垃圾箱）" in t for t in toasts), \
            f"超过 3 个应计数汇总: {toasts}"

    def test_empty_warning(self, static_server, test_docs, page):
        """empty 类型 → 未填写目标（防御性：导入/历史数据可能带空 ref）"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(1200)
        page.evaluate("""() => showRefWarningsToast([{type:'empty', ref_path:'', display_text:'门店周报'}])""")
        toasts = _toasts(page)
        assert any("「门店周报」未填写目标" in t for t in toasts), f"empty 应提示未填写目标: {toasts}"
