"""编辑切换测试 fixtures（pytest 自动加载）

复用现有 8080 后端（不新起进程）；测试文档隔离创建/清理。
"""
import http.server
import json
import socketserver
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
API_BASE = "http://127.0.0.1:8080"

PROJ = "projects/MyKnowledge 项目知识管理平台"
TRAIN = "projects/Training 人员培训"
SUB_PROJ = f"{TRAIN}/projects/测试子项目"
DOC_MAIN = f"{PROJ}/common-knowledge/test-edit-auto-main.md"
DOC_SAME = f"{PROJ}/common-knowledge/test-edit-auto-same.md"
DOC_TARGET = f"{TRAIN}/common-knowledge/test-edit-auto-target.md"
DOC_SUB = f"{SUB_PROJ}/common-knowledge/test-edit-auto-sub.md"
SUB_README = f"{SUB_PROJ}/readme.md"
NEW_TITLE = "test-edit-auto-renamed"


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}", method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def backend_doc(path):
    st, d = api("GET", f"/api/document/{urllib.parse.quote(path, safe='/')}")
    return (st, d) if st == 200 else (st, None)


KB_ROOT = ROOT / ".myknowledge_test"


def _parent_rel(rel_path: str) -> str:
    """文档归属的项目层（根层返回 ''）——与 backend.mcp_server._parent_rel 同语义。

    - "common-knowledge/a.md" → ""
    - "projects/P/common-knowledge/a.md" → "projects/P"
    - "projects/P/projects/子/common-knowledge/a.md" → "projects/P/projects/子"
    """
    idx = rel_path.find("/common-knowledge/")
    if idx == -1 and rel_path.startswith("common-knowledge/"):
        return ""
    if idx >= 0:
        return rel_path[:idx]
    return "/".join(rel_path.split("/")[:-1])


def _git_commit_if_changed(paths, message: str) -> None:
    """仅当 paths 确有 staged 变更时 git commit；无变更则跳过（幂等）。

    不用 GitManager.commit：其 status --porcelain 会把垃圾箱未跟踪残留（trash/
    历史测试残留数百上千个）当 dirty，add 后无 staged 变更时 git commit 会报
    "no changes added to commit" 抛 GitError。这里先 stage 再查 diff --cached。
    git 失败显式抛出（不静默吞掉）。
    """
    import subprocess

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=str(KB_ROOT), capture_output=True, text=True
        )

    add_paths = []
    for p in paths:
        ap = str(Path(p).resolve())
        if Path(ap).exists():
            add_paths.append(ap)
        elif git("ls-files", "--", ap).stdout.strip():
            add_paths.append(ap)  # 已删但 tracked → stage 删除
    if not add_paths:
        return
    git("add", "-A", "--", *add_paths)
    staged = git("diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        return  # 无实际变更，跳过（不产生空提交报错）
    r = git("commit", "-m", message)
    if r.returncode != 0:
        raise RuntimeError(f"git commit failed: {r.stderr.strip()}")


def hard_delete_doc(rel_path: str) -> None:
    """物理删除测试文档（不进垃圾箱）+ git 提交删除 + 重建父 readme。

    与后端写操作范式一致（见 backend/mcp_server.py move_document）：
    精准 git 提交（paths 含已删文件 + 变更 readme）+ 父层 readme 重建。
    文件不存在时静默跳过（unlink 幂等）；git 失败显式抛出（不静默吞掉）。
    """
    from backend.readme_generator import ReadmeGenerator
    from backend.storage import Storage

    target = KB_ROOT / rel_path
    if target.exists():
        target.unlink()

    storage = Storage(kb_root=KB_ROOT)
    template = KB_ROOT / "_templates" / "readme.md"
    parent = _parent_rel(rel_path)
    readme_rel = f"{parent}/readme.md" if parent else "readme.md"
    if template.exists():
        gen = ReadmeGenerator(storage=storage, template_path=template)
        gen.rebuild(parent)

    # git paths 用绝对路径：相对路径会被 Python 进程 cwd（如项目根存在 readme.md）误解析
    _git_commit_if_changed(
        [str(KB_ROOT / rel_path), str(KB_ROOT / readme_rel)],
        f"test-cleanup: remove {rel_path}",
    )


@pytest.fixture(scope="module")
def backend_running():
    """复用现有 8080 后端；无后端则跳过"""
    try:
        urllib.request.urlopen(f"{API_BASE}/api/lock", timeout=3)
    except Exception:
        pytest.skip("需要后端在 8080 运行（myknowledge serve --root .myknowledge_test）")


@pytest.fixture(scope="module")
def static_server():
    # 用 index.html（开发版，外部 js/css 实时加载）——index.standalone.html 是
    # 被 .gitignore 忽略的本地手工内联版，无构建脚本，改前端源码不会同步进去，
    # 测试加载它会拿到旧版 JS（S19/S20 曾因此误判修复无效）
    with socketserver.TCPServer(("127.0.0.1", 0),
                                lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(FRONTEND), **kw)) as httpd:
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{port}/index.html"
        httpd.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            try:
                b = p.chromium.launch(headless=True)
            except Exception as e:
                pytest.skip(f"Browser unavailable: {e}")
        yield b
        b.close()


@pytest.fixture
def test_docs(backend_running):
    """每个测试独立创建/清理测试文档（隔离：S3/S4e rename 会改路径，不能跨测试复用）。

    注意：不建子项目/额外项目目录——归属候选断言（CORE_CANDIDATES ⊆ 实际候选）依赖
    "库内真实项目覆盖核心集合"；子项目 fixture 见 subproject_docs（独立，仅批 2 子项目场景用）。
    """
    docs = {
        DOC_MAIN: ("# Auto Main 文档\n\n主文档正文段落。\n\n## 二级标题甲\n\n二级段落。\n\n### 三级标题乙\n\n三级段落。\n\n引用 [Target](ref:" + DOC_TARGET + ")", "主文档摘要"),
        DOC_SAME: ("# Auto Same 文档\n\n同项目目标文档正文。", "同项目摘要"),
        DOC_TARGET: ("# Auto Target 文档\n\n跨项目目标文档正文。\n\n引用 [Main](ref:" + DOC_MAIN + ")", "跨项目摘要"),
    }
    for path, (content, summary) in docs.items():
        # 无论是否存在都 POST 覆盖，保证每次测试是干净起点（防残留污染复用）
        api("POST", f"/api/document/{urllib.parse.quote(path, safe='/')}",
            {"content": content, "summary": summary})
    yield docs
    # 清理：真删除（不进垃圾箱）+ git 提交删除 + 重建父 readme（含 rename 后的新名）
    for path in list(docs) + [f"{PROJ}/common-knowledge/{NEW_TITLE}.md"]:
        hard_delete_doc(path)


@pytest.fixture
def subproject_docs(backend_running, test_docs):
    """子项目 fixture（批 2 S13/S24 用）：Training 下建"测试子项目"（文档 + readme）。

    readme 直接写测试库文件（后端 API 拒绝 readme 400）；子项目识别靠 list 目录。
    独立 fixture：建子项目会让归属候选 +1（_ensureProjectTree 收所有目录），
    不能放进 test_docs 否则污染候选=7 断言。
    """
    # 无论是否存在都覆盖创建，保证干净起点（防残留污染复用）
    api("POST", f"/api/document/{urllib.parse.quote(DOC_SUB, safe='/')}",
        {"content": "# Auto Sub 文档\n\n子项目文档正文。\n\n## 子级标题\n\n内容。\n\n引用 [Main](ref:" + DOC_MAIN + ")", "summary": "子项目摘要"})
    sub_readme = KB_ROOT / SUB_README
    sub_readme.parent.mkdir(parents=True, exist_ok=True)
    sub_readme.write_text("# 测试子项目\n\n子项目 readme。", encoding="utf-8")
    yield DOC_SUB
    # 清理：文档真删（不进垃圾箱）+ 子项目目录物理移除 + git 提交 + readme 重建
    hard_delete_doc(DOC_SUB)
    import shutil
    sub_dir = KB_ROOT / SUB_PROJ
    if sub_dir.exists():
        shutil.rmtree(sub_dir, ignore_errors=True)
        # 子项目整目录已删：TRAIN readme 重建（去掉子项目条目）+ git 提交目录删除
        from backend.readme_generator import ReadmeGenerator
        from backend.storage import Storage
        storage = Storage(kb_root=KB_ROOT)
        template = KB_ROOT / "_templates" / "readme.md"
        if template.exists():
            gen = ReadmeGenerator(storage=storage, template_path=template)
            gen.rebuild(TRAIN)
        _git_commit_if_changed(
            [str(KB_ROOT / SUB_PROJ), str(KB_ROOT / TRAIN / "readme.md")],
            "test-cleanup: remove subproject dir",
        )


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.add_init_script("""
      window.__toasts = [];
      new MutationObserver(() => {
        document.querySelectorAll('.toast-container .toast').forEach(t => {
          if (!t.dataset.captured) { t.dataset.captured = '1'; window.__toasts.push(t.textContent); }
        });
      }).observe(document.documentElement, {childList: true, subtree: true});
    """)
    yield pg
    ctx.close()
