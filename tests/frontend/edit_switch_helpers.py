"""编辑切换测试 公共操作/断言 helper（纯函数，fixtures 见 conftest.py）

把"手测常规方法"沉淀为可复用操作：
    open_doc → enter_edit(入口) → apply_mod(修改) → navigate(切走)/exit_inplace(原地保存)
    → assert_*(保存/残留/高亮/toast/加载次数)
"""
import json
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROJ = "projects/MyKnowledge 项目知识管理平台"
TRAIN = "projects/Training 人员培训"
SUB_PROJ = f"{TRAIN}/projects/测试子项目"
DOC_MAIN = f"{PROJ}/common-knowledge/test-edit-auto-main.md"
DOC_SAME = f"{PROJ}/common-knowledge/test-edit-auto-same.md"
DOC_TARGET = f"{TRAIN}/common-knowledge/test-edit-auto-target.md"
DOC_SUB = f"{SUB_PROJ}/common-knowledge/test-edit-auto-sub.md"
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
    elif target == "subproject":
        # 子项目页：Training 树未展开 → 先展开顶层，再点树内子项目行（data-project-path）
        sub_row = page.locator(f'[data-sub-path="{SUB_PROJ}"]')
        if sub_row.count() == 0:
            training = page.locator(".sidebar-project").filter(
                has=page.locator(".sidebar-item__name", has_text="Training 人员培训"))
            training.locator(".sidebar-project__chevron").first.click()
            page.wait_for_selector(f'[data-sub-path="{SUB_PROJ}"]', timeout=8000)
            sub_row = page.locator(f'[data-sub-path="{SUB_PROJ}"]')
        sub_row.locator('.sidebar-tree__name[data-project-path]').first.click()
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


def wait_for_backend(path, status, timeout=8.0, interval=0.2):
    """轮询后端直到 GET 状态符合预期（rename 等异步操作需显式等待，防批量跑偶发时序）"""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, _ = backend_doc(path)
        if st == status:
            return
        time.sleep(interval)
    st, _ = backend_doc(path)
    assert st == status, f"等待超时: {path} GET 期望 {status}，实际 {st}"


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


# ── 批 2/批 3 基建 helper（S13/S19/S20/S21/S23/S25 用）──────────────────

def click_toc(page, idx):
    """点侧栏目录第 idx 项（tocJump → scrollIntoView，不退出编辑态）"""
    el = page.locator(f"[data-toc-jump='{idx}']").first
    assert el.count(), f"TOC 第 {idx} 项不存在"
    el.click()
    page.wait_for_timeout(600)


def toggle_project_chevron(page, proj_name):
    """点项目行 chevron 展开/收起，返回 (操作前展开?, 操作后展开?)"""
    proj = page.locator(".sidebar-project").filter(
        has=page.locator(".sidebar-item__name", has_text=proj_name)).first
    chevron = proj.locator(".sidebar-project__chevron").first
    def _open():
        cls = chevron.locator("svg").get_attribute("class") or ""
        return "is-open" in cls
    was = _open()
    chevron.click()
    page.wait_for_timeout(600)
    return was, _open()


def inject_lock(page, locked=True):
    """S21：route mock /api/lock → 前端 checkLock 进入锁定态（不改真实锁文件）"""
    body = {
        "locked": locked,
        "pid": 99999,
        "agent": "test-agent",
        "since_ts": 0, "expires_ts": 0,
        "since": "2026-01-01T00:00:00+08:00",
        "expires_at": "2026-01-01T00:00:00+08:00",
        "expired": False,
    }
    page.route("**/api/lock", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(body)))
    page.evaluate("Alpine.store('app').checkLock()")
    page.wait_for_timeout(500)


def release_lock(page):
    """解除锁 mock，恢复真实 /api/lock 轮询结果"""
    page.unroute("**/api/lock")
    page.evaluate("Alpine.store('app').checkLock()")
    page.wait_for_timeout(500)


def mock_409(page, url_contains="document"):
    """S25：拦截 PUT 保存返回 409（version 冲突）；其余请求放行"""
    def handler(route):
        req = route.request
        if req.method.upper() == "PUT" and url_contains in req.url:
            route.fulfill(status=409, content_type="application/json",
                          body=json.dumps({"detail": "version conflict (test mock 409)"}))
        else:
            route.continue_()
    page.route("**/api/**", handler)


def delete_doc_from_edit(page, confirm=True):
    """S23：编辑态点删除按钮 → 自动退出编辑保存 → 删除确认模态 → 确认/取消"""
    btn = page.locator(".btn-delete", has_text="删除").first
    assert btn.count(), "编辑态删除按钮不可见（应保留可见）"
    btn.click()
    page.wait_for_timeout(1000)          # 自动退出编辑（保存）
    if confirm:
        page.get_by_role("button", name="确认删除").click()
        page.wait_for_timeout(2500)      # DELETE + toast + 倒计时跳转
