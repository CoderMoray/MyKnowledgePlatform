"""Readme generator — fills ``_templates/readme.md`` with directory contents.

Usage::

    gen = ReadmeGenerator(storage, template_path)
    gen.rebuild("")                          # rebuild root readme
    gen.rebuild("projects/以旧换新", parent="root")  # rebuild project readme
    gen.rebuild_project_status()             # rebuild project-status.md
    removed = gen.garbage_collect()           # clean abandoned projects
"""

from __future__ import annotations

import shutil
from datetime import date, timedelta
from pathlib import Path

from backend.storage import Storage, generate_readme_id


class ReadmeGenerator:
    """Rebuild a readme at a given KB-relative path from live directory data."""

    def __init__(self, storage: Storage, template_path: Path) -> None:
        self.storage = storage
        self._template = template_path.read_text(encoding="utf-8")

    # ── public API ──────────────────────────────────────────

    def rebuild(self, project_rel: str, parent: str = "",
                name: str = "", summary: str = "",
                status: str = "", updated: str = "") -> str:
        """Rebuild (or create) the readme at *project_rel*.

        Parameters:
            project_rel: KB-relative directory, e.g. ``""`` for root or
                         ``"projects/以旧换新"`` for a project.
            parent:      ``layer_id`` of the parent readme.
                         ``""`` for the root level.
            name         Override name (used on first build of root).
            summary      Override summary (used on first build of root).
            status       Override status.
            updated      Date override.

        Returns the generated markdown text (also written to disk).
        """
        # projects/ 是根级系统目录，不是项目层 —— 禁止生成 projects/readme.md。
        # 真正的项目层是 "projects/xxx"。调用方误传 "projects" 时直接跳过写入。
        if project_rel == "projects":
            return ""
        # ── Ensure project directory structure ───────────────
        # 白名单：只有 projects/xxx 或 archive/xxx 才视作项目层
        if project_rel and (project_rel.startswith("projects/")
                            or project_rel.startswith("archive/")):
            for _d in ("common-knowledge", "projects", "archive"):
                (self.storage.kb_root / project_rel / _d).mkdir(parents=True, exist_ok=True)

        # ── Gather data ──────────────────────────────────────
        try:
            meta = self.storage.get_readme_meta(project_rel)
            name = name or meta.name
            summary = summary or meta.summary
            status = status or meta.status
            updated = updated or meta.updated
        except FileNotFoundError:
            # First creation — use provided values (or defaults)
            pass

        # Ensure defaults for empty values
        if not name:
            name = (project_rel.rstrip("/").split("/")[-1]
                    if project_rel and project_rel != ""
                    else "MyKnowledge")
        if not status:
            status = "active"

        doc_entries = self.storage.get_doc_entries(project_rel)
        proj_entries = self.storage.get_project_entries(project_rel)
        arch_entries = self.storage.get_archive_entries(project_rel)

        # ── Build id ─────────────────────────────────────────
        layer_id = self._resolve_id(project_rel, name)
        generated = date.today().isoformat()
        parent_id = parent

        # ── Format template sections ─────────────────────────
        doc_lines = "\n".join(
            f"- `{d.path}` ({d.updated}) — {d.summary}" for d in doc_entries
        ) or "_暂无_"

        proj_lines = "\n".join(
            f"- `{p.path}` — {p.summary}" for p in proj_entries
        ) or "_暂无_"

        arch_lines = "\n".join(
            f"- `{a.name}` — {a.summary}" for a in arch_entries
        ) or "_暂无_"

        archive_footer = (
            "➡ `archive/` 完整目录见 `archive/readme.md`"
            if arch_entries else ""
        )

        # ── Identity + created ──────────────────────────────
        from backend.config import get_identity
        try:
            nick, email = get_identity()
            author = f"{nick} <{email}>"
            maintainer = author
        except Exception:
            author = "unknown"
            maintainer = "unknown"

        # Preserve `created` from the existing readme, if any
        try:
            existing = self.storage.get_readme_meta(project_rel)
            existing_created = getattr(existing, "created", None) or ""
        except FileNotFoundError:
            existing_created = ""
        if not existing_created:
            existing_created = generated

        # ── Fill template ────────────────────────────────────
        content = self._template
        replacements = {
            "{layer_id}": layer_id,
            "{name}": name,
            "{summary}": summary,
            "{status}": status,
            "{author}": author,
            "{maintainer}": maintainer,
            "{created}": existing_created,
            "{updated}": updated or generated,
            "{generated}": generated,
            "{parent}": parent_id,
            "{doc_entries}": doc_lines,
            "{project_entries}": proj_lines,
            "{archive_entries}": arch_lines,
            "{archive_footer}": archive_footer,
        }
        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)

        # ── Self-check ───────────────────────────────────────
        self._validate(content, project_rel)

        # ── Write ────────────────────────────────────────────
        frontmatter = {
            "id": layer_id,
            "type": "readme",
            "name": name,
            "summary": summary,
            "status": status,
            "author": author,
            "maintainer": maintainer,
            "created": existing_created,
            "updated": updated or generated,
            "generated": generated,
            "parent": parent_id,
        }
        self.storage.write_readme(project_rel, frontmatter, content)
        return content

    # ── internals ─────────────────────────────────────────────

    # ── project-status.md ────────────────────────────────────

    def rebuild_project_status(self) -> str:
        """Scan all top-level projects and generate ``project-status.md``."""
        from backend.storage import DocEntry

        projects_dir = str(self.storage.kb_root / "projects")
        archive_dir = str(self.storage.kb_root / "archive")

        rows: list[tuple[str, str, str, str, int, str]] = []
        # (status_group, name, rel_path, summary, doc_count, updated)

        for base_rel in ("projects", "archive"):
            for entry in self.storage.list_children(base_rel):
                if not entry.is_dir:
                    continue
                rel = f"{base_rel}/{entry.name}"
                try:
                    meta = self.storage.get_readme_meta(rel)
                except FileNotFoundError:
                    continue
                docs = self.storage.get_doc_entries(rel)
                rows.append((
                    meta.status if base_rel == "archive" else "active",
                    meta.name,
                    rel,
                    meta.summary,
                    len(docs),
                    meta.updated,
                ))

        today = date.today().isoformat()
        lines = ["# 项目状态", "", f"更新于 {today}", ""]

        status_order = ["active", "completed", "cancelled", "abandoned"]
        status_labels = {
            "active": "进行中",
            "completed": "已完成",
            "cancelled": "已取消",
            "abandoned": "已废弃（到期自动清理）",
        }
        status_footer = {
            "abandoned": "\n> `abandoned` 状态的项目在标记 30 天后自动清除。",
        }

        for st in status_order:
            group = [r for r in rows if r[0] == st]
            if not group:
                continue
            lines.append(f"## {status_labels[st]}")
            lines.append("")
            lines.append("| 项目 | 摘要 | 文档 | 最后更新 |")
            lines.append("|------|------|------|---------|")
            for _, name, rel, summary, dc, up in sorted(group, key=lambda x: x[1]):
                lines.append(
                    f"| {name} → `{rel}` | {summary} | {dc} | {up} |"
                )
            lines.append("")
            footer = status_footer.get(st)
            if footer:
                lines.append(footer)
                lines.append("")

        content = "\n".join(lines)
        (self.storage.kb_root / "project-status.md").write_text(
            content, encoding="utf-8"
        )
        return content

    # ── garbage collection ────────────────────────────────────

    def garbage_collect(self) -> list[str]:
        """Remove ``abandoned`` projects older than 30 days.

        Returns a list of removed project names (empty if none).
        """
        removed: list[str] = []
        cutoff = date.today() - timedelta(days=30)

        for entry in self.storage.list_children("archive"):
            if not entry.is_dir:
                continue
            rel = f"archive/{entry.name}"
            try:
                meta = self.storage.get_readme_meta(rel)
            except FileNotFoundError:
                continue

            if meta.status != "abandoned":
                continue

            # Parse updated date — if it's empty/invalid, skip
            try:
                abandoned_date = date.fromisoformat(meta.updated)
            except (ValueError, TypeError):
                continue

            if abandoned_date > cutoff:
                continue  # not old enough

            # Remove
            target = self.storage.kb_root / rel
            shutil.rmtree(str(target))
            removed.append(meta.name or entry.name)

        if removed:
            # Rebuild root readme (archive pointer changed)
            self.rebuild("")

        return removed

    # ── internals ─────────────────────────────────────────────

    @staticmethod
    def _resolve_id(project_rel: str, name: str) -> str:
        """Generate a stable layer id.

        Root is always ``"root"``; projects get a hash from the name.
        """
        if project_rel in ("", "."):
            return "root"
        # Build id from real path components for determinism
        parts = [p for p in project_rel.split("/") if p not in ("projects", "")]
        if not parts:
            parts = [name]
        return generate_readme_id(parts)

    @staticmethod
    def _validate(content: str, project_rel: str) -> None:
        """Basic sanity: ensure no unresolved placeholders remain."""
        remaining = [p for p in
                     ["{layer_id}", "{name}", "{summary}", "{status}",
                      "{author}", "{maintainer}", "{created}",
                      "{updated}", "{generated}", "{parent}",
                      "{doc_entries}", "{project_entries}", "{archive_entries}",
                      "{archive_footer}"]
                     if p in content]
        if remaining:
            raise ValueError(
                f"readme_generator: unresolved placeholders {remaining} "
                f"in {project_rel!r}"
            )
