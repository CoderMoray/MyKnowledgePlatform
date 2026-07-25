#!/usr/bin/env python3
"""MyKnowledge 前端构建脚本

将 CSS 和 JS 源文件内联到 index.html 中，生成独立可运行的 standalone HTML。
仅内联本地文件（css/*.css, js/*.js），保留 CDN 引用。
"""

import re
from pathlib import Path

FRONTEND = Path(__file__).parent
INDEX = FRONTEND / "index.html"
OUTPUT = FRONTEND / "index.standalone.html"

CSS_DIR = FRONTEND / "css"
JS_DIR = FRONTEND / "js"

# CSS 文件加载顺序（design-tokens 必须最先）
CSS_ORDER = [
    "design-tokens.css",
    "reset.css",
    "layout.css",
    "sidebar.css",
    "viewer.css",
    "editor.css",
    "components.css",
    "markdown-content.css",
]


def read_file(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build() -> None:
    html = read_file(INDEX)

    # ── 内联 CSS ──
    for css_file in CSS_ORDER:
        css_path = CSS_DIR / css_file
        if not css_path.exists():
            print(f"  WARN  CSS not found: {css_path}")
            continue
        content = read_file(css_path)
        pattern = re.compile(
            rf'<link\s+[^>]*href=["\']css/{re.escape(css_file)}["\'][^>]*/?>',
            re.IGNORECASE,
        )
        if pattern.search(html):
            # Use lambda to avoid regex interpreting \s etc. in CSS content
            html = pattern.sub(lambda m, f=css_file, c=content: f"<style>\n/* {f} */\n{c}\n</style>", html, count=1)
            print(f"  OK    css/{css_file}")
        else:
            print(f"  SKIP  css/{css_file} (not referenced in index.html)")

    # ── 内联 JS ──
    js_files = sorted(JS_DIR.glob("*.js"))
    for js_path in js_files:
        content = read_file(js_path)
        pattern = re.compile(
            rf'<script\s+[^>]*src=["\']js/{re.escape(js_path.name)}["\'][^>]*>\s*</script>',
            re.IGNORECASE,
        )
        if pattern.search(html):
            # Use lambda to avoid regex interpreting \s etc. in replacement
            html = pattern.sub(lambda m: f"<script>\n/* {js_path.name} */\n{content}\n</script>", html, count=1)
            print(f"  OK    js/{js_path.name}")
        else:
            print(f"  SKIP  js/{js_path.name} (not referenced in index.html)")

    # ── 写入 ──
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = OUTPUT.stat().st_size / 1024
    print(f"\n  Done  → {OUTPUT.name} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    print("MyKnowledge frontend build\n")
    build()
