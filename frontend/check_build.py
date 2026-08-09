#!/usr/bin/env python3
"""MyKnowledge 前端构建忠实性检查（2026-08-09 重构）

验证 index.standalone.html 是 index.html + js/ + css/ 的忠实内联：
  ① HTML 结构完整性：index.html 的 id / x-data 标记在 standalone 全含
     （build 只内联 script/style，不允许改动 HTML 结构）
  ② JS 内联完整性：js/ 里的 Alpine.data / router.on / window.* / Alpine.store
     注册符号在 standalone 全含（防 JS 漏内联）
  ③ CSS 内联完整性：CSS_ORDER 各文件的类/id 选择器在 standalone 全含（防 CSS 漏内联）
  ④ ?v= 版本化一致性：index.html 每个 ?v= 与对应文件内容 md5 前 10 位一致
  ⑤ 编辑保存往返测试（turndown 转换正确性，node + jsdom/turndown）

核心设计：期望全部从当前源码推导——前端演进（改 class/路由/依赖/写法）不会让检查变红；
只有当 build 真的破坏产物（漏内联 / 改结构 / 版本化错）才失败。
在 build.py 之后运行；与 build.py 一起作为 hook / CI 硬门禁。
"""

import hashlib
import re
import subprocess
import shutil
import sys
from pathlib import Path

FRONTEND = Path(__file__).parent
INDEX = FRONTEND / "index.html"
HTML = FRONTEND / "index.standalone.html"
CSS_DIR = FRONTEND / "css"
JS_DIR = FRONTEND / "js"

# 与 build.py 的 CSS_ORDER 保持一致
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


def _file_hash(rel_path: str) -> str:
    """与 build.py 相同的 md5 前 10 位；文件缺失返回 0"""
    try:
        return hashlib.md5((FRONTEND / rel_path.lstrip("./")).read_bytes()).hexdigest()[:10]
    except Exception:
        return "0"


def main():
    global PASS, FAIL
    if not HTML.exists():
        print(f"\u2717 未找到构建产物: {HTML}")
        sys.exit(1)

    index = INDEX.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    print(f"\n{HTML.name}  ({len(html) / 1024:.0f} KB)\n")

    # ── ① HTML 结构完整性 ──
    print("── \u2460 HTML 结构完整性（index.html 标记必须都在 standalone）──")
    ids = set(re.findall(r'id="([^"]+)"', index))
    xdatas = set(re.findall(r'x-data="([^"]+)"', index))
    check(f"提取 id 标记 {len(ids)} 个 / x-data {len(xdatas)} 个", len(ids) > 0 or len(xdatas) > 0)
    for i in sorted(ids):
        check(f"id=\"{i}\"", f'id="{i}"' in html, "build 改动 HTML 结构")
    for x in sorted(xdatas):
        check(f"x-data=\"{x}\"", f'x-data="{x}"' in html, "组件挂载点丢失")

    # ── ② JS 内联完整性 ──
    print("\n── \u2461 JS 内联完整性（js/ 注册符号必须都在 standalone）──")
    # 只检查 index.html 实际引用的 js（build.py 只内联被引用的；editor.js/viewer.js 等遗留文件不内联）
    ref_js = set(re.findall(r'src=["\'](js/[^"\']+?\.js)', index))
    check(f"index.html 引用 js 文件 {len(ref_js)} 个", len(ref_js) > 0)
    syms = set()
    for rel in sorted(ref_js):
        f = FRONTEND / rel
        if not f.exists():
            check(f"js 文件 {rel}", False, "引用但文件缺失")
            continue
        src = f.read_text(encoding="utf-8")
        syms.update(re.findall(r'Alpine\.data\("([^"]+)"\)', src))
        syms.update(re.findall(r'router\.on\("([^"]+)"', src))
        syms.update(re.findall(r'window\.(\w+)\s*=', src))
        syms.update(re.findall(r'Alpine\.store\("([^"]+)"', src))
    check(f"提取注册符号 {len(syms)} 个", len(syms) > 0)
    missing = [s for s in sorted(syms) if s not in html]
    if missing:
        for s in missing:
            check(f"符号 {s}", False, "JS 未内联进 standalone")
    else:
        check(f"全部 {len(syms)} 个注册符号内联", True)

    # ── ③ CSS 内联完整性 ──
    print("\n── \u2462 CSS 内联完整性（CSS_ORDER 选择器必须都在 standalone）──")
    selectors = set()
    for css_name in CSS_ORDER:
        p = CSS_DIR / css_name
        if not p.exists():
            check(f"css/{css_name}", False, "CSS 文件缺失")
            continue
        src = p.read_text(encoding="utf-8")
        for m in re.finditer(r"([^{}@/\n]+)\{[^}]*\}", src):
            sel = m.group(1)
            selectors.update(re.findall(r"\.[a-zA-Z_][\w-]*", sel))
            selectors.update(re.findall(r"#[a-zA-Z_][\w-]*", sel))
    check(f"提取选择器 {len(selectors)} 个", len(selectors) > 0)
    missing = [s for s in sorted(selectors) if s not in html]
    if missing:
        for s in missing[:10]:
            check(f"选择器 {s}", False, "CSS 未内联进 standalone")
        if len(missing) > 10:
            print(f"      … 共 {len(missing)} 个缺失")
    else:
        check(f"全部 {len(selectors)} 个选择器内联", True)

    # ── ④ ?v= 版本化一致性 ──
    print("\n── \u2463 ?v= 版本化一致性（hash 与文件内容匹配）──")
    vrefs = re.findall(r"((?:js/|css/|vendor/)[^\"']+?)\?v=([0-9a-f]{10})", index)
    check(f"提取版本化引用 {len(vrefs)} 个", len(vrefs) > 0)
    bad = 0
    for path, v in vrefs:
        want = _file_hash(path)
        if want == "0":
            check(f"{path} ?v={v}", False, "资源文件缺失")
            bad += 1
        elif v != want:
            check(f"{path} ?v={v}", False, f"内容哈希应为 {want}（改源码后未重新 build）")
            bad += 1
    if not bad:
        check(f"全部 {len(vrefs)} 个 ?v= 与内容一致", True)
    m = re.search(r'"myk-tiptap":\s*"\./tiptap-bundle\.mjs\?v=([0-9a-f]{10})"', index)
    if m:
        want = _file_hash("tiptap-bundle.mjs")
        check("tiptap-bundle.mjs ?v=", m.group(1) == want, f"内容哈希应为 {want}")

    # ── ⑤ 编辑保存往返测试（node + jsdom/turndown）──
    print("\n── \u2464 编辑保存往返测试（turndown 转换）──")
    node = shutil.which("node") or "node"
    test_js = str(FRONTEND / "test-save-roundtrip.js")
    if Path(test_js).exists():
        node_path = str(FRONTEND / "node_modules") if (FRONTEND / "node_modules").exists() \
            else str(Path.home() / ".workbuddy/binaries/node/workspace/node_modules")
        try:
            r = subprocess.run([node, test_js], capture_output=True, text=True, timeout=30,
                               env={"NODE_PATH": node_path})
            out = r.stdout.strip()
            m = re.search(r"(\d+)/(\d+) 通过", out)
            if m:
                got, want = int(m.group(1)), int(m.group(2))
                PASS += got
                FAIL += (want - got)
                print(out)
            else:
                FAIL += 1
                print("  ❌ 往返测试解析失败\n" + out[:500])
        except Exception as e:
            FAIL += 1
            print(f"  ❌ 往返测试执行异常: {e}")

    total = PASS + FAIL
    print(f"\n{'=' * 40}")
    print(f"  通过 {PASS}/{total}  |  失败 {FAIL}")
    print(f"{'=' * 40}\n")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
