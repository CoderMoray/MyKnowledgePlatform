"""MCP server for MyKnowledge.

Created via ``create_mcp_app(storage, gen)``; the CLI entry point passes both.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from backend.storage import Storage


def _attach_identity(meta: dict, is_new: bool) -> None:
    """Set ``author`` (once) and ``maintainer`` (always) from identity config.

    Raises ``FileNotFoundError`` if identity has not been configured
    (user must run ``myknowledge login`` first).
    """
    from backend.config import get_identity
    nick, email = get_identity()  # will raise if not configured
    author_str = f"{nick} <{email}>"
    if is_new:
        meta["author"] = author_str
    meta["maintainer"] = author_str


def _lock_file(kb_root: Path) -> Path:
    """Path to the AI session lock file."""
    return kb_root / ".lock"


_LOCK_TIMEOUT = 300  # 5 minutes


def acquire_lock(storage: Storage) -> bool:
    """Try to acquire the AI session lock.

    Returns ``True`` if the lock was acquired (or the old lock expired).
    Returns ``False`` if another process holds a valid lock.
    """
    import os, time
    lock = _lock_file(storage.kb_root)
    if lock.exists():
        try:
            ts = int(lock.read_text(encoding="utf-8").split(":")[1])
            if time.time() - ts < _LOCK_TIMEOUT:
                return False  # held by another process
        except (ValueError, IndexError, OSError):
            pass  # corrupt or unreadable — reclaim
    lock.write_text(f"{os.getpid()}:{int(time.time())}", encoding="utf-8")
    return True


def release_lock(storage: Storage) -> None:
    """Release the AI session lock (no-op if absent)."""
    lock = _lock_file(storage.kb_root)
    lock.unlink(missing_ok=True)


def rename_project(storage: Storage, old_rel: str, new_name: str) -> str:
    """Rename a project: directory mv + ref replacement + rebuild.

    Returns a confirmation message.  Raises ``ValueError`` if the
    project has uncommitted changes (user must handle them first).
    """
    import shutil, re
    from backend.git_manager import GitManager

    kb_root = storage.kb_root
    old_dir = kb_root / old_rel
    if not old_dir.is_dir():
        raise FileNotFoundError(f"项目不存在: {old_rel}")

    # ── 1. Check for dirty files ──────────────────────────
    gm = GitManager(kb_root)
    dirty = gm.has_uncommitted_changes()
    if dirty:
        # Check if any dirty file is under this project
        status = gm._run("status", "--porcelain", "--", str(old_dir))
        if status:
            dirty_files = []
            for line in status.strip().split("\n"):
                if line.strip():
                    dirty_files.append(line.strip().split()[-1])
            raise ValueError(
                f"项目有未提交的变更，请先处理：\n"
                + "\n".join(f"  • {f}" for f in dirty_files)
                + "\n\n请调 maint__read_diff 处理后再重试。"
            )

    # ── 2. Compute new path ──────────────────────────────
    parts = old_rel.split("/")
    parts[-1] = new_name
    new_rel = "/".join(parts)
    new_dir = kb_root / new_rel
    if new_dir.exists():
        raise FileExistsError(f"目标路径已存在: {new_rel}")

    # ── 3. Move directory ────────────────────────────────
    shutil.move(str(old_dir), str(new_dir))

    # Files to track for git commit (start with the moved dir)
    committed_files = set()
    for f in new_dir.rglob("*"):
        if f.is_file():
            committed_files.add(str(f))

    # ── 4. Replace ref: links ────────────────────────────
    old_prefix = f"{old_rel}/"
    new_prefix = f"{new_rel}/"
    ref_pattern = re.compile(r'(ref:)' + re.escape(old_prefix))

    for md_file in kb_root.rglob("*.md"):
        if ".git" in md_file.parts:
            continue
        text = md_file.read_text(encoding="utf-8")
        if old_prefix in text:
            updated = ref_pattern.sub(r'\g<1>' + new_prefix, text)
            md_file.write_text(updated, encoding="utf-8")
            committed_files.add(str(md_file))

    # ── 5. Also scan _refs/ directories ──────────────────
    for refs_dir in kb_root.rglob("_refs"):
        for md_file in refs_dir.rglob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            if old_prefix in text:
                updated = ref_pattern.sub(r'\g<1>' + new_prefix, text)
                md_file.write_text(updated, encoding="utf-8")
                committed_files.add(str(md_file))

    # ── 6. Update readme frontmatter name ────────────────
    readme_path = new_dir / "readme.md"
    if readme_path.exists():
        meta, body = storage.read_document(f"{new_rel}/readme.md")
        meta["name"] = new_name
        storage.write_readme(new_rel, meta, body)

    # ── 7. Rebuild ───────────────────────────────────────
    from backend.readme_generator import ReadmeGenerator
    template = kb_root / "_templates" / "readme.md"
    if template.exists():
        gen = ReadmeGenerator(storage=storage, template_path=template)
        gen.rebuild(new_rel)
        gen.rebuild("")
        gen.rebuild_project_status()
        # Track rebuild files
        for f in [kb_root / "readme.md", kb_root / "project-status.md",
                  new_dir / "readme.md"]:
            if f.exists():
                committed_files.add(str(f))

    # ── 8. Git commit (specific files only, skip if no repo) ──
    try:
        file_args = sorted(f for f in committed_files if Path(f).is_file())
        if file_args:
            gm._run("add", "--", *file_args)
            gm.commit(f"rename: {old_rel.split('/')[-1]} → {new_name}")
        from backend.events import broadcast as _evt
        _evt(storage.kb_root)
    except Exception:
        pass  # git 未初始化时跳过 commit

    return f"✓ 已重命名: {new_name}"


def rename_document(storage: Storage, old_rel: str, new_name: str) -> str:
    """Rename a single document: file mv + ref replacement + rebuild."""
    import shutil, re

    old_path = storage.kb_root / old_rel
    if not old_path.is_file():
        raise FileNotFoundError(f"文件不存在: {old_rel}")

    # Compute new path (same directory, new name)
    new_rel = str(Path(old_rel).parent / new_name)
    new_path = storage.kb_root / new_rel
    if new_path.exists():
        raise FileExistsError(f"目标文件已存在: {new_rel}")

    # Move
    shutil.move(str(old_path), str(new_path))

    committed_files = {str(new_path)}

    # Replace ref: links (exact path match only)
    old_escaped = re.escape(old_rel)
    pattern = re.compile(r'(ref:)' + old_escaped + r'(?=[\): ]|$)')

    for md_file in storage.kb_root.rglob("*.md"):
        if ".git" in md_file.parts:
            continue
        text = md_file.read_text(encoding="utf-8")
        if old_rel in text:
            updated = pattern.sub(r'\g<1>' + new_rel, text)
            if updated != text:
                md_file.write_text(updated, encoding="utf-8")
                committed_files.add(str(md_file))

    # Also scan _refs/ directories
    for refs_dir in storage.kb_root.rglob("_refs"):
        for md_file in refs_dir.rglob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            if old_rel in text:
                updated = pattern.sub(r'\g<1>' + new_rel, text)
                if updated != text:
                    md_file.write_text(updated, encoding="utf-8")
                    committed_files.add(str(md_file))

    # Rebuild parent project readme
    from backend.readme_generator import ReadmeGenerator
    template = storage.kb_root / "_templates" / "readme.md"
    parent_rel = _parent_rel(old_rel)
    if template.exists() and parent_rel:
        gen = ReadmeGenerator(storage=storage, template_path=template)
        gen.rebuild(parent_rel)
        gen.rebuild_project_status()
        committed_files.add(str(storage.kb_root / "readme.md"))
        committed_files.add(str(storage.kb_root / "project-status.md"))

    # Git commit
    from backend.git_manager import GitManager
    try:
        gm = GitManager(storage.kb_root)
        file_args = sorted(f for f in committed_files if Path(f).is_file())
        if file_args:
            gm._run("add", "--", *file_args)
            gm.commit(f"rename: {old_rel.split('/')[-1]} → {new_name}")
        from backend.events import broadcast as _evt
        _evt(storage.kb_root)
    except Exception:
        pass

    return f"✓ 已重命名: {old_rel.split('/')[-1]} → {new_name}"


def _parent_rel(path: str) -> str:
    """Determine the project_rel that owns a given document path.

    Examples:
        ``"common-knowledge/doc.md"`` → ``""`` (root)
        ``"projects/p1/common-knowledge/doc.md"`` → ``"projects/p1"``
    """
    idx = path.find("/common-knowledge/")
    if idx == -1 and path.startswith("common-knowledge/"):
        return ""
    if idx >= 0:
        return path[:idx]
    # fallback: parent directory
    idx = path.rfind("/")
    return path[:idx] if idx > 0 else ""


def _validate_path(
    path: str,
    kind: str = "auto",
    storage: object = None,
) -> None:
    """Validate a knowledge base path and raise a helpful ``ValueError``.

    Parameters
    ----------
    path:
        KB-relative path to validate.
    kind:
        ``"file"`` — must be a ``.md`` file under ``common-knowledge/``,
        ``projects/``, or ``archive/``.
        ``"dir"``  — must be a project directory under ``projects/`` or
        ``archive/`` (used by rebuild, rename, project-meta).
        ``"auto"`` — if ``path`` ends with ``.md`` → file, else → dir.
    storage:
        When provided, also verifies the path exists on disk.
        If ``None``, only checks format.

    The error message includes recovery instructions so AI agents can
    self-correct without human intervention.
    """
    # ── Guard 1: path traversal ──────────────────────────────
    if ".." in path.split("/"):
        _raise_path_error(
            path,
            f"路径包含非法字符「..」，禁止路径穿越。\n"
            f"请使用 KB 相对路径，例如：\"projects/首页重构/common-knowledge/xxx.md\"",
        )

    # ── Guard 2: absolute prefix ────────────────────────────
    if path.startswith("/"):
        _raise_path_error(
            path,
            f"路径以「/」开头，这是绝对路径。\n"
            f"请使用 KB 相对路径，例如：\"projects/首页重构/common-knowledge/xxx.md\"",
        )

    # ── Determine kind ──────────────────────────────────────
    is_dir = kind == "dir" or (kind == "auto" and not path.endswith(".md"))
    is_file = kind == "file" or (kind == "auto" and path.endswith(".md"))

    # Empty string is only valid for dir kind (root)
    if not path:
        if kind == "file":
            _raise_path_error(path, "文档路径不能为空。")
        return  # root dir — always valid

    # ── Guard 3: file-specific rules ────────────────────────
    if is_file:
        if not path.endswith(".md"):
            _raise_path_error(
                path,
                f"文档文件必须以「.md」结尾。\n\n"
                f"正确示例：\n"
                f'  • write__create_document(path="common-knowledge/术语表.md", ...)\n'
                f'  • write__create_document(path="projects/首页重构/common-knowledge/改版方案.md", ...)\n'
                f'  • write__create_document(path="archive/平台 Logo 设计/common-knowledge/设计需求.md", ...)',
            )
        valid_prefixes = ("common-knowledge/", "projects/", "archive/")
        if not path.startswith(valid_prefixes):
            _raise_path_error(
                path,
                f"文档路径必须以「common-knowledge/」「projects/」或「archive/」开头。\n\n"
                f"恢复方法：\n"
                f"  1. 调 nav__list_dir(project_rel=\"projects\") 列出所有活跃项目\n"
                f"  2. 调 nav__list_dir(project_rel=\"archive\") 列出所有归档项目\n"
                f"  3. 选择一个项目，路径格式为：projects/项目名/common-knowledge/文件名.md\n\n"
                f"正确示例：\n"
                f'  write__create_document(path="common-knowledge/术语表.md", ...)\n'
                f'  write__create_document(path="projects/首页重构/common-knowledge/改版方案.md", ...)',
            )

    # ── Guard 4: dir-specific rules ─────────────────────────
    if is_dir:
        if path in ("projects", "archive"):
            _raise_path_error(
                path,
                f"「{path}」是系统目录，不是项目。\n\n"
                f"正确用法：\n"
                f"  • 根层（重建根 readme）：不传 project_rel 或传 \"\"\n"
                f"  • 具体项目：\"projects/项目名称\"（例如：\"projects/首页重构\"）\n"
                f"  • 已归档项目：\"archive/项目名称\"\n"
                f"  • 子项目：\"projects/父项目/projects/子项目\"\n\n"
                f"恢复方法：\n"
                f"  1. 调 nav__list_dir(project_rel=\"projects\") 列出所有活跃项目\n"
                f"  2. 调 nav__list_dir(project_rel=\"archive\") 列出所有归档项目\n"
                f"  3. 用列出的项目名构造正确路径重试\n\n"
                f"例如：maint__rebuild_index(project_rel=\"projects/首页重构\")",
            )
        if not path.startswith(("projects/", "archive/")):
            _raise_path_error(
                path,
                f"项目路径应以「projects/」或「archive/」开头。\n\n"
                f"恢复方法：\n"
                f"  1. 调 nav__list_dir(project_rel=\"projects\") 列出所有活跃项目\n"
                f"  2. 调 nav__list_dir(project_rel=\"archive\") 列出所有归档项目\n"
                f"  3. 用列出的项目名构造正确路径重试\n\n"
                f"例如：maint__rebuild_index(project_rel=\"projects/首页重构\")",
            )

    # ── Guard 5: existence check ────────────────────────────
    if storage is not None:
        target = storage.kb_root / path
        if is_file and not target.is_file():
            tool_hint = ('write__update_document' if kind != 'file' else 'write__create_document')
            _raise_path_error(
                path,
                f"文档不存在：{path}\n\n"
                f"可能的原因：\n"
                f"  • 文件名或路径拼写错误\n"
                f"  • 文件在另一个项目下\n\n"
                f"恢复方法：\n"
                f"  1. 如果是新建文档，用 write__create_document（不要用{kind}）\n"
                f"  2. 调 nav__get_document_with_refs(path) 确认路径是否正确\n"
                f"  3. 调 nav__list_dir(project_rel=\"projects\") 列出所有项目，确认正确的项目名",
            )
        if is_dir and not target.is_dir():
            _raise_path_error(
                path,
                f"项目目录不存在：{path}\n\n"
                f"恢复方法：\n"
                f"  1. 调 nav__list_dir(project_rel=\"projects\") 列出所有活跃项目\n"
                f"  2. 调 nav__list_dir(project_rel=\"archive\") 列出所有归档项目\n"
                f"  3. 确认项目名是否正确（注意空格和大小写），重试",
            )


def _raise_path_error(path: str, detail: str) -> None:
    """Raise a formatted ``ValueError`` with recovery instructions.

    The error message is designed for AI agents to self-correct:
    what went wrong → correct format → how to discover correct paths → example.
    """
    raise ValueError(
        f"路径错误：{path or '(空)'}\n\n"
        f"{detail}\n\n"
        f"──\n"
        f"💡 如果不确定当前有哪些项目，请先调 nav__list_dir 查看。"
    )


def _validate_project_rel(project_rel: str, storage: object) -> None:
    """(Legacy alias) """  # kept for backward compat — delegates to _validate_path
    try:
        _validate_path(project_rel, kind="dir", storage=storage)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def _git_commit(kb_root: Path, message: str) -> None:
    """Helper: git commit (no-op if git is not initialized)."""
    from backend.git_manager import GitManager
    gm = GitManager(kb_root)
    try:
        gm.commit(message)
    except Exception:
        pass  # non-fatal for MCP tools


def _auto_archive(parent_rel: str, storage: Storage, gen: object) -> None:
    """Move non-active projects from ``projects/`` to ``archive/``."""
    if not parent_rel.startswith("projects/"):
        return
    project_name = parent_rel.split("/")[-1]
    src = storage.kb_root / parent_rel
    dst = storage.kb_root / "archive" / project_name
    if dst.exists():
        return
    try:
        meta, _ = storage.read_document(f"{parent_rel}/readme.md")
    except FileNotFoundError:
        return
    if meta.get("status", "active") == "active":
        return

    import shutil
    shutil.move(str(src), str(dst))
    gen.rebuild("")   # type: ignore[union-attr]
    gen.rebuild_project_status()   # type: ignore[union-attr]
    _git_commit(storage.kb_root, f"archive: {project_name} → {meta.get('status', '?')}")
    from backend.events import broadcast as _evt
    _evt(storage.kb_root)


def create_mcp_app(storage: Storage,
                   gen: Optional[object] = None,
                   gm: Optional[object] = None) -> FastMCP:
    """Build the FastMCP application with all tools.

    Args:
        storage: ``Storage`` instance for the KB.
        gen:     ``ReadmeGenerator`` (enables write-through).
        gm:      ``GitManager`` (enables diff & checkpoint tools).
    """

    mcp = FastMCP("MyKnowledge")

    # ══════════════════════════════════════════════════════════
    #  Read-only tools
    # ══════════════════════════════════════════════════════════

    @mcp.tool()
    def nav__read_readme(project_rel: str = "") -> str:
        """[nav] Read the routing index (readme.md) of a knowledge base layer.

        Args:
            project_rel: KB-relative path, e.g. ``"projects/以旧换新"``.
                         Leave empty to read the root readme.
        Returns:
            Full markdown content of the readme (frontmatter + body).
        """
        path = f"{project_rel}/readme.md" if project_rel else "readme.md"
        return storage.read_content(path)

    @mcp.tool()
    def nav__list_dir(project_rel: str = "") -> str:
        """[nav] List files and directories in a knowledge base layer.

        Args:
            project_rel: KB-relative path, e.g. ``"projects/以旧换新"``.
        Returns:
            Formatted table (directory marker, name, last modified).
        """
        entries = storage.list_children(project_rel)
        if not entries:
            return "(空目录)"
        lines = ["类型    名称              修改日期"]
        lines.append("─" * 50)
        for e in entries:
            marker = "📁" if e.is_dir else "  "
            lines.append(f"{marker}   {e.name:<20} {e.modified}")
        return "\n".join(lines)

    @mcp.tool()
    def nav__get_document(path: str) -> str:
        """[nav] Read the full content of a knowledge document.

        Args:
            path: KB-relative path, e.g. ``"common-knowledge/补贴标准.md"``
                  or ``"projects/以旧换新/common-knowledge/补贴标准.md"``.
        Returns:
            Full markdown content (frontmatter + body).
        """
        return storage.read_content(path)

    # ══════════════════════════════════════════════════════════
    #  Write tools
    # ══════════════════════════════════════════════════════════

    def _write_through(parent_rel: str, msg: str) -> None:
        """Rebuild indices and commit. Raises if no write lock."""
        if gen is None:
            return
        # ── Lock check ──────────────────────────────
        if not _lock_file(storage.kb_root).exists():
            raise RuntimeError(
                "错误：写锁不存在。\n\n"
                "你的工作流顺序有误 — 必须先完成维护流程才能执行写操作。\n\n"
                "请按以下步骤修正：\n"
                "  1. maint__acquire_lock\n"
                "  2. maint__read_diff（处理待提交的变更）\n"
                "  3. 确认变更后继续\n\n"
                "完成这三步后再重新调用本工具。"
            )
        gen.rebuild(parent_rel)               # type: ignore[union-attr]
        gen.rebuild_project_status()          # type: ignore[union-attr]
        _git_commit(storage.kb_root, msg)

        # ── Auto-archive: non-active projects move to archive/ ──
        if parent_rel.startswith("projects/") and gen is not None:
            _auto_archive(parent_rel, storage, gen)

        from backend.events import broadcast as _evt
        _evt(storage.kb_root)

    @mcp.tool()
    def write__create_document(path: str, content: str,
                        summary: str = "",
                        doc_type: str = "knowledge") -> str:
        """[write] Create a new knowledge document in the KB.

        Args:
            path:   KB-relative path, e.g. ``"common-knowledge/补贴标准.md"``
                    or ``"projects/以旧换新/common-knowledge/流程.md"``.
            content:  Markdown body (without frontmatter).
            summary:  One-line description (stored in frontmatter).
            doc_type: ``knowledge`` | ``artifact`` | ``note``.
        Returns:
            The document id (auto-generated).
        """
        _validate_path(path, kind="file")
        meta = {"type": doc_type}
        if summary:
            meta["summary"] = summary
        _attach_identity(meta, is_new=True)
        written = storage.write_document(path, meta, content)
        parent_rel = _parent_rel(path)
        _write_through(parent_rel, f"create: {path}")
        return written["id"]

    @mcp.tool()
    def write__update_document(path: str, content: str = "",
                        summary: str = "") -> str:
        """[write] Update an existing knowledge document.

        Fields left empty keep their current value.
        Args:
            path:    KB-relative path to the existing .md file.
            content: New markdown body (leave empty to keep existing).
            summary: New one-line description (leave empty to keep existing).
        Returns:
            The document id.
        """
        _validate_path(path, kind="file", storage=storage)
        old_meta, old_body = storage.read_document(path)
        if content:
            new_body = content
        else:
            new_body = old_body

        new_meta = dict(old_meta)
        if summary:
            new_meta["summary"] = summary
        else:
            new_meta.pop("summary", None)
        _attach_identity(new_meta, is_new=False)

        written = storage.write_document(path, new_meta, new_body,
                                         auto_id=False)
        parent_rel = _parent_rel(path)
        _write_through(parent_rel, f"update: {path}")
        return written.get("id", "")

    @mcp.tool()
    def write__update_project_meta(project_rel: str,
                            name: str = "",
                            summary: str = "",
                            status: str = "") -> str:
        """[write] Update project-level metadata (stored in readme frontmatter).

        Args:
            project_rel: KB-relative project path, e.g. ``"projects/以旧换新"``.
                         Use ``""`` for root.
            name:        New project name (leave empty to keep).
            summary:     New description (leave empty to keep).
            status:      ``active`` | ``completed`` | ``cancelled`` | ``abandoned``.
        Returns:
            The project id.
        """
        if project_rel:
            _validate_path(project_rel, kind="dir", storage=storage)
        readme_path = f"{project_rel}/readme.md" if project_rel else "readme.md"
        old_meta, old_body = storage.read_document(readme_path)

        new_meta = dict(old_meta)
        if name:
            new_meta["name"] = name
        if summary:
            new_meta["summary"] = summary
        if status:
            new_meta["status"] = status
        new_meta["updated"] = __import__("datetime").date.today().isoformat()

        storage.write_document(readme_path, new_meta, old_body, auto_id=False)

        # Rebuild parent readme (so its child entries reflect new summary)
        if gen is not None:
            parent = "/".join(project_rel.split("/")[:-1]) if project_rel else ""
            if parent in ("", "."):
                gen.rebuild("")                              # type: ignore[union-attr]
            else:
                gen.rebuild(parent)                          # type: ignore[union-attr]
            gen.rebuild_project_status()                     # type: ignore[union-attr]
            _git_commit(storage.kb_root, f"meta: {project_rel}")

        return new_meta.get("id", "")

    @mcp.tool()
    def write__delete_document(path: str) -> str:
        """[write] Delete a knowledge document from the KB.

        The file is removed from disk, but git history preserves it
        (can be recovered via ``git checkout``).

        Args:
            path: KB-relative path, e.g. ``"common-knowledge/补贴标准.md"``.
        Returns:
            Confirmation message.
        """
        _validate_path(path, kind="file", storage=storage)
        import os
        full = storage.kb_root / path
        if not full.exists():
            return f"⚠ 文件不存在: {path}"

        os.remove(str(full))
        parent_rel = _parent_rel(path)
        _write_through(parent_rel, f"delete: {path}")
        return f"✓ 已删除: {path}"

    @mcp.tool()
    def write__rename_project(project_rel: str, new_name: str) -> str:
        """Rename a project: directory, ref links, readme, indices.

        Args:
            project_rel: Current KB-relative path, e.g. ``"projects/以旧换新"``.
            new_name:    New project name, e.g. ``"二手置换"``.
        Returns:
            Confirmation or error message.
        """
        _validate_path(project_rel, kind="dir", storage=storage)
        from backend.mcp_server import rename_project as _rename
        try:
            return _rename(storage, project_rel, new_name)
        except (ValueError, FileNotFoundError, FileExistsError) as e:
            return str(e)

    @mcp.tool()
    def write__rename_document(path: str, new_name: str) -> str:
        """Rename a single document: file mv + ref links + rebuild.

        Args:
            path:     Current KB-relative path, e.g. ``"common-knowledge/补贴标准.md"``.
            new_name: New filename, e.g. ``"新标准.md"``.
        Returns:
            Confirmation or error message.
        """
        _validate_path(path, kind="file", storage=storage)
        from backend.mcp_server import rename_document as _rd
        try:
            return _rd(storage, path, new_name)
        except (ValueError, FileNotFoundError, FileExistsError) as e:
            return str(e)

    @mcp.tool()
    def maint__validate_doc(path: str) -> str:
        """[maint] Check a document's frontmatter integrity.

        Args:
            path: KB-relative path to the .md file.
        Returns:
            Validation report (issues listed, or "✓ 格式正常").
        """
        _validate_path(path, kind="file", storage=storage)
        try:
            meta, body = storage.read_document(path)
        except FileNotFoundError:
            return f"✗ 文件不存在: {path}"
        except Exception as e:
            return f"✗ 读取失败: {e}"

        issues: list[str] = []
        if not isinstance(meta, dict):
            issues.append("frontmatter 不是合法的 YAML dict")
        else:
            if "summary" not in meta or not meta.get("summary"):
                issues.append("缺少 summary 字段")
            if "type" not in meta:
                issues.append("缺少 type 字段")
            if not body.strip():
                issues.append("正文为空")

        if not issues:
            return f"✓ {path} 格式正常"
        return f"⚠ {path}\n" + "\n".join(f"  • {i}" for i in issues)

    @mcp.tool()
    def maint__read_diff(from_hash: str = "") -> str:
        """[maint] Read git diff for agent inspection.

        Args:
            from_hash: Git commit hash to diff from.  Leave empty to diff
                       from the checkpoint (``agent-commit.txt``) to HEAD.
        Returns:
            Diff text, or a message explaining why no diff is available.
        """
        if gm is None:
            return "Git 管理器未就绪"

        cp_file = storage.kb_root / "agent-commit.txt"

        if from_hash:
            try:
                return gm.read_diff(from_hash)  # type: ignore[union-attr]
            except Exception as e:
                return f"diff 失败: {e}"

        # From checkpoint to HEAD
        head = gm.get_head_hash()  # type: ignore[union-attr]
        if not head:
            return "尚无任何 commit"
        cp = gm.read_checkpoint(cp_file)  # type: ignore[union-attr]
        if not cp:
            return "无 checkpoint 记录，请指定 from_hash"
        try:
            return gm.read_diff(cp, head)  # type: ignore[union-attr]
        except Exception as e:
            return f"diff 失败: {e}"

    @mcp.tool()
    def maint__check_integrity() -> str:
        """[maint] Run integrity check: GC + rebuild status.

        Returns a summary report.
        """
        from backend.readme_generator import ReadmeGenerator
        gen_local = gen
        report: list[str] = []

        if gen_local is not None:
            removed = gen_local.garbage_collect()
            if removed:
                report.append(f"已清除过期项目: {', '.join(removed)}")
            else:
                report.append("无过期项目需要清理")

            gen_local.rebuild_project_status()
            report.append("项目状态已更新")

        return "\n".join(report) if report else "检查完成，无变更。"

    @mcp.tool()
    def share__publish(project_rel: str,
                        with_context: bool = False) -> str:
        """[share] Export a project subtree as an encrypted .mkpkg file.

        Args:
            project_rel:  KB-relative project path, e.g. ``"projects/以旧换新"``.
            with_context: If True, scan for ``ref:`` references pointing
                          outside the subtree and include them in ``_refs/``.
        Returns:
            Absolute path to the generated .mkpkg file.
        """
        from backend.share import publish as _publish
        return _publish(storage, project_rel, with_context=with_context)

    @mcp.tool()
    def share__import_share(file_path: str,
                     sharer_email: str = "") -> str:
        """[share] Import a .mkpkg package into the knowledge base.

        Args:
            file_path:    Path to the .mkpkg file.
            sharer_email: Email of the person who created the package.
                          Leave empty to try the local identity first.
        Returns:
            Import result message.
        """
        from backend.share import import_share as _import
        return _import(storage, file_path, sharer_email=sharer_email)

    @mcp.tool()
    def maint__rebuild_index(project_rel: str = "") -> str:
        """[maint] Manually rebuild the readme index for a project layer.

        Args:
            project_rel: Path to rebuild, e.g. ``"projects/以旧换新"``
                         or ``""`` for root.
        Returns:
            Confirmation message.
        """
        _validate_project_rel(project_rel, storage)
        if gen is not None:
            gen.rebuild(project_rel)
            if project_rel == "":
                gen.rebuild_project_status()
            return f"✓ 已重建: {project_rel or 'root'}"
        return "生成器未就绪"

    @mcp.tool()
    @mcp.tool()
    def nav__get_document_with_refs(path: str) -> str:
        """[nav] Read a document and append referenced content.

        Inline references use Markdown link syntax with ``ref:`` prefix:

            [text](ref:path)
            [text](ref:path::section_title)

        The tool extracts all refs from the body, reads the latest content
        for each, and appends a references section at the end.  One level
        deep only (no recursive follow-through).
        """
        import re

        try:
            meta, body = storage.read_document(path)
        except FileNotFoundError:
            return f"⚠ 文件不存在: {path}"

        # ── Scan for inline refs ────────────────────────────
        ref_pattern = re.compile(r'\]\(ref:([^\s)]+?)(?:::([^)]*))?\)')
        raw_refs = ref_pattern.findall(body)
        seen: set[str] = {path}
        ref_list: list[tuple[str, str]] = []  # (ref_path, section_title)
        for ref_path, section in raw_refs:
            if ref_path not in seen:
                seen.add(ref_path)
                ref_list.append((ref_path, section))

        # ── Build main content ──────────────────────────────
        parts = [f"---\n{_yaml_dump(meta)}---\n\n{body}"]

        # ── Resolve references (refs/ first, then original) ─
        if ref_list:
            parts.append("\n\n--- 参考文献 ---\n")
            for i, (ref_path, section) in enumerate(ref_list, 1):
                try:
                    ref_meta, ref_body = _resolve_ref(path, ref_path, storage)
                except FileNotFoundError:
                    parts.append(f"[{i}] {ref_path} (⚠ 不存在)\n")
                    continue

                if section:
                    excerpt = _extract_section(ref_body, section)
                    if excerpt is not None:
                        content = f"---\n{_yaml_dump(ref_meta)}---\n\n{excerpt}"
                    else:
                        content = (
                            f"⚠ 未找到段落「{section}」"
                            f"— 返回全文\n"
                            f"---\n{_yaml_dump(ref_meta)}---\n\n{ref_body}"
                        )
                else:
                    content = f"---\n{_yaml_dump(ref_meta)}---\n\n{ref_body}"

                parts.append(
                    f"[{i}] {ref_path}"
                    + (f" :: {section}" if section else "")
                    + f"\n{content}\n"
                )

        return "".join(parts)

    @mcp.tool()
    def maint__acquire_lock() -> str:
        """Acquire the AI session write lock.

        Only one process can hold the lock at a time (5 min timeout).
        Call this before making any write operations.
        Returns a confirmation string.
        """
        ok = acquire_lock(storage)
        return "LOCK ACQUIRED" if ok else "LOCK BUSY (another process holds it)"

    @mcp.tool()
    def maint__release_lock() -> str:
        """Release the AI session write lock.

        Call this after completing all write operations.
        """
        release_lock(storage)
        return "LOCK RELEASED"

    @mcp.prompt()
    def nav__maintenance_procedure() -> str:
        """每次对话开始时执行的知识库维护流程。"""
        return """## 知识库维护流程

每次与用户对话开始时，请按以下顺序自动执行：

### 1. 获取锁
调 `maint__acquire_lock`：
- 返回 "LOCK ACQUIRED" → 继续
- 返回 "LOCK BUSY" → 等待几秒后重试，最多 3 次，仍忙则通知用户稍后再试

### 2. 检查待处理的变更
调 `maint__read_diff` 对比 checkpoint 到 HEAD：

- 无差异 → 开始对话
- 有差异 → 读 diff → `maint__validate_doc` 检查 frontmatter
  → `maint__rebuild_index` 修复索引
  → 总结变更给用户 → 用户确认 → 不做额外 commit（用户确认即可）
  → 更新 checkpoint（写 agent-commit.txt 或用 write__update_project_meta）

### 3. 回答问题
正常与用户对话，需要读写时调对应的 MCP 工具。

### 4. 结束前
完成所有工作后：
1. `maint__release_lock`
2. 告知用户「知识库已同步」
"""

    return mcp


def _yaml_dump(data: dict) -> str:
    import yaml
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()


def _resolve_ref(main_path: str, ref_path: str,
                 storage: Storage) -> tuple[dict, str]:
    """Resolve a ``ref:`` reference, checking ``_refs/`` first.

    Returns ``(meta, body)`` from the first available source:
      1. ``当前项目/_refs/<ref_path>`` (imported context, highest priority)
      2. ``<ref_path>`` (original KB-relative path)
    Raises ``FileNotFoundError`` if neither exists.
    """
    # Try _refs/ first
    if main_path.startswith("projects/"):
        parts = main_path.split("/")
        project_rel = f"{parts[0]}/{parts[1]}"
        refs_path = f"{project_rel}/_refs/{ref_path}"
        try:
            return storage.read_document(refs_path)
        except FileNotFoundError:
            pass

    # Fallback to original path
    return storage.read_document(ref_path)


def _extract_section(text: str, title: str) -> str | None:
    """Extract content under a markdown heading from *text*.

    Returns ``None`` if *title* is not found.
    """
    import re

    # Build pattern: match `## title` or `# title` at line start
    esc_title = re.escape(title.strip())
    pattern = re.compile(r'^#{1,6}\s+' + esc_title + r'\s*$', re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return None

    heading_level = len(m.group().split()[0])  # number of # characters
    start = m.end()

    # Find next heading of same or lower level
    next_pat = re.compile(
        r'^#{1,' + str(heading_level) + r'}\s+\S', re.MULTILINE
    )
    next_m = next_pat.search(text, start)
    if next_m:
        return text[start:next_m.start()].strip()
    return text[start:].strip()
