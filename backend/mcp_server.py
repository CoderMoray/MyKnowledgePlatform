"""MCP server for MyKnowledge.

Created via ``create_mcp_app(storage, gen)``; the CLI entry point passes both.
"""

from __future__ import annotations

import functools
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

    acquire_lock(storage)  # ensure lock held for this write
    # ── Lock check ──────────────────────────────
    if not _lock_file(kb_root).exists():
        raise RuntimeError(
            "错误：写锁不存在。\n\n"
            "你的工作流顺序有误 — 必须先完成维护流程才能执行写操作。\n\n"
            "请按以下步骤修正：\n"
            "  1. maint__acquire_lock\n"
            "  2. maint__read_diff（处理待提交的变更）\n"
            "  3. 确认变更后继续\n\n"
            "完成这三步后再重新调用本工具。"
        )

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

    release_lock(storage)
    return f"✓ 已重命名: {new_name}"


def rename_document(storage: Storage, old_rel: str, new_name: str) -> str:
    """Rename a single document: file mv + ref replacement + rebuild.

    Lock is guaranteed released via ``finally`` even on error.
    """
    import shutil, re

    acquire_lock(storage)  # ensure lock held for this write
    try:
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
    finally:
        release_lock(storage)


def delete_project(storage: Storage, project_rel: str) -> str:
    """Permanently delete a project directory and all its contents.

    The directory is removed from disk (git history preserves it).
    All ``ref:`` links pointing into this project are replaced
    with a ``(已删除)`` marker.  Parent readme and project-status
    are rebuilt.

    Returns a confirmation message.  Raises ``ValueError`` if the
    project has uncommitted changes (user must handle them first).
    """
    import shutil
    from backend.git_manager import GitManager
    from backend.readme_generator import ReadmeGenerator

    kb_root = storage.kb_root

    acquire_lock(storage)  # ensure lock held for this write
    # ── Lock check ──────────────────────────────
    if not _lock_file(kb_root).exists():
        raise RuntimeError(
            "错误：写锁不存在。\n\n"
            "你的工作流顺序有误 — 必须先完成维护流程才能执行写操作。\n\n"
            "请按以下步骤修正：\n"
            "  1. maint__acquire_lock\n"
            "  2. maint__read_diff（处理待提交的变更）\n"
            "  3. 确认变更后继续\n\n"
            "完成这三步后再重新调用本工具。"
        )

    old_dir = kb_root / project_rel
    if not old_dir.is_dir():
        raise FileNotFoundError(f"项目不存在: {project_rel}")

    project_name = project_rel.rstrip("/").split("/")[-1]

    # ── 1. Check for dirty files ──────────────────────────
    gm = GitManager(kb_root)
    dirty = gm.has_uncommitted_changes()
    if dirty:
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

    # ── 2. Move project into trash (recoverable) ─────────
    from backend.trash import move_project_to_trash
    trash_rel = move_project_to_trash(storage, project_rel)

    # ── 3. Rebuild ────────────────────────────────────────
    template = kb_root / "_templates" / "readme.md"
    committed_files = set()
    if template.exists():
        gen = ReadmeGenerator(storage=storage, template_path=template)
        # Rebuild parent
        parent_parts = project_rel.rstrip("/").split("/")
        if len(parent_parts) > 2 and parent_parts[-2] == "projects":
            parent_rel = "/".join(parent_parts[:-2])
        else:
            parent_rel = "/".join(parent_parts[:-1])
        if parent_rel and parent_rel not in ("projects", "archive", ""):
            gen.rebuild(parent_rel)
        gen.rebuild("")
        gen.rebuild_project_status()
        for f in [kb_root / "readme.md", kb_root / "project-status.md"]:
            if f.exists():
                committed_files.add(str(f))
        committed_files.add(str(kb_root / "trash"))

    # ── 4. Git commit ────────────────────────────────────
    try:
        committed_files.add(str(kb_root / project_rel))  # track deletion
        if committed_files:
            gm._run("add", "--", *sorted(str(f) for f in committed_files if Path(f).is_file()))
            gm._run("add", "--all", str(kb_root))  # ensure deletions tracked
            gm.commit(f"delete(trash): {project_rel}")
        from backend.events import broadcast as _evt
        _evt(kb_root)
    except Exception:
        pass

    release_lock(storage)
    return f"✓ 已移入垃圾箱: {project_rel} → {trash_rel}（30 天内可恢复）"


def move_project(storage: Storage, project_rel: str, target_parent_rel: str) -> str:
    """Move a project from its current parent to a different parent directory.

    Similar to ``rename_project`` but the destination is a different parent
    rather than a new name.  The project's own name is preserved.

    Returns a confirmation message.  Raises ``ValueError`` if the
    project has uncommitted changes (user must handle them first).
    """
    import shutil, re
    from backend.git_manager import GitManager
    from backend.readme_generator import ReadmeGenerator

    kb_root = storage.kb_root

    acquire_lock(storage)  # ensure lock held for this write
    # ── Lock check ──────────────────────────────
    if not _lock_file(kb_root).exists():
        raise RuntimeError(
            "错误：写锁不存在。\n\n"
            "你的工作流顺序有误 — 必须先完成维护流程才能执行写操作。\n\n"
            "请按以下步骤修正：\n"
            "  1. maint__acquire_lock\n"
            "  2. maint__read_diff（处理待提交的变更）\n"
            "  3. 确认变更后继续\n\n"
            "完成这三步后再重新调用本工具。"
        )

    old_dir = kb_root / project_rel
    if not old_dir.is_dir():
        raise FileNotFoundError(f"项目不存在: {project_rel}")

    project_name = project_rel.rstrip("/").split("/")[-1]
    # Determine target: if moving to root level (""), "projects", or "archive",
    # place directly under that; otherwise place under the target's projects/.
    target_stripped = target_parent_rel.rstrip("/")
    if target_stripped == "":
        new_rel = f"projects/{project_name}"  # root level
    elif target_stripped in ("projects", "archive"):
        new_rel = f"{target_stripped}/{project_name}"
    else:
        new_rel = f"{target_stripped}/projects/{project_name}"
    new_dir = kb_root / new_rel
    if new_dir.exists():
        raise FileExistsError(f"目标路径已存在: {new_rel}")

    # ── 1. Check for dirty files ──────────────────────────
    gm = GitManager(kb_root)
    dirty = gm.has_uncommitted_changes()
    if dirty:
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

    # ── 2. Move directory ────────────────────────────────
    shutil.move(str(old_dir), str(new_dir))

    committed_files = set()
    for f in new_dir.rglob("*"):
        if f.is_file():
            committed_files.add(str(f))

    # ── 3. Replace ref: links ────────────────────────────
    old_prefix = f"{project_rel}/"
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

    for refs_dir in kb_root.rglob("_refs"):
        for md_file in refs_dir.rglob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            if old_prefix in text:
                updated = ref_pattern.sub(r'\g<1>' + new_prefix, text)
                md_file.write_text(updated, encoding="utf-8")
                committed_files.add(str(md_file))

    # ── 4. Update readme frontmatter path ────────────────
    readme_path = new_dir / "readme.md"
    if readme_path.exists():
        meta, body = storage.read_document(f"{new_rel}/readme.md")
        storage.write_readme(new_rel, meta, body)

    # ── 5. Rebuild ───────────────────────────────────────
    template = kb_root / "_templates" / "readme.md"
    if template.exists():
        gen = ReadmeGenerator(storage=storage, template_path=template)
        # Rebuild old parent project
        old_parts = project_rel.rstrip("/").split("/")
        # ("projects/ParentA/projects/Child") → old_project_parent = "projects/ParentA"
        if len(old_parts) > 2 and old_parts[-2] == "projects":
            old_project_parent = "/".join(old_parts[:-2])
        else:
            old_project_parent = "/".join(old_parts[:-1])
        if old_project_parent and old_project_parent not in ("projects", "archive", ""):
            gen.rebuild(old_project_parent)
        # Rebuild new parent project
        # target_stripped = "projects/ParentB" → new_parent = "projects/ParentB"
        # target_stripped = "" → new_parent = "" (root)
        new_parent = target_stripped
        if new_parent:
            gen.rebuild(new_parent)
        else:
            gen.rebuild("")  # root
        # Rebuild the moved project itself
        gen.rebuild(new_rel)
        gen.rebuild("")
        gen.rebuild_project_status()
        for f in [kb_root / "readme.md", kb_root / "project-status.md",
                  readme_path]:
            if f.exists():
                committed_files.add(str(f))

    # ── 6. Git commit ────────────────────────────────────
    try:
        file_args = sorted(f for f in committed_files if Path(f).is_file())
        if file_args:
            gm._run("add", "--", *file_args)
            gm.commit(f"move: {project_rel} → {new_rel}")
        from backend.events import broadcast as _evt
        _evt(storage.kb_root)
    except Exception:
        pass

    release_lock(storage)
    return f"✓ 已移动: {project_rel} → {new_rel}"


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


def _heartbeat(kb_root: Path, kind: str) -> None:
    """Record an MCP tool invocation heartbeat.

    ``kind`` is one of ``"nav"`` (read-only) or ``"write"`` (modification).
    Written to ``.mcp-heartbeat`` — read by ``GET /api/mcp`` for live status.
    """
    try:
        (kb_root / ".mcp-heartbeat").write_text(
            f"{kind}:{int(__import__('time').time())}", encoding="utf-8"
        )
    except OSError:
        pass


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
        f"💡 提示：\n"
        f"  • 如果不确定路径，调 nav__list_dir 或 nav__exists 查看\n"
        f"  • 如果需要创建文档，调 write__create_document\n"
        f"  • 禁止直接操作 KB 文件系统（write_to_file / mv / cp / rm）"
    )


def _semantic_type(project_rel: str, name: str, is_dir: bool) -> str:
    """Return a semantic type label for a :class:`DirEntry`.

    Labels help agents understand the role of each item in the KB hierarchy:
    ``project`` / ``subproject`` / ``document`` / ``knowledge`` / ``dir``.
    """
    if not is_dir:
        if name == "readme.md":
            return "📄 index"
        if project_rel == "" or project_rel == "projects" or project_rel == "archive":
            return "📄 doc"
        return "📄 doc"
    if project_rel in ("", "projects", "archive"):
        return "📂 project"
    if name == "common-knowledge":
        return "📂 knowledge"
    if name == "projects":
        return "📂 subproject"
    if name == "archive":
        return "📂 archive"
    if name == "_refs":
        return "📂 refs"
    return "📂 subproject"


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

    def _rebuild_all_for_restore(_storage: Storage, _original: str) -> None:
        """Rebuild indices after a restore / trash-empty operation."""
        if gen is None:
            return
        from backend.mcp_server import _parent_rel
        # Rebuild the parent of the restored item (if any)
        parts = _original.rstrip("/").split("/")
        if len(parts) > 1:
            parent = "/".join(parts[:-1])
            if parent and parent not in ("projects", "archive", "", "trash"):
                gen.rebuild(parent)  # type: ignore[union-attr]
        gen.rebuild("")  # type: ignore[union-attr]
        gen.rebuild_project_status()  # type: ignore[union-attr]

    # ── Auto-inject heartbeat on every tool invocation ──
    _orig_tool = mcp.tool

    def _hb_decorator(fn=None, **kwargs):
        """Wrap mcp.tool() to inject heartbeat."""
        if fn is not None:
            @functools.wraps(fn)
            def _wrapper(*args, **fn_kwargs):
                kind = "nav" if fn.__name__.startswith("nav__") else "write"
                _heartbeat(storage.kb_root, kind)
                return fn(*args, **fn_kwargs)
            # Call the ORIGINAL tool() with parentheses to get a decorator
            return _orig_tool(**kwargs)(_wrapper)
        # Decorator form: @mcp.tool(**kwargs) → returns a decorator
        def _deco(f):
            return _hb_decorator(f, **kwargs)
        return _deco
    mcp.tool = _hb_decorator
    # ───────────────────────────────────────────────────

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
    def nav__list_dir(project_rel: str = "",
                     recursive: bool = False) -> str:
        """[nav] List files and directories in a knowledge base layer.

        Args:
            project_rel: KB-relative path, e.g. ``"projects/以旧换新"``.
            recursive:   When ``True``, recursively list all nested items.
        Returns:
            Formatted table (type, name, last modified, and relative path
            when recursive is enabled).
        """
        if recursive:
            entries = storage.list_children_recursive(project_rel)
        else:
            entries = storage.list_children(project_rel)
        if not entries:
            return "(空目录)"
        lines = ["类型             名称              修改日期"]
        lines.append("─" * 70)
        for e in entries:
            type_label = _semantic_type(project_rel, e.name, e.is_dir)
            indent = "  " if recursive and "/" in e.name else "  "
            display = f"{indent}{e.name:<28} {e.modified}"
            lines.append(f"{type_label:<8} {display}")
        return "\n".join(lines) + "\n\n🔍 提示：不确定路径时记得调 nav__find(keyword=...) 或 nav__exists(path=...)"

    @mcp.tool()
    def nav__exists(path: str) -> str:
        """[nav] Check whether a path exists in the knowledge base.

        Accepts both file paths (``.md``) and directory paths (project, subproject).
        Returns a clear "存在" / "不存在" answer so the agent can decide
        whether to create or read without first guessing by ``list_dir``.

        Args:
            path: KB-relative path, e.g. ``"projects/以旧换新"``
                  or ``"common-knowledge/术语表.md"``.
        Returns:
            A human-readable existence verdict including type (文件/目录).
        """
        target = storage.kb_root / path
        if target.exists():
            kind = "文件" if target.is_file() else "目录"
            return f"✓ 存在：{path}（{kind}）"
        # Offer helpful suggestions for non-existent paths
        segs = path.split("/")
        hints = []
        if len(segs) > 1:
            parent = "/".join(segs[:-1])
            hints.append(f"  调 nav__list_dir(project_rel=\"{parent}\") 看看有什么")
        if not path.startswith(("common-knowledge/", "projects/", "archive/")):
            hints.append("  路径应以 common-knowledge/ 或 projects/ 开头")
        hint_text = "\n" + "\n".join(hints) if hints else ""
        return f"✗ 不存在：{path}{hint_text}"

    @mcp.tool()
    def nav__find(keyword: str, scope: str = "") -> str:
        """[nav] Search for files and directories by name (fuzzy, case-insensitive).

        Accepts a keyword and optionally a scope to limit search to a specific
        project or directory.  Returns all matching items with their full
        KB-relative path, type, and last-modified date.

        Args:
            keyword: Search term (case-insensitive substring match).
            scope:   Optional KB-relative directory to restrict search to,
                     e.g. ``"projects"`` or ``"projects/以旧换新"``.
                     Leave empty to search the entire KB.
        Returns:
            Formatted table of matching items, or a "无匹配" message.
        """
        results = storage.find_by_name(keyword, scope)
        if not results:
            return (
                f"未找到匹配「{keyword}」的项目或文档。\n\n"
                "尝试换一个关键词，或调 nav__list_dir(project_rel=\"projects\") 浏览所有项目。"
            )

        lines = ["类型             路径                    修改日期"]
        lines.append("─" * 80)
        for rel_path, is_dir, modified in results:
            kind = "📂 project" if rel_path.startswith(("projects/", "archive/")) and is_dir else \
                   "📂 subprj" if is_dir else \
                   "📄 doc"
            lines.append(f"{kind:<8} {rel_path:<50} {modified}")
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
        """Rebuild indices and commit. Auto-acquires lock on entry, releases on exit."""
        if gen is None:
            return
        acquire_lock(storage)  # ensure lock held for this write
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

        # ── Auto-release lock after every write operation ──
        release_lock(storage)

    @mcp.tool()
    def write__create_document(path: str, content: str,
                        summary: str = "",
                        doc_type: str = "knowledge",
                        dry_run: bool = False,
                        if_exists: str = "overwrite") -> str:
        """[write] Create a new knowledge document in the KB.

        Args:
            path:      KB-relative path, e.g. ``"common-knowledge/补贴标准.md"``
                       or ``"projects/以旧换新/common-knowledge/流程.md"``.
                       **当 path 的中间目录不存在时，自动创建中间目录。**
            content:   Markdown body (without frontmatter).
            summary:   One-line description (stored in frontmatter).
            doc_type:  ``knowledge`` | ``artifact`` | ``note``.
            dry_run:   When ``True``, only preview the operation without writing.
                       Returns the full path and what would happen.
            if_exists: ``overwrite`` (default) — replace existing file.
                       ``error`` — raise an error if file exists.
                       ``skip`` — do nothing and return existing doc id.
        Returns:
            The document id (or preview info when dry_run=True).
        """
        _validate_path(path, kind="file")
        full_path = storage.kb_root / path

        # ── Dry-run: preview only ──────────────────────────────
        if dry_run:
            exists = full_path.is_file()
            existing_meta = None
            if exists:
                try:
                    existing_meta, _ = storage.read_document(path)
                except Exception:
                    pass
            # Determine intermediate directories that would be created
            parent_dir = full_path.parent
            auto_dirs = []
            if parent_dir != storage.kb_root:
                parts = list(parent_dir.relative_to(storage.kb_root).parts)
                cum = storage.kb_root
                for p in parts:
                    cum = cum / p
                    if not cum.exists():
                        auto_dirs.append(str(cum.relative_to(storage.kb_root)))

            lines = [f"🔍 **Dry-run: write__create_document**"]
            lines.append("─" * 60)
            lines.append(f"  路径:          {path}")
            lines.append(f"  摘要:          {summary or '(无)'}")
            lines.append(f"  类型:          {doc_type}")
            if auto_dirs:
                lines.append(f"  自动创建的目录: {', '.join(auto_dirs)}")
            if exists:
                if if_exists == "overwrite":
                    lines.append(f"  ⚠ 文件已存在 → 将覆盖（if_exists=overwrite）")
                elif if_exists == "error":
                    lines.append(f"  ⚠ 文件已存在 → 将报错（if_exists=error）")
                else:
                    lines.append(f"  ⚠ 文件已存在 → 将跳过（if_exists=skip）")
            else:
                lines.append(f"  ✅ 文件不存在 → 将创建新文档")
            if existing_meta:
                lines.append(f"  已有文档 id:   {existing_meta.get('id', '(未知)')}")
                lines.append(f"  已有创建时间: {existing_meta.get('created', '(未知)')}")
            lines.append("─" * 60)
            lines.append("💡 确认无误后调用本工具时设置 dry_run=False 即可。")
            return "\n".join(lines)

        # ── if_exists check ────────────────────────────────────
        if full_path.is_file():
            if if_exists == "error":
                raise FileExistsError(
                    f"文件已存在：{path}\n\n"
                    f"如需覆盖请设 if_exists=\"overwrite\"。\n"
                    f"如需跳过请设 if_exists=\"skip\"。"
                )
            if if_exists == "skip":
                try:
                    meta, _ = storage.read_document(path)
                    return f"⏭ 已跳过（文件已存在），现有文档 id: {meta.get('id', '(未知)')}"
                except Exception:
                    return f"⏭ 已跳过（文件已存在）"

        # ── Write ──────────────────────────────────────────────
        meta = {"type": doc_type}
        if summary:
            meta["summary"] = summary
        _attach_identity(meta, is_new=True)
        written = storage.write_document(path, meta, content)
        parent_rel = _parent_rel(path)
        _write_through(parent_rel, f"create: {path}")
        return f"✅ 已创建 {path} → id: {written['id']}"

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
        # 字段语义：created 创建（不变）、updated 最后修改、maintainer 最后维护者。
        # AI 正式写入路径更新 updated（与 write__update_project_meta 一致）。
        # 注意：storage.write_document 仅当 updated 缺失时才注入，故需显式覆盖旧值。
        new_meta["updated"] = __import__("datetime").date.today().isoformat()

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
        acquire_lock(storage)  # ensure lock held for this write
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
            # projects/ 是根级系统目录，不是项目层，应重建根 readme，
            # 避免意外生成 projects/readme.md。archive/ 层索引（archive/readme.md）
            # 是预期产物，仍按其 parent 重建。
            if parent in ("", "."):
                rebuild_rel = ""
            elif parent == "projects":
                rebuild_rel = ""
            else:
                rebuild_rel = parent
            gen.rebuild(rebuild_rel)                         # type: ignore[union-attr]
            gen.rebuild_project_status()                     # type: ignore[union-attr]
            _git_commit(storage.kb_root, f"meta: {project_rel}")

        release_lock(storage)
        return new_meta.get("id", "")

    @mcp.tool()
    def write__delete_document(path: str) -> str:
        """[write] Move a knowledge document into the trash (recoverable).

        The document is moved to ``trash/documents/`` with its original
        path recorded, so it can be restored via ``write__restore_document``
        within 30 days.

        Args:
            path: KB-relative path, e.g. ``"common-knowledge/补贴标准.md"``.
        Returns:
            Confirmation message.
        """
        _validate_path(path, kind="file", storage=storage)
        from backend.trash import move_doc_to_trash, docs_dir
        full = storage.kb_root / path
        if not full.exists():
            return f"⚠ 文件不存在: {path}"

        acquire_lock(storage)
        try:
            trash_rel = move_doc_to_trash(storage, path)
            parent_rel = _parent_rel(path)
            _write_through(parent_rel, f"delete(trash): {path}")
            return f"✓ 已移入垃圾箱: {path} → {trash_rel}（30 天内可恢复）"
        finally:
            release_lock(storage)

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
    def write__move_project(project_rel: str, target_parent_rel: str) -> str:
        """Move a project to a different parent directory.

        The project's own name is preserved; only the parent changes.
        Ref links within the KB are automatically updated, and both the
        source parent and target parent readmes are rebuilt.

        Args:
            project_rel:      Current KB-relative path, e.g. ``"projects/首页重构"``.
            target_parent_rel: Destination parent, e.g. ``"projects/归档旧项目"``.
                              Use ``""`` to move to root level.
        Returns:
            Confirmation or error message.
        """
        _validate_path(project_rel, kind="dir", storage=storage)
        from backend.mcp_server import move_project as _move
        try:
            return _move(storage, project_rel, target_parent_rel)
        except (ValueError, FileNotFoundError, FileExistsError) as e:
            return str(e)

    @mcp.tool()
    def write__delete_project(project_rel: str) -> str:
        """Move a project into trash (recoverable, 30 days).

        The whole project tree is moved to ``trash/projects/``.  Ref links
        pointing into it are left as-is so agents can detect them via
        ``maint__check_refs``.

        Args:
            project_rel: KB-relative path, e.g. ``"projects/已归档旧项目"``.
        Returns:
            Confirmation or error message.
        """
        _validate_path(project_rel, kind="dir", storage=storage)
        from backend.mcp_server import delete_project as _dp
        try:
            return _dp(storage, project_rel)
        except (ValueError, FileNotFoundError, FileExistsError) as e:
            return str(e)

    @mcp.tool()
    def write__restore_document(trash_path: str) -> str:
        """Restore a trashed document back to its original path.

        Args:
            trash_path: Path under ``trash/documents/``, e.g.
                        ``"trash/documents/补贴标准.md"``.  Use
                        ``maint__list_trash`` to discover available items.
        Returns:
            Confirmation message or error.
        """
        from backend.trash import restore
        try:
            original = restore(storage, trash_path)
            _rebuild_all_for_restore(storage, original)
            return f"✓ 已恢复: {trash_path} → {original}"
        except (ValueError, FileNotFoundError) as e:
            return str(e)

    @mcp.tool()
    def write__restore_project(trash_path: str) -> str:
        """Restore a trashed project back to its original path.

        Args:
            trash_path: Path under ``trash/projects/``, e.g.
                        ``"trash/projects/项目A"``.
        Returns:
            Confirmation message or error.
        """
        from backend.trash import restore
        try:
            original = restore(storage, trash_path)
            _rebuild_all_for_restore(storage, original)
            return f"✓ 已恢复: {trash_path} → {original}"
        except (ValueError, FileNotFoundError) as e:
            return str(e)

    @mcp.tool()
    def maint__list_trash() -> str:
        """[maint] List all items currently in the trash.

        Returns document and project entries with their type, name,
        original path, deletion time, and trash path.
        """
        from backend.trash import list_trash
        items = list_trash(storage)
        if not items:
            return "（垃圾箱为空）"
        lines = ["类型       名称                   原路径        删除时间"]
        lines.append("─" * 78)
        for it in items:
            lines.append(
                f"{it['type']:<10} {it['name'][:22]:<22} "
                f"{it['original_path'][:22]:<22} {it['deleted_at']}"
            )
        lines.append("─" * 78)
        lines.append("💡 恢复: write__restore_document / write__restore_project "
                     "（参数为 trash_path）")
        return "\n".join(lines)

    @mcp.tool()
    def maint__check_refs(project_rel: str = "") -> str:
        """[maint] Scan a project (or entire KB) for ref link health.

        Classifies every ``ref:`` link as ``normal`` (target exists),
        ``in_trash`` (target was deleted but recoverable), or ``dead``
        (target never existed).

        Args:
            project_rel: Optional project to scope the scan to. Empty = entire KB.
        Returns:
            A report of all refs grouped by status.
        """
        from backend.trash import ref_status
        import re as _re

        scope = storage.kb_root
        if project_rel:
            scope = storage.kb_root / project_rel
            if not scope.is_dir():
                return f"⚠ 项目不存在: {project_rel}"
            scan_files = scope.rglob("*.md")
        else:
            scan_files = storage.kb_root.rglob("*.md")

        normal, in_trash, dead = [], [], []
        for md_file in scan_files:
            if ".git" in md_file.parts or "/trash/" in str(md_file):
                continue
            text = md_file.read_text(encoding="utf-8")
            for m in _re.finditer(r'ref:([^)\s]+)', text):
                target = m.group(1)
                rel = md_file.relative_to(storage.kb_root)
                status = ref_status(storage, target)
                entry = {"from": str(rel), "ref": target}
                if status == "normal":
                    normal.append(entry)
                elif status == "in_trash":
                    in_trash.append(entry)
                else:
                    dead.append(entry)

        parts = []
        parts.append(f"🔍 ref 检查报告（{project_rel or '全库'}）")
        parts.append(f"  ✅ 正常: {len(normal)}")
        parts.append(f"  🗑️ 垃圾箱中: {len(in_trash)}")
        parts.append(f"  ⚠️ 已死: {len(dead)}")
        if in_trash:
            parts.append("\n--- 垃圾箱中（可恢复或更新）---")
            for e in in_trash:
                parts.append(f"  [{e['from']}] → {e['ref']}")
        if dead:
            parts.append("\n--- 已死（需补充知识或更新）---")
            for e in dead:
                parts.append(f"  [{e['from']}] → {e['ref']}")
        return "\n".join(parts)

    @mcp.tool()
    def maint__empty_trash(confirm: bool = False) -> str:
        """[maint] Permanently empty all trash items older than 30 days.

        Args:
            confirm: Must be ``True`` to actually delete.
        Returns:
            Number of items purged, or a no-op message.
        """
        if not confirm:
            return "（需 confirm=True 才会清空）"
        from backend.trash import gc_trash
        n = gc_trash(storage)
        _rebuild_all_for_restore(storage, "")
        return f"🗑️ 已清空 {n} 个超过 30 天的垃圾箱条目"

    @mcp.tool()
    def maint__validate_doc(path: str) -> str:
        """[maint] Check a document's frontmatter integrity.

        Args:
            path: KB-relative path to the .md file.
        Returns:
            Validation report (issues listed, or "✓ 格式正常").
        """
        try:
            _validate_path(path, kind="file", storage=storage)
        except ValueError as e:
            return f"✗ {e}"
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
    def nav__get_document_with_refs(path: str) -> str:
        """[nav] Read a document and append referenced content.

        Inline references use Markdown link syntax with ``ref:`` prefix:

            [text](ref:path)
            [text](ref:path::section_title)

        The tool extracts all refs from the body, reads the latest content
        for each, and appends a references section at the end.  One level
        deep only (no recursive follow-through).
        """

        try:
            meta, body = storage.read_document(path)
        except FileNotFoundError:
            return f"⚠ 文件不存在: {path}"

        # ── Scan for refs + external links (http/https) ────
        from backend.main import _extract_all_refs
        all_refs = _extract_all_refs(body)
        seen: set[str] = {path}
        ref_list: list[tuple[str, str, str]] = []  # (type, path, title)
        for rtype, rpath, title in all_refs:
            dedup_key = rtype + ":" + rpath
            if dedup_key not in seen:
                seen.add(dedup_key)
                ref_list.append((rtype, rpath, title))

        # ── Build main content ──────────────────────────────
        parts = [f"---\n{_yaml_dump(meta)}---\n\n{body}"]

        # ── Resolve references + external links ────────────
        if ref_list:
            parts.append("\n\n--- 参考文献 ---\n")
            for i, (rtype, ref_path, title) in enumerate(ref_list, 1):
                if rtype == "external":
                    parts.append(f"[{i}] 🌐 {title}\n    {ref_path}\n")
                    continue
                try:
                    ref_meta, ref_body = _resolve_ref(path, ref_path, storage)
                except FileNotFoundError:
                    parts.append(f"[{i}] {ref_path} (⚠ 不存在)\n")
                    continue

                if title:
                    excerpt = _extract_section(ref_body, title)
                    if excerpt is not None:
                        sub = f"---\n{_yaml_dump(ref_meta)}---\n\n{excerpt}"
                    else:
                        sub = (
                            f"⚠ 未找到段落「{title}」"
                            f"— 返回全文\n"
                            f"---\n{_yaml_dump(ref_meta)}---\n\n{ref_body}"
                        )
                else:
                    sub = f"---\n{_yaml_dump(ref_meta)}---\n\n{ref_body}"

                parts.append(
                    f"[{i}] {ref_path}"
                    + (f" :: {title}" if title else "")
                    + f"\n{sub}\n"
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
        Automatically updates the checkpoint to the latest HEAD.
        """
        # Update checkpoint before releasing lock
        try:
            cp_file = storage.kb_root / "agent-commit.txt"
            head = gm._run("rev-parse", "--short", "HEAD").strip()
            gm.write_checkpoint(head, cp_file)
        except Exception:
            pass  # non-fatal
        release_lock(storage)
        return "LOCK RELEASED"

    @mcp.prompt()
    def nav__maintenance_procedure() -> str:
        """每次对话开始时执行的知识库维护流程。"""
        return """## 知识库工作流

每次与用户对话开始时，按以下流程自动执行。

### 一、获取锁
调 `maint__acquire_lock`：
- "LOCK ACQUIRED" → 继续
- "LOCK BUSY" → 等待后重试，最多 3 次

### 二、检查待处理变更
调 `maint__read_diff` 对比 checkpoint 到 HEAD：
- 无差异 → 开始对话
- 有差异 → 读 diff → `maint__validate_doc`
  → `maint__rebuild_index`（如 readme 过时）
  → 总结变更 → 用户确认 → 继续

### 三、路径规则（重要）

所有写工具接受以下路径格式，不符会报错：

| 用途 | 路径格式 | 示例 |
|------|---------|------|
| 根层知识 | `common-knowledge/文件名.md` | `common-knowledge/技术选型.md` |
| 项目内知识 | `projects/项目名/common-knowledge/文件名.md` | `projects/首页重构/common-knowledge/改版方案.md` |
| 子项目内知识 | `projects/父项目/projects/子项目/common-knowledge/文件名.md` | — |
| 归档项目 | `archive/项目名/...` | `archive/首页重构/readme.md` |

禁止：`..`、绝对路径、非 `.md` 后缀、`projects`（系统目录）等。
不确定路径时，先调 `nav__list_dir(project_rel="projects")` 列出项目，
或用 `nav__find(keyword=...)` 按名称搜索，或用 `nav__exists(path=...)` 一次性确认。

### 四、铁律：禁止直接操作 KB 文件系统

**严禁通过任何方式直接创建、修改、删除 MYKNOWLEDGE_ROOT 下的文件或目录。**
包括但不限于：`write_to_file`、`execute_command`（`mv/cp/rm/touch`）、`replace_in_file`、Path 对象操作等。

所有知识库操作必须按以下规则处理：

| 你想做的事 | 正确做法 |
|-----------|---------|
| 创建/更新文档 | `write__create_document` / `write__update_document` |
| 删除文档（进垃圾箱） | `write__delete_document` |
| 删除项目（进垃圾箱） | `write__delete_project` |
| 从垃圾箱恢复 | `write__restore_document` / `write__restore_project` |
| 改名项目 | `write__rename_project` |
| 移动项目（换父级） | `write__move_project` |
| 改名文档 | `write__rename_document` |
| 更新项目元数据 | `write__update_project_meta` |
| 读文件 | `nav__get_document` / `nav__get_document_with_refs` |
| 列目录 | `nav__list_dir`（支持 `recursive=True`） |
| 搜索 | `nav__exists` / `nav__find` |

**如果需要的操作不存在于任何 MCP 工具中：**
1. 总结需求文档（包括场景描述、期望的输入和输出）
2. 告知用户：「当前 MCP 工具不支XXXX持此操作，我已整理需求文档，请反馈给项目开发方。」
3. **不得自行绕过 MCP 直接操作文件系统**

### 五、新增探索工具（避免盲目逐层 list）

| 工具 | 用途 | 示例 |
|------|------|------|
| `nav__exists(path)` | 一次性确认路径是否存在 | `nav__exists("projects/以旧换新")` |
| `nav__find(keyword, scope?)` | 按名称模糊搜索（不区分大小写） | `nav__find(keyword="补贴", scope="projects")` |
| `nav__list_dir(recursive=True)` | 递归展开目录树，减少往返 | `nav__list_dir(project_rel="projects/以旧换新", recursive=True)` |

> 目标：**1 次 exists/find + 1 次 create** 完成文档创建，无需逐层猜测路径。

### 六、写操作与自动流程

写完自动触发：
1. `readme` 索引重建
2. `project-status.md` 更新
3. Git 自动 commit
4. SSE 通知前端

**project meta 更新时额外自动归档：**
- status 改为 `completed` / `cancelled` / `abandoned` 后
- 项目目录从 `projects/` 自动移入 `archive/`
- 无需手动操作

### 七、对话中

正常交互，需要时调对应的 MCP 工具：
- **导航**：`nav__read_readme` → `nav__list_dir` → `nav__exists` → `nav__find` → `nav__get_document_with_refs`
- **写**：`write__create_document`(支持 `dry_run=True` 预览 + `if_exists="error|skip|overwrite"`) / `write__update_document` / `write__update_project_meta` / `write__delete_project`
- **改名/移动**：`write__rename_project` / `write__rename_document` / `write__move_project`
- **删除/恢复**：`write__delete_document` / `write__delete_project`（进垃圾箱，30 天可恢复）/ `write__restore_document` / `write__restore_project`
- **维护**：`maint__validate_doc` / `maint__rebuild_index` / `maint__list_trash` / `maint__check_refs` / `maint__empty_trash`
- **分享**：`share__publish` / `share__import_share`

> **垃圾箱与死链**：删除文档/项目会移入 `trash/`（30 天保留）。删除后引用它的文档里 `ref:` 链接保留，可调 `maint__check_refs` 查看死链状态（`normal` / `in_trash` / `dead`）。`in_trash` 可恢复；`dead` 需向用户补充知识或更新。

> **锁说明**：每个写工具执行完毕后**自动释放写锁**。无需手动调 `maint__release_lock`。
> 如需单独释放锁或只读操作结束（如 `maint__read_diff` 后不想继续写），手动调 `maint__release_lock` 即可。

### 八、结束前
1. 告知用户「知识库已同步」
2. 如果锁仍持有（只读流程后），调 `maint__release_lock` 释放
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
