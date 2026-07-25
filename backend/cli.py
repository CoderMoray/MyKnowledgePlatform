"""CLI entry point — ``myknowledge init``, ``serve``, ``mcp``, etc.

Usage (development)::

    python -m backend.cli init [--root /path/to/kb]
    python -m backend.cli mcp     [--root /path/to/kb]
    python -m backend.cli serve   [--root /path/to/kb]
    python -m backend.cli rebuild [path]
    python -m backend.cli check

Once installed::

    myknowledge init
    myknowledge mcp
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Optional

from backend.config import resolve_root
from backend.git_manager import GitManager
from backend.storage import Storage


# ══════════════════════════════════════════════════════════════
#  init
# ══════════════════════════════════════════════════════════════

_PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"


def _check_git() -> str | None:
    """Check if git binary is available.  Returns an error hint or *None*."""
    import subprocess
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=10)
        return None
    except FileNotFoundError:
        return "git 未安装。请先安装 Git：https://git-scm.com/downloads"
    except Exception:
        return "git 执行异常，请确认已安装"


_REQUIRED_PACKAGES = {
    "yaml": ("PyYAML", "pip install pyyaml"),
    "mcp": ("mcp", "pip install mcp"),
    "git": ("GitPython", "pip install gitpython"),
}


def _check_python_deps(mirror: str = "") -> list[str]:
    """Try importing required packages.  Returns a list of install hints."""
    hints: list[str] = []
    for mod, (pkg, cmd) in _REQUIRED_PACKAGES.items():
        try:
            __import__(mod)
        except ImportError:
            if mirror:
                hints.append(f"  {cmd} -i {mirror}")
            else:
                hints.append(f"  {cmd}")
    return hints


def _shipped_templates() -> Path:
    """Path to the default templates shipped with the package."""
    return Path(__file__).resolve().parent / "templates"


def cmd_init(args: argparse.Namespace) -> int:
    """Create a new knowledge base at the root path."""
    # ── Dependency check ──────────────────────────────────
    git_err = _check_git()
    dep_hints = _check_python_deps(mirror=args.mirror)

    if git_err or dep_hints:
        print("⚠ 缺少依赖，请先安装：", file=sys.stderr)
        if git_err:
            print(f"\n  {git_err}", file=sys.stderr)
        if dep_hints:
            print("\n  Python 包：", file=sys.stderr)
            for h in dep_hints:
                print(h, file=sys.stderr)
        return 1

    kb_root = resolve_root(args.root)

    if kb_root.exists():
        print(f"✗ {kb_root} already exists.", file=sys.stderr)
        return 1

    # Step 1: directory tree
    for d in ["_templates", "common-knowledge", "projects", "archive", "publish"]:
        (kb_root / d).mkdir(parents=True, exist_ok=True)

    # Step 2: copy default templates
    shipped = _shipped_templates()
    if shipped.is_dir():
        for src in shipped.iterdir():
            if src.suffix == ".md":
                shutil.copy2(src, kb_root / "_templates" / src.name)

    # Step 3: build initial readme + project-status
    storage = Storage(kb_root=kb_root)
    from backend.readme_generator import ReadmeGenerator
    template = kb_root / "_templates" / "readme.md"
    gen = ReadmeGenerator(storage=storage, template_path=template)
    gen.rebuild("", name="MyKnowledge", summary="项目知识库初始化", status="active")
    gen.rebuild_project_status()

    # Step 4: git init + first commit
    git = GitManager(kb_root)
    git.init()
    git.commit("init: 创建知识库")

    print(f"✓ 知识库已创建: {kb_root}")

    # ── Identity check ──────────────────────────────────
    from backend.config import get_identity
    try:
        get_identity()
    except (FileNotFoundError, ValueError):
        print("\n⚠ 身份未设置。请先运行:")
        print(f"  myknowledge login <your_email@example.com> <昵称>")
        print("  否则所有写入操作将失败。")

    return 0


# ══════════════════════════════════════════════════════════════
#  mcp
# ══════════════════════════════════════════════════════════════


def _auto_init(kb_root: Path) -> None:
    """Create KB directory + templates + root readme + git init."""
    for d in ["_templates", "common-knowledge", "projects", "archive", "publish"]:
        (kb_root / d).mkdir(parents=True, exist_ok=True)
    shipped = _shipped_templates()
    if shipped.is_dir():
        for src in shipped.iterdir():
            if src.suffix == ".md":
                shutil.copy2(src, kb_root / "_templates" / src.name)
    storage = Storage(kb_root=kb_root)
    from backend.readme_generator import ReadmeGenerator
    template = kb_root / "_templates" / "readme.md"
    gen = ReadmeGenerator(storage=storage, template_path=template)
    gen.rebuild("", name="MyKnowledge", summary="项目知识库初始化", status="active")
    gen.rebuild_project_status()
    git = GitManager(kb_root)
    git.init()
    git.commit("init: 创建知识库")


def cmd_mcp(args: argparse.Namespace) -> int:
    """Start the MCP server (stdio mode — for agent clients).

    Auto-initializes the KB on first run — user does not need to
    run ``init`` separately.
    """
    kb_root = resolve_root(args.root)
    if not kb_root.is_dir():
        _auto_init(kb_root)

    # ── Identity check (mandatory) ──────────────────────
    from backend.config import get_identity
    try:
        get_identity()
    except (FileNotFoundError, ValueError):
        print("✗ 身份未设置。请先运行:", file=sys.stderr)
        print("  myknowledge login <your_email@example.com> <昵称>", file=sys.stderr)
        return 1

    storage = Storage(kb_root=kb_root)
    from backend.readme_generator import ReadmeGenerator
    template = kb_root / "_templates" / "readme.md"
    gen = ReadmeGenerator(storage=storage, template_path=template)
    gen.garbage_collect()  # clean abandoned projects on startup

    from backend.git_manager import GitManager
    from backend.mcp_server import create_mcp_app
    gm = GitManager(kb_root)
    app = create_mcp_app(storage, gen=gen, gm=gm)
    app.run(transport="stdio")
    return 0


# ══════════════════════════════════════════════════════════════
#  check
# ══════════════════════════════════════════════════════════════


def cmd_check(args: argparse.Namespace) -> int:
    """Check knowledge base integrity: GC, rebuild status, report."""
    kb_root = resolve_root(args.root)
    if not kb_root.is_dir():
        print(f"✗ 知识库不存在: {kb_root}", file=sys.stderr)
        return 1

    storage = Storage(kb_root=kb_root)
    from backend.readme_generator import ReadmeGenerator
    template = kb_root / "_templates" / "readme.md"
    gen = ReadmeGenerator(storage=storage, template_path=template)

    removed = gen.garbage_collect()
    if removed:
        print(f"已清除过期项目: {', '.join(removed)}")
    else:
        print("✓ 无过期项目需要清理")

    gen.rebuild_project_status()
    print("✓ 项目状态已更新")
    return 0


# ══════════════════════════════════════════════════════════════
#  serve (FastAPI Web UI)
# ══════════════════════════════════════════════════════════════


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the FastAPI web server for the Web UI."""
    kb_root = resolve_root(args.root)
    if not kb_root.is_dir():
        _auto_init(kb_root)

    import os
    os.environ["MYKNOWLEDGE_ROOT"] = str(kb_root)

    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=args.port,
        reload=args.reload,
    )
    return 0


# ══════════════════════════════════════════════════════════════
#  login / whoami
# ══════════════════════════════════════════════════════════════


def cmd_login(args: argparse.Namespace) -> int:
    """Set identity (email + nickname)."""
    from backend.config import set_identity
    set_identity(args.email, args.nickname)
    print(f"✓ 身份已设置: {args.nickname} <{args.email}>")
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    from backend.config import get_identity
    try:
        nick, email = get_identity()
        print(f"{nick} <{email}>")
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


# ══════════════════════════════════════════════════════════════
#  publish / import_share
# ══════════════════════════════════════════════════════════════


def cmd_publish(args: argparse.Namespace) -> int:
    from backend.share import publish as _publish
    from backend.storage import Storage
    storage = Storage(kb_root=resolve_root(args.root))
    result = _publish(storage, args.path, with_context=args.with_context)
    print(result)
    return 0


def cmd_import_share(args: argparse.Namespace) -> int:
    from backend.share import import_share as _import
    from backend.storage import Storage
    storage = Storage(kb_root=resolve_root(args.root))
    result = _import(storage, args.file,
                     sharer_email=args.sharer_email)
    print(result)
    return 0


# ══════════════════════════════════════════════════════════════
#  argparse
# ══════════════════════════════════════════════════════════════

def _add_common_args(p: argparse.ArgumentParser) -> None:
    """Add --root to a subparser."""
    p.add_argument("--root", default=None,
                   help="KB 根目录（默认 ~/.myknowledge）")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="myknowledge",
        description="MyKnowledge — local-first 知识管理平台",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p = sub.add_parser("init", help="创建新知识库")
    _add_common_args(p)
    p.add_argument("--mirror", default="",
                   help=f"pip 镜像源，如 {_PIP_MIRROR}")
    p.set_defaults(func=cmd_init)

    # mcp
    p = sub.add_parser("mcp", help="启动 MCP server（stdio 模式）")
    _add_common_args(p)
    p.set_defaults(func=cmd_mcp)

    # check
    p = sub.add_parser("check", help="检查知识库完整性（清理过期项目等）")
    _add_common_args(p)
    p.set_defaults(func=cmd_check)

    # login / whoami
    p = sub.add_parser("login", help="设置身份（邮箱 + 昵称）")
    p.add_argument("email", help="邮箱地址")
    p.add_argument("nickname", help="昵称")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("whoami", help="显示当前身份")
    p.set_defaults(func=cmd_whoami)

    # publish
    p = sub.add_parser("publish", help="导出项目为分享包 .mkpkg")
    _add_common_args(p)
    p.add_argument("path", help="项目路径，如 projects/以旧换新")
    p.add_argument("--with-context", action="store_true",
                   help="同时打包 ref: 引用的外部文件到 _refs/")
    p.set_defaults(func=cmd_publish)

    # import_share
    p = sub.add_parser("import-share", help="导入 .mkpkg 分享包")
    _add_common_args(p)
    p.add_argument("file", help=".mkpkg 文件路径")
    p.add_argument("--sharer-email", default="",
                   help="分享者邮箱（为空则使用本地身份解密）")
    p.set_defaults(func=cmd_import_share)

    # serve
    p = sub.add_parser("serve", help="启动 Web UI（FastAPI）")
    _add_common_args(p)
    p.add_argument("--port", type=int, default=8080,
                   help="端口号（默认 8080）")
    p.add_argument("--reload", action="store_true",
                   help="开发模式：代码变更自动重启")
    p.set_defaults(func=cmd_serve)

    # rebuild — placeholder
    for name, help_text in [
        ("rebuild", "重建指定路径的 readme"),
    ]:
        p = sub.add_parser(name, help=help_text)
        _add_common_args(p)
        p.add_argument("path", nargs="?", default="",
                       help="操作目标路径")
        p.set_defaults(func=lambda _: (
            print(f"尚未实现: {name}", file=sys.stderr)))

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
