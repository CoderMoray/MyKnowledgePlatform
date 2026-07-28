#!/usr/bin/env python3
"""MyKnowledge 前端构建检查

验证 index.standalone.html 是否包含所有必需的元素、函数和配置。
在 build.py 之后运行。
"""

import re
import sys
from pathlib import Path

FRONTEND = Path(__file__).parent
HTML = FRONTEND / "index.standalone.html"

PASS = 0
FAIL = 0


def check(label, condition, hint=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \u2713  {label}")
    else:
        FAIL += 1
        msg = f"  \u2717  {label}"
        if hint:
            msg += f"  ({hint})"
        print(msg)


def has(html, pattern):
    return bool(re.search(pattern, html))


def count(html, pattern):
    return len(re.findall(pattern, html))


def main():
    global PASS, FAIL
    if not HTML.exists():
        print(f"\u2717 未找到构建产物: {HTML}")
        sys.exit(1)

    html = HTML.read_text(encoding="utf-8")
    size_kb = len(html) / 1024
    print(f"\n{HTML.name}  ({size_kb:.0f} KB)\n")

    # CDN
    print("── CDN 依赖 ──")
    check("Alpine.js CDN", has(html, r"alpinejs@3"), "缺少 Alpine.js")
    check("marked CDN", has(html, r"marked@11"), "缺少 marked")
    check("highlight.js CDN", has(html, r"highlight\.js@11"), "缺少 highlight.js")
    check("Turndown CDN", has(html, r"turndown@7"), "缺少 turndown")
    check("TipTap Core", has(html, r"@tiptap/core"), "缺少 @tiptap/core")
    check("TipTap StarterKit", has(html, r"@tiptap/starter-kit"), "缺少 @tiptap/starter-kit")
    check("CDN 路径无 /lib/", not has(html, r"/lib/highlight\.min\.js"),
          "highlight.js 路径含 /lib/")

    # 全局函数
    print("\n── 全局函数 ──")
    funcs = [
        "marked.parse", "class Router", "Alpine.store",
        "loadDocument", "formatDate", "extractDisplayName",
        "statusLabel", "fileName", "escapeHtml",
        "_mykRefClick", "_mykSplash",
    ]
    for fn in funcs:
        check(fn, has(html, fn), f"{fn} 未定义")

    # 路由
    print("\n── 路由 ──")
    check('路由 #dashboard', has(html, r'router\.on\("dashboard"'), "缺少 dashboard 路由")
    check('路由 #project/:name', has(html, r'router\.on\("project'), "缺少 project 路由")
    check('路由 #doc/:path', has(html, r'router\.on\("doc'), "缺少 doc 路由")
    check('已删除 #view 路由', not has(html, r'router\.on\("view'), "view 路由应已删除")
    check('已删除 #edit 路由', not has(html, r'router\.on\("edit'), "edit 路由应已删除")
    check('路由 #status', has(html, r'router\.on\("status'), "缺少 status 路由")
    check("所有跳转指向 #doc/", count(html, r'doc/') >= 2,
          "doc 跳转不足（至少 2 处）")

    # 页面元素
    print("\n── 页面元素 ──")
    check("full-screen splash", has(html, r'class="splash"'), "全屏 splash 未定义")
    check("page-splash（内容区加载动画）", has(html, r'class="page-splash'), "页面切换加载动画未定义")
    check("splashBar", has(html, r'id="splashBar"'), "splashBar 元素缺失")
    check("pageSplashBar", has(html, r'id="pageSplashBar"'), "pageSplashBar 元素缺失")
    check("sidebar", has(html, r'class="sidebar"'), "sidebar 未定义")
    check("content-panel", has(html, r'class="content-panel"'), "content-panel 未定义")
    check("sidebar-footer", has(html, r'class="sidebar-footer"'), "sidebar-footer 未定义")
    check("docComponent", has(html, r'docComponent'), "docComponent 未定义")
    check("组件文件 (doc.js)", has(html, r"js/components/doc.js"), "缺少 doc.js")
    check("组件文件 (sidebar.js)", has(html, r"js/components/sidebar.js"), "缺少 sidebar.js")
    check("组件文件 (modal.js)", has(html, r"js/components/modal.js"), "缺少 modal.js")
    check("theme-switcher", has(html, r'class="theme-switcher"'), "主题切换器未定义")
    check("page-label", has(html, r'class="page-label"'), "page-label 未定义")
    check("tiptap-editor 挂载点", has(html, r'id="tiptap-editor"'), "tiptap-editor 挂载点缺失")
    check("ProseMirror 类", has(html, r'ProseMirror'), "ProseMirror 类缺失")
    check("ProseMirror--readonly", has(html, r'ProseMirror--readonly'), "只读态 ProseMirror 样式缺失")

    # 模板 x-data 与 Alpine.data 注册一致性
    xdata_refs = set(re.findall(r'x-data="(\w+Component)"', html))
    alpine_regs = set(re.findall(r'Alpine\.data\("(\w+Component)"', html))
    unregistered = xdata_refs - alpine_regs
    orphaned = alpine_regs - xdata_refs
    if unregistered:
        for name in sorted(unregistered):
            check(f"模板引用 {name}", False, f"模板 x-data=\"{name}\" 无对应 Alpine.data() 注册")
    if orphaned:
        for name in sorted(orphaned):
            check(f"未使用的组件 {name}", False, f"Alpine.data(\"{name}\") 注册了但模板未引用")

    # Ref 链接渲染检查（marked renderer 必须正确处理 ref: 协议）
    ref_links = re.findall(r'data-ref-path="([^"]+)"', html)
    if len(ref_links) >= 2:
        check(f"ref 链接渲染 ({len(ref_links)} 处)", True, "")
    else:
        check("ref 链接渲染", len(ref_links) >= 2,
              f"ref 链接不足 2 处（当前 {len(ref_links)}），marked renderer 可能未生效")
    # 确保 ref 链接路径不含 :: 后缀（已 stripped）
    bad_refs = [p for p in ref_links if "::" in p]
    check("ref 路径无 :: 后缀", len(bad_refs) == 0,
          f"存在 {len(bad_refs)} 处含 :: 的 ref 路径")

    # 渲染一致性检查
    print("\n── 渲染一致性 ──")
    selectors = [
        ("h1", r"h1\b"),
        ("h2", r"h2\b"),
        ("h3", r"h3\b"),
        ("p", r"\bp\b"),
        ("ul", r"\bul\b"),
        ("ol", r"\bol\b"),
        ("blockquote", r"blockquote\b"),
        ("pre/code", r"\bpre\b"),
        ("table", r"\btable\b"),
        ("a 链接", r"\ba\b"),
        ("hr 水平线", r"\bhr\b"),
    ]
    for label, sel in selectors:
        # 检查 markdown-body 和 ProseMirror 都有对应的样式
        md_ok = has(html, rf"\.markdown-body\s+{sel}")
        pm_ok = has(html, rf"\.ProseMirror\s+{sel}") or has(html, rf"\.ProseMirror-{sel}")
        check(f"样式 \"{label}\" 双引擎对齐",
              md_ok and pm_ok,
              f"markdown-body({md_ok}) vs ProseMirror({pm_ok})")

    # Store 状态
    print("\n── Store 状态 ──")
    check("editingMode 状态", has(html, r"editingMode"), "editingMode 状态未定义")
    check("systemStatus 计算属性", has(html, r"systemStatus"), "systemStatus 未定义")
    check("meta 拍平 (Object.assign)", has(html, r"Object\.assign\(data,\s*data\.meta\)"),
          "meta 拍平逻辑不存在")

    # 样式
    print("\n── 样式 ──")
    check("status-dot--danger（红点）", has(html, r"status-dot--danger"), "红点样式未定义")
    check("page-label__back（返回箭头）", has(html, r"page-label__back"), "返回箭头样式未定义")
    check("sidebar-footer 同行布局",
          has(html, r"flex-direction:\s*row") and has(html, r"justify-content:\s*space-between"),
          "sidebar-footer 未同行布局")
    check("btn-delete-top（淡红删除）", has(html, r"btn-delete-top"), "删除按钮样式未定义")

    # 关键文本
    print("\n── 关键文本 ──")
    for text in ["知识库版本", "知识", "子项目", "归档",
                 "用户使用中", "用户编辑中", "AI 编辑中",
                 "已完成", "已取消", "已废弃"]:
        c = html.count(text)
        check(f"文本「{text}」", c > 0, f"出现 {c} 次")

    total = PASS + FAIL
    print(f"\n{'='*40}")
    print(f"  通过 {PASS}/{total}  |  失败 {FAIL}")
    print(f"{'='*40}\n")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
