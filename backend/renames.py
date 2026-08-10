"""Rename mapping — old path → new path redirect support (S15).

When a document is renamed (``write__rename_document`` / ``PUT
/api/document/rename``), we persist a mapping ``old_path → new_path`` so a
GET on the old path can answer with a redirect instead of a bare 404.
This lets the frontend (or any stale bookmark / history entry) jump to the
renamed document automatically.

Storage:
    ``<kb_root>/.renames.json`` — a hidden dot-file, so it never shows up
    in directory listings.  It is ignored by git via ``.git/info/exclude``
    (repo-local, NOT committed), so the mapping never pollutes the
    document tree or the repository state.

Design notes:
    * Chain folding — when ``A → B`` then ``B → C``, every key that pointed
      to ``B`` is re-pointed to ``C`` on write; ``resolve_rename`` also
      follows the chain defensively (with a cycle guard).
    * All functions are best-effort: any I/O failure is swallowed so a
      broken mapping file never blocks the rename / delete main flow.
"""

from __future__ import annotations

import json
from pathlib import Path

RENAMES_FILE = ".renames.json"


def mapping_path(kb_root: Path) -> Path:
    """Absolute path of the rename mapping file."""
    return kb_root / RENAMES_FILE


def read_mapping(storage) -> dict[str, str]:
    """Read ``{old_path: new_path}``; empty dict when missing/corrupt."""
    p = mapping_path(storage.kb_root)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        pass
    return {}


def _write_mapping(storage, mapping: dict[str, str]) -> None:
    """Atomically write the mapping file (tmp + replace)."""
    p = mapping_path(storage.kb_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    tmp.replace(p)


def _ensure_git_ignored(kb_root: Path) -> None:
    """Ignore the mapping file from git via ``.git/info/exclude``.

    ``.git/info/exclude`` is repo-local (never committed), so ignoring the
    mapping there keeps ``git status`` clean without touching the document
    tree or adding a tracked ``.gitignore``.
    """
    try:
        git_dir = kb_root / ".git"
        if not git_dir.is_dir():
            return  # no git → nothing to ignore
        exclude = git_dir / "info" / "exclude"
        if exclude.exists() and RENAMES_FILE in exclude.read_text(
                encoding="utf-8").splitlines():
            return  # already ignored
        with open(exclude, "a", encoding="utf-8") as f:
            f.write("\n" + RENAMES_FILE + "\n")
    except Exception:
        pass  # best-effort: ignoring failure never blocks the rename


def record_rename(storage, old_rel: str, new_rel: str) -> None:
    """Persist ``old_rel → new_rel``, folding rename chains.

    If ``A → B`` already exists and now ``B → C`` is recorded, ``A`` is
    re-pointed directly to ``C`` (chain folding on write).
    """
    try:
        mapping = read_mapping(storage)
        changed = False
        # Chain folding: any key that pointed to old_rel now points to new_rel
        for k, v in list(mapping.items()):
            if v == old_rel:
                mapping[k] = new_rel
                changed = True
        if mapping.get(old_rel) != new_rel:
            mapping[old_rel] = new_rel
            changed = True
        if not changed:
            return
        _ensure_git_ignored(storage.kb_root)
        _write_mapping(storage, mapping)
    except Exception:
        pass  # best-effort: mapping failure never blocks the rename flow


def remove_renames_for(storage, path: str) -> None:
    """Drop every mapping whose key OR value equals *path*.

    Called when a document is deleted (moved to trash): a deleted document
    must surface as "deleted" rather than redirecting elsewhere.
    """
    try:
        mapping = read_mapping(storage)
        keys = [k for k in mapping if k == path or mapping[k] == path]
        if not keys:
            return
        for k in keys:
            mapping.pop(k, None)
        _write_mapping(storage, mapping)
    except Exception:
        pass  # best-effort


def resolve_rename(storage, path: str) -> str | None:
    """Resolve *path* through the mapping to a live target, or ``None``.

    Returns the final destination (following chains, with a cycle guard)
    only when that destination currently exists on disk.  Otherwise
    ``None`` — callers fall back to the normal not_found/deleted logic.
    """
    mapping = read_mapping(storage)
    if not mapping or path not in mapping:
        return None

    current = path
    seen: set[str] = set()
    while current in mapping:
        if current in seen:
            return None  # cycle — never redirect
        seen.add(current)
        nxt = mapping[current]
        if not nxt or nxt == current:
            break
        current = nxt

    if current == path:
        return None
    if (storage.kb_root / current).is_file():
        return current
    return None
