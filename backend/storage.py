"""Low-level file operations for the knowledge base.

Every operation is relative to a *kb_root* directory — pass it explicitly
when constructing ``Storage``.  A single codebase can manage multiple
knowledge bases by creating multiple ``Storage`` instances.
"""

from __future__ import annotations

import re
import yaml
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional
from uuid import uuid4, uuid5, NAMESPACE_URL

# ── Regex ────────────────────────────────────────────────────
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

# ── ID namespaces ────────────────────────────────────────────
_PROJECT_NS = uuid5(NAMESPACE_URL, "https://myknowledge.dev/project")
_DOC_NS = uuid5(NAMESPACE_URL, "https://myknowledge.dev/doc")


# ═════════════════════════════════════════════════════════════
#  Pure frontmatter helpers (stateless, no kb_root needed)
# ═════════════════════════════════════════════════════════════

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split markdown into (meta_dict, body_str).

    If no frontmatter is present (or malformed) returns ``({}, text)``.
    Never raises.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text.strip()
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        meta = None
    if not isinstance(meta, dict):
        meta = {}
    # yaml auto-parses ``2026-07-23`` as ``datetime.date`` — always keep as str
    for k, v in list(meta.items()):
        if hasattr(v, "isoformat"):
            meta[k] = v.isoformat()
    return meta, m.group(2)


def dump_frontmatter(meta: dict, body: str) -> str:
    """Reconstruct ``--- frontmatter ---`` + body."""
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm}\n---\n\n{body}"


def generate_doc_id() -> str:
    """Short readable ``doc_yyyymmdd_xxxx``."""
    today = date.today().strftime("%Y%m%d")
    short = uuid4().hex[:6]
    return f"doc_{today}_{short}"


def generate_readme_id(names: list[str]) -> str:
    """Deterministic id from the ancestor chain, e.g. ``readme_abc123def456``."""
    seed = "-".join(names)
    return f"readme_{uuid5(_PROJECT_NS, seed).hex[:12]}"


# ══════════════════════════════════════════════════════════════
#  Data types
# ══════════════════════════════════════════════════════════════

@dataclass
class DirEntry:
    name: str          # basename
    is_dir: bool
    modified: str      # ISO date string


@dataclass
class DocEntry:
    path: str          # e.g. ``common-knowledge/补贴标准.md``
    summary: str
    updated: str


@dataclass
class ProjectEntry:
    path: str          # e.g. ``projects/机器更换/``
    name: str
    summary: str


@dataclass
class ReadmeMeta:
    """Extracted frontmatter of a *readme.md*."""
    id: str
    name: str
    summary: str
    status: str = "active"
    author: str = ""
    maintainer: str = ""
    created: str = ""
    updated: str = ""
    generated: str = ""


# ══════════════════════════════════════════════════════════════
#  Storage class (one instance per knowledge base)
# ══════════════════════════════════════════════════════════════

class Storage:
    """File operations bound to a specific knowledge base root."""

    def __init__(self, kb_root: Path, templates_dir: Optional[Path] = None) -> None:
        self.kb_root = kb_root.resolve()
        self._templates_dir = templates_dir.resolve() if templates_dir else (self.kb_root / "_templates")

        # Cache for commonly-used paths
        self._projects_dir = self.kb_root / "projects"
        self._archive_dir = self.kb_root / "archive"
        self._ck_dir = self.kb_root / "common-knowledge"

    # ── Path resolution ────────────────────────────────────────

    def _abs(self, rel: str) -> Path:
        """KB-relative path → absolute filesystem path."""
        return (self.kb_root / rel).resolve()

    def _rel(self, abs_path: Path) -> str:
        """Absolute path → KB-relative string."""
        return str(abs_path.relative_to(self.kb_root))

    @staticmethod
    def _ensure_dir(path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ── Read ───────────────────────────────────────────────────

    def read_content(self, rel_path: str) -> str:
        """Read the raw full content (frontmatter + body) of a KB file."""
        return self._abs(rel_path).read_text(encoding="utf-8")

    def read_document(self, rel_path: str) -> tuple[dict, str]:
        """Return (frontmatter_meta, body) from a KB-relative path."""
        text = self._abs(rel_path).read_text(encoding="utf-8")
        return parse_frontmatter(text)

    def read_frontmatter(self, rel_path: str) -> dict:
        """Only frontmatter (fast, skips full body manipulation)."""
        meta, _ = self.read_document(rel_path)
        return meta

    def read_dir(self, rel_path: str) -> dict[str, dict]:
        """Return ``{path→meta}`` for every ``.md`` in a directory."""
        result: dict[str, dict] = {}
        for entry in self.list_children(rel_path):
            if entry.name.endswith(".md"):
                child = f"{rel_path}/{entry.name}" if rel_path else entry.name
                result[child] = self.read_frontmatter(child)
        return result

    def path_exists(self, rel_path: str) -> bool:
        """Check whether a KB-relative path exists (file or directory)."""
        return self._abs(rel_path).exists()

    def find_by_name(self, keyword: str, scope: str = "") -> list[tuple[str, bool, str]]:
        """Recursively search for files/directories matching *keyword* (case-insensitive).

        Returns a list of ``(rel_path, is_dir, modified)`` tuples sorted by path.
        Optionally limit search to a *scope* directory.
        """
        from fnmatch import fnmatch

        search_root = self._abs(scope) if scope else self.kb_root
        if not search_root.is_dir():
            return []

        results: list[tuple[str, bool, str]] = []
        kw_lower = keyword.lower()

        for child in sorted(search_root.rglob("*")):
            # Skip hidden directories
            if any(part.startswith(".") for part in child.relative_to(search_root).parts):
                continue
            # Skip __pycache__
            if "__pycache__" in child.parts:
                continue
            # Name match (case-insensitive substring or simple glob)
            name = child.name.lower()
            if kw_lower in name or fnmatch(name, kw_lower):
                rel = str(child.relative_to(self.kb_root))
                mtime = child.stat().st_mtime
                results.append((rel, child.is_dir(), date.fromtimestamp(mtime).isoformat()))

        return results

    def list_children_recursive(self, rel_path: str) -> list[DirEntry]:
        """Recursive listing of a KB directory.

        Same filtering rules as ``list_children()`` but recurses into subdirectories.
        Each ``DirEntry.name`` is the *basename*, and ``DirEntry.is_dir`` is preserved.
        The caller can reconstruct the full path by accumulating parents.
        """
        def _recurse(full: Path, depth: int) -> list[DirEntry]:
            if not full.is_dir():
                return []
            hidden = {".git", "__pycache__", ".events", ".lock"}
            top_level_hidden = {"_templates", "publish", "config.yaml",
                                "agent-commit.txt", "trash"}

            items: list[DirEntry] = []
            for child in sorted(full.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
                if child.name in hidden:
                    continue
                if rel_path in ("", ".") and child.name in top_level_hidden:
                    continue

                mtime = child.stat().st_mtime
                items.append(DirEntry(
                    name=child.name,
                    is_dir=child.is_dir(),
                    modified=date.fromtimestamp(mtime).isoformat(),
                ))
                if child.is_dir():
                    items.extend(_recurse(child, depth + 1))
            return items

        return _recurse(self._abs(rel_path), 0)

    def list_children(self, rel_path: str) -> list[DirEntry]:
        """Non-recursive listing of a KB directory.

        Dot-files, ``__pycache__``, ``.git`` are always hidden.
        Top-level directories (``_templates``, ``publish``) are hidden
        only when listing the root.
        """
        full = self._abs(rel_path)
        if not full.is_dir():
            return []

        hidden = {".git", "__pycache__", ".events", ".lock"}
        top_level_hidden = {"_templates", "publish", "config.yaml",
                            "agent-commit.txt", "trash"}

        entries: list[DirEntry] = []
        for child in sorted(full.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
            if child.name in hidden:
                continue
            if rel_path in ("", ".") and child.name in top_level_hidden:
                continue

            mtime = child.stat().st_mtime
            entries.append(DirEntry(
                name=child.name,
                is_dir=child.is_dir(),
                modified=date.fromtimestamp(mtime).isoformat(),
            ))
        return entries

    # ── Write ─────────────────────────────────────────────────

    def write_document(self, rel_path: str, meta: dict, body: str,
                       *, auto_id: bool = True) -> dict:
        """Write a document; returns the final meta dict (augmented)."""
        full = self._abs(rel_path)
        self._ensure_dir(full.parent)

        if auto_id and "id" not in meta:
            meta["id"] = generate_doc_id()
        if "updated" not in meta:
            meta["updated"] = date.today().isoformat()
        if "created" not in meta:
            # 首次创建时注入，更新时保留原值
            meta["created"] = date.today().isoformat()

        full.write_text(dump_frontmatter(meta, body), encoding="utf-8")
        return meta

    def write_readme(self, project_rel: str, meta: dict, body: str) -> None:
        """Write a *readme.md* at ``{project_rel}/readme.md``.

        The *body* must be a complete markdown document (frontmatter + content),
        as produced by ``ReadmeGenerator.rebuild()``.  The *meta* dict is
        accepted for API consistency but **not** serialised — the body is
        written verbatim.
        """
        path = f"{project_rel}/readme.md" if project_rel else "readme.md"
        full = self._abs(path)
        self._ensure_dir(full.parent)
        full.write_text(body, encoding="utf-8")

    # ── Read helpers for readme generation ────────────────────

    def get_readme_meta(self, project_rel: str) -> ReadmeMeta:
        """Read the frontmatter of a project's ``readme.md``."""
        path = f"{project_rel}/readme.md" if project_rel else "readme.md"
        meta = self.read_frontmatter(path)
        return ReadmeMeta(
            id=meta.get("id") or "",
            name=meta.get("name") or "",
            summary=meta.get("summary") or "",
            status=meta.get("status") or "active",
            author=meta.get("author") or "",
            maintainer=meta.get("maintainer") or "",
            created=meta.get("created") or "",
            updated=meta.get("updated") or "",
            generated=meta.get("generated") or "",
        )

    def get_doc_entries(self, project_rel: str) -> list[DocEntry]:
        """Return all knowledge documents in the project's ``common-knowledge/``."""
        ck = f"{project_rel}/common-knowledge" if project_rel else "common-knowledge"
        entries: list[DocEntry] = []
        for path, meta in self.read_dir(ck).items():
            entries.append(DocEntry(
                path=self._rel(self._abs(path)),
                summary=meta.get("summary", ""),
                updated=meta.get("updated", ""),
            ))
        entries.sort(key=lambda e: e.updated, reverse=True)
        return entries

    def get_project_entries(self, project_rel: str) -> list[ProjectEntry]:
        """Return all sub-projects under the project's ``projects/``."""
        sub = f"{project_rel}/projects" if project_rel else "projects"
        entries: list[ProjectEntry] = []
        for entry in self.list_children(sub):
            if not entry.is_dir:
                continue
            sub_path = f"{sub}/{entry.name}"
            try:
                rm = self.get_readme_meta(sub_path)
            except FileNotFoundError:
                continue
            entries.append(ProjectEntry(
                path=self._rel(self._abs(sub_path)),
                name=rm.name,
                summary=rm.summary,
            ))
        entries.sort(key=lambda e: e.name)
        return entries

    def get_archive_entries(self, project_rel: str) -> list[ProjectEntry]:
        """Return archived projects under the project's ``archive/``."""
        arch = f"{project_rel}/archive" if project_rel else "archive"
        entries: list[ProjectEntry] = []
        for entry in self.list_children(arch):
            if not entry.is_dir:
                continue
            arch_path = f"{arch}/{entry.name}"
            try:
                rm = self.get_readme_meta(arch_path)
            except FileNotFoundError:
                continue
            entries.append(ProjectEntry(
                path=self._rel(self._abs(arch_path)),
                name=rm.name,
                summary=rm.summary,
            ))
        entries.sort(key=lambda e: e.name)
        return entries
