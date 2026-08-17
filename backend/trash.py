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

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

TRASH = "trash"
DOCS = f"{TRASH}/documents"
PROJS = f"{TRASH}/projects"
GC_DAYS = 30

# Persistent index of trash contents: ``original_path → {type, trash_path}``.
# Lives *inside* ``trash/`` so it is already hidden from external listings
# (``top_level_hidden`` contains ``trash``).  Documents and projects are both
# indexed; project entries keep ``original_path`` for the prefix-match logic
# in ``ref_status`` (``rel_path.startswith(op + "/")``).
TRASH_INDEX = "trash/trash_index.json"

# Process-level cache: kb_root → parsed index dict.  Avoids re-reading +
# re-parsing the JSON on every ``ref_status`` call (hover previews hit it a lot).
_index_cache: dict[str, dict] = {}


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
    # Trash contents changed → invalidate the index (next read lazily rebuilds).
    _invalidate_trash_index(storage)
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
    # Trash contents changed → invalidate the index (next read lazily rebuilds).
    _invalidate_trash_index(storage)
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
        # Use the trash index (fast) instead of scanning every trash project.
        entry = _get_trash_index(storage).get(project_rel)
        if entry and entry.get("type") == "project":
            tp = entry.get("trash_path")
            # Confirm the trashed project dir still exists before reporting it.
            if tp and (storage.kb_root / tp).is_dir():
                return tp
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
        _invalidate_trash_index(storage)
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
        _invalidate_trash_index(storage)
        return original_path

    raise ValueError(f"无效的垃圾箱路径: {trash_rel}")


# ── List / GC ──────────────────────────────────────────────────


def list_trash(storage) -> list[dict]:
    """List trash contents: type, name, original_path, deleted_at.

    Reads only the frontmatter header of each trash file (not the body), which
    keeps ``list_trash`` fast even with thousands of trashed items.
    """
    items: list[dict] = []
    ddir = docs_dir(storage.kb_root)
    if ddir.is_dir():
        # ddir is kb_root/trash/documents (already realpath'd); glob yields
        # canonical absolute paths — use the abs fast-reader to skip per-file
        # resolve() in Storage._abs.
        for f in sorted(ddir.glob("*.md")):
            meta = storage.read_frontmatter_bytes_abs(f)
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
            meta = storage.read_frontmatter_bytes_abs(d / "readme.md")
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
    if removed:
        _invalidate_trash_index(storage)
    return removed


def empty_trash(storage) -> int:
    """Permanently remove **all** trash items (documents + projects).

    User-triggered "clear trash" (the frontend empty button) — unlike
    :func:`gc_trash` (which only purges items older than 30 days), this clears
    everything immediately, including fresh items.  Returns the number of
    items removed.
    """
    import shutil
    items = list_trash(storage)
    removed = 0
    for item in items:
        p = storage.kb_root / item["trash_path"]
        if p.exists():
            if p.is_dir():
                shutil.rmtree(str(p))
            else:
                p.unlink()
            removed += 1
    if removed:
        _invalidate_trash_index(storage)
    return removed


# ── Trash index (dead-link fast path) ──────────────────────────


def _index_path(kb_root: Path) -> Path:
    return kb_root / TRASH_INDEX


def _load_trash_index(storage) -> dict | None:
    """Read ``trash_index.json`` → ``{original_path: {type, trash_path}}``.

    Returns ``None`` on any failure (missing / corrupt / non-dict JSON) so the
    caller triggers a rebuild.  Never raises.
    """
    p = _index_path(storage.kb_root)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _rebuild_trash_index(storage) -> dict:
    """Scan ``list_trash`` and persist a fresh index; return it.

    Used both as the fallback (corrupt/missing index) and the one-time cold
    rebuild.  The scan itself is cheap because ``list_trash`` now reads only
    frontmatter headers.
    """
    index: dict[str, dict] = {}
    for item in list_trash(storage):
        op = item.get("original_path")
        if not op:
            continue
        index[op] = {"type": item.get("type", "document"),
                     "trash_path": item.get("trash_path", "")}
    try:
        _index_path(storage.kb_root).write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        # Best-effort persist; never fail the caller over a write hiccup.
        pass
    _index_cache[str(storage.kb_root)] = index
    return index


def _get_trash_index(storage) -> dict:
    """Unified entry point: process cache → file → rebuild.

    1. Cache hit → return.
    2. Cache miss → read file; if valid, cache + return.
    3. File missing/corrupt → rebuild from ``list_trash`` + persist + cache.
    """
    key = str(storage.kb_root)
    cached = _index_cache.get(key)
    if cached is not None:
        return cached
    loaded = _load_trash_index(storage)
    if loaded is not None:
        _index_cache[key] = loaded
        return loaded
    return _rebuild_trash_index(storage)


def _invalidate_trash_index(storage) -> None:
    """Drop the process cache + delete the on-disk index for this KB root.

    Called by write operations (delete/restore/empty/gc).  The next read then
    lazily rebuilds a fresh index — avoids re-scanning thousands of entries on
    every write.
    """
    key = str(storage.kb_root)
    _index_cache.pop(key, None)
    try:
        _index_path(storage.kb_root).unlink(missing_ok=True)
    except OSError:
        pass


# ── Ref status (dead-link check) ───────────────────────────────


def ref_status(storage, rel_path: str) -> str:
    """Classify a referenced path: ``normal`` | ``in_trash`` | ``dead``.

    ``normal``  — the path exists at its original location.
    ``in_trash`` — the path was deleted and is recoverable from trash.
    ``dead``     — the path was never deleted and does not exist.

    Dead-link branch goes through the trash index (in-memory + persisted) with a
    ``stat``/``exists`` fallback to guard against index/disk drift, instead of a
    full scan of every trash file.
    """
    from urllib.parse import unquote
    # S16: 任何调用方可能传 %20 编码路径（含空格文档路径），先解码再判。
    # unquote 幂等：%20→空格、空格→空格，不会双重解码。
    rel_path = unquote(rel_path)
    # Strip any :section suffix that may have slipped in
    rel_path = re.split(r"::", rel_path)[0].strip("/")
    if (storage.kb_root / rel_path).exists():
        return "normal"

    index = _get_trash_index(storage)
    hit = index.get(rel_path)
    if hit is None:
        # Project-level prefix match: path lies inside a trashed project
        for op, entry in index.items():
            if entry.get("type") == "project" and op:
                if rel_path.startswith(op.rstrip("/") + "/"):
                    # stat fallback: index says in_trash, but confirm the
                    # trashed project dir actually still exists on disk.
                    if _trash_entry_exists(storage, entry):
                        return "in_trash"
                    break
        return "dead"

    # Direct hit by original_path → confirm trash file still on disk.
    if _trash_entry_exists(storage, hit):
        return "in_trash"
    return "dead"


def _trash_entry_exists(storage, entry: dict) -> bool:
    """Fallback confirmation: does the indexed trash entry still exist on disk?

    Guards against index/disk drift (e.g. index says ``in_trash`` but the file
    was manually deleted).  Returns False when the entry or its ``trash_path``
    is malformed/missing so the caller reports ``dead`` instead of a stale
    ``in_trash``.
    """
    tp = entry.get("trash_path")
    if not tp:
        return False
    return (storage.kb_root / tp).exists()
