"""编辑切换测试 公共操作/断言 helper（纯函数，fixtures 见 conftest.py）

把"手测常规方法"沉淀为可复用操作：
    open_doc → enter_edit(入口) → apply_mod(修改) → navigate(切走)/exit_inplace(原地保存)
    → assert_*(保存/残留/高亮/toast/加载次数)
"""
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROJ = "projects/MyKnowledge 项目知识管理平台"
DOC_MAIN = f"{PROJ}/common-knowledge/test-edit-auto-main.md"
DOC_SAME = f"{PROJ}/common-knowledge/test-edit-auto-same.md"
DOC_TARGET = "projects/Training 人员培训/common-knowledge/test-edit-auto-target.md"
NEW_TITLE = "test-edit-auto-renamed"

from conftest import backend_doc  # noqa: E402  (fixtures 同目录 conftest)


# ── 操作 helper ───────────────────────────────────────────────────
def open_doc(page, static_url, path):
    page.goto(f"{static_url}#doc/{urllib.parse.quote(path, safe='/')}")
    page.wait_for_selector(".editor-shell .ProseMirror", timeout=15000)
    page.wait_for_timeout(600)


def enter_edit(page, entry):
    """进入编辑：body（点正文）/ title（点标题）/ summary（点摘要）"""
    if entry == "title":
        page.locator(".viewer__title").click()
    elif entry == "summary":
        page.locator(".viewer__summary").click()
    else:
        page.locator(".editor-shell .ProseMirror").click(position={"x": 150, "y": 80})
    page.wait_for_selector(".viewer__title-input", timeout=5000)
    page.wait_for_timeout(250)


def apply_mod(page, mod, marker="AUTO-MARKER-2026"):
    """应用修改：none / body / title / summary / body_title"""
    if mod in ("body", "body_title"):
        page.locator(".editor-shell .ProseMirror").click(position={"x": 300, "y": 300})
        page.keyboard.press("Control+End")
        page.keyboard.type(f"\n\n{marker}", delay=15)
    if mod in ("title", "body_title"):
        page.fill(".viewer__title-input", NEW_TITLE)
    if mod == "summary":
        page.fill(".viewer__summary-input", "AUTO-新摘要")
    page.wait_for_timeout(200)


def exit_inplace(page):
    """原地保存：点侧栏 footer（非编辑区）→ onDocClick → exitEdit（不切走）"""
    page.locator(".sidebar-footer").click(position={"x": 40, "y": 10}, force=True)
    page.wait_for_timeout(1200)


def navigate(page, target):
    """切换目标：doc_same / doc_cross / project / dashboard / trash / back / url / ref"""
    if target == "doc_same":
        page.locator(f'.sidebar-tree__item[data-doc-path="{DOC_SAME}"]').click()
    elif target == "doc_cross":
        row = page.locator(f'.sidebar-tree__item[data-doc-path="{DOC_TARGET}"]')
        if row.count() == 0:
            # Training 树未展开（当前在 MyKnowledge，自动展开只覆盖当前路径链）→ 先展开
            training = page.locator(".sidebar-project").filter(
                has=page.locator(".sidebar-item__name", has_text="Training 人员培训"))
            training.locator(".sidebar-project__chevron").first.click()
            page.wait_for_selector(f'.sidebar-tree__item[data-doc-path="{DOC_TARGET}"]', timeout=8000)
            row = page.locator(f'.sidebar-tree__item[data-doc-path="{DOC_TARGET}"]')
        row.click()
    elif target == "project":
        page.locator(".sidebar-item__name", has_text="MyKnowledge 项目知识管理平台").first.click()
    elif target == "dashboard":
        page.evaluate("window.location.hash = 'dashboard'")
    elif target == "trash":
        page.evaluate("window.location.hash = 'trash'")
    elif target == "back":
        page.go_back()
    elif target == "url":
        page.evaluate(f"window.location.hash = 'doc/{urllib.parse.quote(DOC_SAME, safe='')}'")
    elif target == "ref":
        page.locator(".editor-shell .ProseMirror a[href*='test-edit-auto-target']").first.click()
    page.wait_for_timeout(1500)


# ── 断言 helper ───────────────────────────────────────────────────
def shown_title(page):
    el = page.locator(".viewer__title > span")
    return el.inner_text().strip() if el.count() else ""


def shown_summary(page):
    el = page.locator(".viewer__summary").locator("span").nth(1)
    return el.inner_text().strip() if el.count() else ""


def shown_body(page):
    return page.locator(".editor-shell").inner_text()


def toasts(page):
    return page.evaluate("window.__toasts")


def active_tree_doc(page):
    """当前高亮的侧栏文档行路径"""
    el = page.locator(".sidebar-tree__item--active[data-doc-path]").first
    return el.get_attribute("data-doc-path") if el.count() else ""


def assert_backend_content(path, contains):
    st, d = backend_doc(path)
    assert st == 200, f"后端 GET {path} -> {st}"
    assert contains in (d or {}).get("content", ""), f"后端 content 缺 {contains!r}"


def assert_backend_summary(path, expect):
    st, d = backend_doc(path)
    assert st == 200, f"后端 GET {path} -> {st}"
    assert (d or {}).get("summary") == expect, f"后端 summary={ (d or {}).get('summary')!r} != {expect!r}"


def attach_tracker(page):
    """绑定 ApiTracker（重复加载检测）"""
    sys.path.insert(0, str(ROOT / "tests" / "frontend"))
    from api_tracker import ApiTracker
    return ApiTracker(page)


def delay_route(page, method, url_contains, seconds):
    """竞态注入：延迟匹配请求的响应，制造乱序（保存 PUT 晚于加载 GET 返回）"""
    def handler(route):
        req = route.request
        if req.method.upper() == method.upper() and url_contains in req.url:
            time.sleep(seconds)
        route.continue_()
    page.route("**/api/**", handler)
