"""Trash (recycle bin) for MyKnowledge.

Deleted documents and projects are moved into ``trash/`` instead of being
removed, so users can recover them for up to 30 days.

Layout::

    ~/.myknowledge/
    └── trash/
        ├── readme.md            # index (optional)
        ├── documents/           # single-file deletes (write__delete_document)
        │   └── <name>.md        # frontmatter: original_path, deleted_at
        └── projects/            # whole-project deletes (write__delete_project)
            └── <project>/       # entire tree; project readme holds original_path
                └── ...
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

TRASH = "trash"
DOCS = f"{TRASH}/documents"
PROJS = f"{TRASH}/projects"
GC_DAYS = 30


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def trash_root(kb_root: Path) -> Path:
    return kb_root / TRASH


def docs_dir(kb_root: Path) -> Path:
    return kb_root / DOCS


def projects_dir(kb_root: Path) -> Path:
    return kb_root / PROJS


# ── Delete ─────────────────────────────────────────────────────


def _unique_name(kb_root: Path, target_dir: Path, filename: str) -> str:
    """Avoid collisions in a flat trash subdir (e.g. documents/)."""
    cand = target_dir / filename
    if not cand.exists():
        return filename
    stem, ext = Path(filename).stem, Path(filename).suffix
    for i in range(1, 1000):
        alt = f"{stem}_{i}{ext}"
        if not (target_dir / alt).exists():
            return alt
    return f"{stem}_{int(datetime.now().timestamp())}{ext}"


def move_doc_to_trash(storage, rel_path: str) -> str:
    """Move a single document into ``trash/documents/``.

    Returns the new trash-relative path.  Raises FileNotFoundError if the
    document does not exist.
    """
    import shutil

    abs_src = storage.kb_root / rel_path
    if not abs_src.is_file():
        raise FileNotFoundError(f"文件不存在: {rel_path}")

    ddir = docs_dir(storage.kb_root)
    ddir.mkdir(parents=True, exist_ok=True)
    filename = _unique_name(storage.kb_root, ddir, abs_src.name)
    trash_rel = f"{DOCS}/{filename}"

    # Preserve frontmatter, stamp original_path + deleted_at
    meta, body = storage.read_document(rel_path)
    new_meta = dict(meta)
    new_meta["original_path"] = rel_path
    new_meta["deleted_at"] = _now()
    # 不覆盖 type（文档类型 knowledge/readme 保留；trash 条目分类由目录推断）
    storage.write_document(trash_rel, new_meta, body, auto_id=False)

    # Remove original (now duplicated in trash)
    abs_src.unlink()

    # Drop rename mappings pointing at this document (S15): a deleted doc
    # must surface as "deleted", not redirect.  Best-effort — never blocks.
    from backend.renames import remove_renames_for
    remove_renames_for(storage, rel_path)
    return trash_rel


def move_project_to_trash(storage, project_rel: str) -> str:
    """Move a whole project tree into ``trash/projects/``.

    Returns the new trash-relative path.
    """
    import shutil

    abs_src = storage.kb_root / project_rel
    if not abs_src.is_dir():
        raise FileNotFoundError(f"项目不存在: {project_rel}")

    pdir = projects_dir(storage.kb_root)
    pdir.mkdir(parents=True, exist_ok=True)
    name = project_rel.rstrip("/").split("/")[-1]
    dest = pdir / _unique_name(storage.kb_root, pdir, name)
    trash_rel = f"{PROJS}/{dest.name}"

    shutil.move(str(abs_src), str(dest))

    # Stamp the project's own readme with original_path + deleted_at
    from backend.storage import dump_frontmatter
    readme_rel = f"{trash_rel}/readme.md"
    try:
        meta, body = storage.read_document(readme_rel)
        new_meta = dict(meta)
        new_meta["original_path"] = project_rel
        new_meta["deleted_at"] = _now()
        new_meta["type"] = "project"
        storage.write_readme(trash_rel, {}, dump_frontmatter(new_meta, body))
    except FileNotFoundError:
        # Project has no readme (shouldn't happen); create one
        storage.write_readme(
            trash_rel, {},
            dump_frontmatter(
                {"original_path": project_rel, "deleted_at": _now(),
                 "type": "project", "name": name}, f"# {name}（已删除）"),
        )
    return trash_rel


# ── Restore ────────────────────────────────────────────────────


def _read_trash_meta(storage, trash_rel: str) -> dict:
    if trash_rel.startswith(f"{DOCS}/"):
        meta, _ = storage.read_document(trash_rel)
        return meta
    if trash_rel.startswith(f"{PROJS}/"):
        meta, _ = storage.read_document(f"{trash_rel}/readme.md")
        return meta
    raise ValueError(f"无效的垃圾箱路径: {trash_rel}")


def _parent_project_in_trash(storage, original_path: str) -> str | None:
    """If restoring a doc whose containing project is itself in trash, return it."""
    # Determine the root project of the original path, e.g. projects/P
    parts = original_path.split("/")
    if len(parts) >= 2 and parts[0] == "projects":
        project_rel = f"{parts[0]}/{parts[1]}"
        for d in projects_dir(storage.kb_root).iterdir():
            if not d.is_dir():
                continue
            try:
                meta = _read_trash_meta(storage, f"{PROJS}/{d.name}")
            except Exception:
                continue
            if meta.get("original_path") == project_rel:
                return f"{PROJS}/{d.name}"
    return None


def restore(storage, trash_rel: str) -> str:
    """Restore a document/project from trash back to its original path.

    Raises ValueError when:
    - trash item is not found,
    - its parent project is still in trash (must restore project first),
    - the original path is already occupied.
    """
    import shutil

    meta = _read_trash_meta(storage, trash_rel)
    original_path = meta.get("original_path", "").lstrip("/")
    if not original_path:
        raise ValueError(f"垃圾箱条目缺少 original_path: {trash_rel}")

    # 历史数据防护：original_path 是删除时记录的，可能来自旧版本/非法输入。
    # 恢复前重新过完整路径校验，防止恢复到 readme/孤儿/非法层级。
    from backend.mcp_server import _validate_path
    is_doc = trash_rel.startswith(f"{DOCS}/")
    try:
        _validate_path(original_path, kind="file" if is_doc else "dir")
    except ValueError as exc:
        raise ValueError(
            f"垃圾箱条目 original_path 不合法，拒绝恢复: {original_path}\n{exc}") from exc

    if trash_rel.startswith(f"{DOCS}/"):
        # Dependency: containing project must not be in trash
        parent = _parent_project_in_trash(storage, original_path)
        if parent:
            raise ValueError(
                f"文档所属项目已在垃圾箱（{parent}）。\n"
                f"请先恢复项目 {meta.get('original_path')}，再恢复此文档。"
            )
        # Conflict: target already exists
        if (storage.kb_root / original_path).exists():
            raise ValueError(f"目标路径已存在: {original_path}（不覆盖）")
        _, body = storage.read_document(trash_rel)
        clean = {k: v for k, v in meta.items()
                 if k not in ("original_path", "deleted_at")}
        storage.write_document(original_path, clean, body, auto_id=False)
        (storage.kb_root / trash_rel).unlink()
        return original_path

    if trash_rel.startswith(f"{PROJS}/"):
        dest = storage.kb_root / original_path
        if dest.exists():
            raise ValueError(f"目标路径已存在: {original_path}（不覆盖）")
        src = storage.kb_root / trash_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        # Clear trash stamps from restored project readme
        from backend.storage import dump_frontmatter
        readme_rel = f"{original_path}/readme.md"
        try:
            m2, b2 = storage.read_document(readme_rel)
            clean = {k: v for k, v in m2.items()
                     if k not in ("original_path", "deleted_at", "type")}
            storage.write_readme(original_path, {}, dump_frontmatter(clean, b2))
        except FileNotFoundError:
            pass
        return original_path

    raise ValueError(f"无效的垃圾箱路径: {trash_rel}")


# ── List / GC ──────────────────────────────────────────────────


def list_trash(storage) -> list[dict]:
    """List trash contents: type, name, original_path, deleted_at."""
    items: list[dict] = []
    ddir = docs_dir(storage.kb_root)
    if ddir.is_dir():
        for f in sorted(ddir.glob("*.md")):
            try:
                meta, _ = storage.read_document(f"{DOCS}/{f.name}")
            except Exception:
                continue
            items.append({
                "type": "document", "name": f.name,
                "original_path": meta.get("original_path", ""),
                "deleted_at": meta.get("deleted_at", ""),
                "trash_path": f"{DOCS}/{f.name}",
            })
    pdir = projects_dir(storage.kb_root)
    if pdir.is_dir():
        for d in sorted(pdir.iterdir()):
            if not d.is_dir():
                continue
            try:
                meta, _ = storage.read_document(f"{PROJS}/{d.name}/readme.md")
            except Exception:
                continue
            items.append({
                "type": "project", "name": d.name,
                "original_path": meta.get("original_path", ""),
                "deleted_at": meta.get("deleted_at", ""),
                "trash_path": f"{PROJS}/{d.name}",
            })
    return items


def gc_trash(storage, days: int = GC_DAYS) -> int:
    """Permanently remove trash items older than *days* days.

    Returns the number of items removed.
    """
    import shutil
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    for item in list_trash(storage):
        try:
            ts = datetime.fromisoformat(item["deleted_at"])
        except (ValueError, TypeError):
            continue
        if ts < cutoff:
            p = storage.kb_root / item["trash_path"]
            if p.exists():
                if p.is_dir():
                    shutil.rmtree(str(p))
                else:
                    p.unlink()
                removed += 1
    return removed


# ── Ref status (dead-link check) ───────────────────────────────


def ref_status(storage, rel_path: str) -> str:
    """Classify a referenced path: ``normal`` | ``in_trash`` | ``dead``.

    ``normal``  — the path exists at its original location.
    ``in_trash`` — the path was deleted and is recoverable from trash.
    ``dead``     — the path was never deleted and does not exist.
    """
    # Strip any :section suffix that may have slipped in
    rel_path = re.split(r"::", rel_path)[0].strip("/")
    if (storage.kb_root / rel_path).exists():
        return "normal"

    # Single-doc match by original_path
    for item in list_trash(storage):
        if item["original_path"] == rel_path:
            return "in_trash"
        # Project-level: path is inside a trashed project
        if item["type"] == "project" and item["original_path"]:
            op = item["original_path"].rstrip("/")
            if rel_path.startswith(op + "/"):
                return "in_trash"

    return "dead"
