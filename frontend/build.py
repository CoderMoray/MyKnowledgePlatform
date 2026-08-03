#!/usr/bin/env python3
"""MyKnowledge 前端构建脚本

将 CSS 和 JS 源文件内联到 index.html 中，生成独立可运行的 standalone HTML。
仅内联本地文件（css/*.css, js/*.js），保留 CDN 引用。
"""

import re
import subprocess
import sys
import tempfile
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


# ── 资源版本化（cache busting）─────────────────────────────────────────────
# 后端静态服务只返回 ETag（无 Cache-Control），浏览器启发式缓存会导致
# 普通刷新拿到旧资源。这里给所有本地资源引用加 ?v=<build 时间戳>，
# 每次 build 版本变化 → 资源 URL 变化 → 浏览器强制重新下载。
# 配合后端 HTML no-cache，普通刷新即拿到最新版本，无需手动强刷。
def _strip_versions(html: str) -> str:
    """去掉已有 ?v= 参数，避免重复 build 累积"""
    return re.sub(r"(\?v=)\d+", "", html)


def _versionize(html: str, version: str) -> str:
    def addv(url: str) -> str:
        return url + ("&" if "?" in url else "?") + "v=" + version

    # 本地 JS（js/、vendor/）
    html = re.sub(
        r'(<script[^>]*\ssrc=["\'])((?:js/|vendor/)[^"\']+)(["\'])',
        lambda m: m.group(1) + addv(m.group(2)) + m.group(3),
        html,
    )
    # 本地 CSS（css/、vendor/ 的 .css）
    html = re.sub(
        r'(<link[^>]*\shref=["\'])((?:css/|vendor/)[^"\']+\.css)(["\'])',
        lambda m: m.group(1) + addv(m.group(2)) + m.group(3),
        html,
    )
    # importmap 里的 tiptap bundle
    html = re.sub(
        r'("myk-tiptap":\s*")(\./tiptap-bundle\.mjs)(")',
        lambda m: m.group(1) + addv(m.group(2)) + m.group(3),
        html,
    )
    return html


def build() -> None:
    import time

    version = str(int(time.time()))
    # 读取原始 index.html，去除旧版本参数，再打上新版本号
    original = _strip_versions(read_file(INDEX))
    html = _versionize(original, version)

    # 写回 index.html（开发版资源带版本号 → 普通刷新即最新）
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  OK    index.html versioned (?v={version})")

    # ── 内联 CSS ──
    for css_file in CSS_ORDER:
        css_path = CSS_DIR / css_file
        if not css_path.exists():
            print(f"  WARN  CSS not found: {css_path}")
            continue
        content = read_file(css_path)
        pattern = re.compile(
            rf'<link\s+[^>]*href=["\']css/{re.escape(css_file)}(?:\?v=\d+)?["\'][^>]*/?>',
            re.IGNORECASE,
        )
        if pattern.search(html):
            # Use lambda to avoid regex interpreting \s etc. in CSS content
            html = pattern.sub(lambda m, f=css_file, c=content: f"<style>\n/* {f} */\n{c}\n</style>", html, count=1)
            print(f"  OK    css/{css_file}")
        else:
            print(f"  SKIP  css/{css_file} (not referenced in index.html)")

    # ── 内联 JS ──
    js_files = sorted(JS_DIR.glob("*.js")) + sorted((JS_DIR / "components").glob("*.js"))
    for js_path in js_files:
        content = read_file(js_path)
        rel_path = str(js_path.relative_to(FRONTEND))
        pattern = re.compile(
            rf'<script\s+[^>]*src=["\']{re.escape(rel_path)}(?:\?v=\d+)?["\'][^>]*>\s*</script>',
            re.IGNORECASE,
        )
        if pattern.search(html):
            html = pattern.sub(lambda m: f"<script>\n/* {rel_path} */\n{content}\n</script>", html, count=1)
            print(f"  OK    {rel_path}")
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

    # ── JS 语法检查 ──
    import tempfile

    with open(OUTPUT, "r", encoding="utf-8") as f:
        html = f.read()
    codes = []
    for m in re.finditer(r"<script>([\s\S]*?)</script>", html):
        code = m.group(1).strip()
        if len(code) > 100:
            codes.append(code)
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
        f.write("\n".join(codes))
        tmp = f.name
    ret = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    Path(tmp).unlink()
    if ret.returncode != 0:
        print(f"\n  ✗  JS 语法错误:\n{ret.stderr}")
        sys.exit(1)
    else:
        print(f"\n  ✓  JS 语法正确 ({len(codes)} 个脚本块)")

    # ── CDN 可达性检查 ──
    print("\n── CDN 检查 ──")
    cdn_urls = set()
    for m in re.finditer(r'"(https?://(?:cdn\.jsdelivr\.net|esm\.sh)/[^"]+)"', html):
        cdn_urls.add(m.group(1))
    checked = 0
    failed = 0
    for url in sorted(cdn_urls):
        if "alpinejs" in url:
            continue
        try:
            r = subprocess.run(
                ["curl", "-sI", "--connect-timeout", "3", url],
                capture_output=True, text=True, timeout=5
            )
            status = r.stdout.split()[1] if r.stdout else "000"
            if status in ("200", "301", "302", "304"):
                checked += 1
            else:
                print(f"  ✗  {url} → {status}")
                failed += 1
        except Exception as e:
            print(f"  ?  {url} → {e}")
            failed += 1
    if failed:
        print(f"  ⚠  {failed}/{checked + failed} 个 CDN 不可达")
    else:
        print(f"  ✓  {checked} 个 CDN 全部可达")
