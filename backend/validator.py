"""Knowledge base structural validation — single source of truth.

The ``maint__knowledgebase_diagnose`` MCP tool (and, later, a REST endpoint
and a ``heal`` CLI) all call :func:`validate_kb` to locate structural health
problems.  This module is **pure read-only**: it never creates directories,
never writes files, never commits, and never mutates the working tree.

The recursive structure it validates (mirrors ``_validate_path``'s rules):

.. code-block:: text

    root/
    ├── readme.md + project-status.md
    ├── common-knowledge/*.md
    ├── projects/项目名/{readme.md, common-knowledge/, projects/, archive/}
    └── archive/项目名/（同 projects 结构）

- Documents (``.md``) must live under ``common-knowledge/``; a ``.md`` placed
  directly at a project/root layer (e.g. ``projects/P/x.md``) is an orphan
  (``position`` issue).
- ``common-knowledge/`` is a *document* directory, not a container — nothing
  may be nested under it (``illegal``).
- Index files (``readme.md`` / ``project-status.md``) are compared against
  the generated text via ``ReadmeGenerator.rebuild(dry_run=True)`` — an
  in-memory binary comparison, never parsed from markdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.storage import Storage
from backend.readme_generator import ReadmeGenerator

# System noise that must never be inspected as KB content.
_NOISE_NAMES = frozenset({
    "_refs", "_templates", "publish", "trash",
    "config.yaml", "agent-commit.txt", ".mcp-heartbeat", ".lock",
})

# System container names (used to recognise the recursive structure).
_SYSTEM_CONTAINERS = frozenset({"common-knowledge", "projects", "archive"})


@dataclass
class ValidationIssue:
    """A single structural problem found by :func:`validate_kb`.

    Attributes:
        path:            Affected file / directory (KB-relative).
        type:            One of ``position`` / ``metadata`` / ``index`` /
                         ``ref`` / ``illegal`` / ``system``.
        severity:        ``high`` / ``medium`` / ``low``.
        message:         Human-readable message (Chinese).
        action:          Suggested remediation, one of ``move_to_peer_ck`` /
                         ``add_metadata`` / ``rebuild_index`` / ``review`` /
                         ``rebuild``.
        needs_semantic:  Whether semantic judgement is required (decides if
                         the issue belongs in the frontend "complex zone").
    """

    path: str
    type: str
    severity: str
    message: str
    action: str
    needs_semantic: bool = False


@dataclass
class ValidationReport:
    """Aggregated result of :func:`validate_kb`."""

    issues: list[ValidationIssue] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)

    def by_type(self) -> dict[str, list[ValidationIssue]]:
        grouped: dict[str, list[ValidationIssue]] = {}
        for issue in self.issues:
            grouped.setdefault(issue.type, []).append(issue)
        return grouped


# ── noise / structure helpers ────────────────────────────────────

def _is_noise(name: str) -> bool:
    """Whether *name* should be excluded from KB structure inspection."""
    if name.startswith("."):
        return True
    if name == "__pycache__":
        return True
    if name.endswith(".pyc"):
        return True
    return name in _NOISE_NAMES


# ── main validation entrypoint ───────────────────────────────────

def validate_kb(storage: Storage, gen) -> ValidationReport:
    """Recursively scan the KB and return a structural diagnosis.

    Pure read-only: never creates directories, writes files, commits, or
    mutates the working tree.  *gen* is a ``ReadmeGenerator`` used for the
    in-memory ``rebuild(dry_run=True)`` index comparison.
    """
    report = ValidationReport()

    # ── Walk the directory tree, classifying every node ──────
    _walk_tree(storage, "", report, context="root")

    # ── Index consistency (rebuild(dry_run=True) memory compare) ──
    _check_indexes(storage, gen, report)

    # ── project-status.md index check ────────────────────────
    _check_project_status(storage, gen, report)

    # ── Summary ──────────────────────────────────────────────
    by_type = report.by_type()
    report.summary = {
        "total_files": _count_md_files(storage),
        "total_issues": len(report.issues),
        "by_type": {k: len(v) for k, v in sorted(by_type.items())},
    }
    return report


def _is_in_doc_area(rel: str) -> bool:
    """Whether *rel* (a directory) is a ``common-knowledge/`` document area.

    ``common-knowledge/`` is a document directory (not a container): only its
    direct ``.md`` children are valid knowledge documents.  Any file directly
    inside a ``common-knowledge/`` dir lives in the document area.
    """
    return rel == "common-knowledge" or rel.endswith("/common-knowledge")


def _walk_tree(storage: Storage, rel: str, report: ValidationReport,
               context: str = "root") -> None:
    """Recursively walk *rel* classifying every node.

    *context* is one of:
      - ``"root"``       — the KB root (``""``).  Holds the system files
                           (``readme.md``/``project-status.md``) + the three
                           containers ``common-knowledge/``/``projects/``/``archive/``.
      - ``"container"``  — a ``projects/``/``archive/`` container.  Its direct
                           children are project layers.
      - ``"project"``    — a project layer (``projects/P`` etc.).  Its direct
                           children may only be containers + ``readme.md``.

    Documents (``.md``) are valid only directly under a ``common-knowledge/``
    document area; a ``.md`` anywhere else is an orphan → ``position``.
    """
    for entry in storage.list_children(rel):
        child = f"{rel}/{entry.name}" if rel else entry.name

        # ── System noise → skip entirely ─────────────────────
        if _is_noise(entry.name):
            continue

        if entry.is_dir:
            # ── container dirs ───────────────────────────────
            if entry.name == "common-knowledge":
                _check_common_knowledge(storage, child, report)
            elif entry.name in ("projects", "archive"):
                _walk_tree(storage, child, report, context="container")
            elif context == "container":
                # a project layer under a projects/archive container → legal
                _walk_tree(storage, child, report, context="project")
            elif context == "root":
                report.add(ValidationIssue(
                    path=child, type="illegal", severity="medium",
                    message=f"根层目录「{entry.name}」不是系统容器目录 "
                            "(common-knowledge/projects/archive)。",
                    action="review", needs_semantic=True,
                ))
            else:  # context == "project"
                # a directory directly under a project layer, not a container
                report.add(ValidationIssue(
                    path=child, type="illegal", severity="medium",
                    message=f"目录「{entry.name}」直接位于项目层下，不是合法的"
                            "项目容器（子项目必须放在 projects/ 下）。",
                    action="review", needs_semantic=True,
                ))
                # still inspect inside so we don't miss nested problems
                _walk_tree(storage, child, report, context="project")
        else:
            # ── files ────────────────────────────────────────
            if entry.name == "readme.md":
                # system index — existence/position handled by _check_indexes
                continue
            if entry.name == "project-status.md":
                if rel == "":
                    continue  # valid system file at root
                report.add(ValidationIssue(
                    path=child, type="system", severity="medium",
                    message="project-status.md 只能位于根层，此处位置错误。",
                    action="rebuild", needs_semantic=False,
                ))
                continue
            if not entry.name.endswith(".md"):
                report.add(ValidationIssue(
                    path=child, type="illegal", severity="medium",
                    message=f"「{entry.name}」不是 .md 文档，位于知识库结构内。",
                    action="review", needs_semantic=True,
                ))
                continue
            if _is_in_doc_area(rel):
                _check_document(storage, child, report)
            else:
                # orphan doc — a .md directly at root/project/container layer
                report.add(ValidationIssue(
                    path=child, type="position", severity="high",
                    message="知识文档未放在 common-knowledge/ 下（孤儿文档），"
                            "不会被任何索引收录。",
                    action="move_to_peer_ck", needs_semantic=False,
                ))
                # a misplaced doc may still have frontmatter/metadata defects
                _check_document(storage, child, report)


def _check_common_knowledge(storage: Storage, ck_rel: str,
                            report: ValidationReport) -> None:
    """Validate a ``common-knowledge/`` document directory.

    Only ``.md`` documents may live directly under it — no nested dirs.
    """
    entries = storage.list_children(ck_rel)
    if not entries:
        report.add(ValidationIssue(
            path=ck_rel, type="illegal", severity="low",
            message="空目录：common-knowledge/ 下没有任何文档。",
            action="review", needs_semantic=True,
        ))
        return
    for entry in entries:
        child = f"{ck_rel}/{entry.name}"
        if _is_noise(entry.name):
            continue
        if entry.is_dir:
            report.add(ValidationIssue(
                path=child, type="illegal", severity="high",
                message="common-knowledge/ 是文档目录不是项目容器，"
                        "后面不能再有子目录。",
                action="review", needs_semantic=True,
            ))
            # still inspect inside so we don't miss nested problems
            _walk_tree(storage, child, report)
            continue
        if not entry.name.endswith(".md"):
            report.add(ValidationIssue(
                path=child, type="illegal", severity="medium",
                message=f"「{entry.name}」不是 .md 文档，位于 common-knowledge/ 下。",
                action="review", needs_semantic=True,
            ))
            continue
        _check_document(storage, child, report)


def _check_document(storage: Storage, path: str,
                    report: ValidationReport) -> None:
    """Validate a single knowledge document: metadata + dead refs."""
    # ── metadata ────────────────────────────────────────────
    try:
        text = storage.read_content(path)
    except FileNotFoundError:
        return  # race — file vanished mid-scan; skip
    from backend.storage import parse_frontmatter
    meta, _body = parse_frontmatter(text)
    if not meta:
        report.add(ValidationIssue(
            path=path, type="metadata", severity="high",
            message="frontmatter 缺失或 YAML 解析失败（无法读取元信息）。",
            action="add_metadata", needs_semantic=False,
        ))
    else:
        if not meta.get("id"):
            report.add(ValidationIssue(
                path=path, type="metadata", severity="medium",
                message="frontmatter 缺少 id 字段。",
                action="add_metadata", needs_semantic=False,
            ))
        if not meta.get("created"):
            report.add(ValidationIssue(
                path=path, type="metadata", severity="low",
                message="frontmatter 缺少 created 字段。",
                action="add_metadata", needs_semantic=False,
            ))
        if meta.get("summary") is None or not str(meta.get("summary", "")).strip():
            report.add(ValidationIssue(
                path=path, type="metadata", severity="low",
                message="frontmatter 缺少 summary 字段。",
                action="add_metadata", needs_semantic=True,
            ))

    # ── dead refs ───────────────────────────────────────────
    _check_doc_refs(storage, path, _body, report)


def _check_doc_refs(storage: Storage, path: str, body: str,
                    report: ValidationReport) -> None:
    """Extract ``ref:`` links and flag targets that don't resolve."""
    from backend.main import _extract_all_refs
    from backend.mcp_server import _resolve_ref

    try:
        all_refs = _extract_all_refs(body)
    except Exception:
        return
    seen: set[str] = set()
    for ref_type, ref_path, _title in all_refs:
        if ref_type == "external":
            continue  # external URLs can't be validated
        key = ref_type + ":" + ref_path
        if key in seen:
            continue
        seen.add(key)
        try:
            _resolve_ref(path, ref_path, storage)
        except FileNotFoundError:
            report.add(ValidationIssue(
                path=path, type="ref", severity="medium",
                message=f"死链：引用的目标「{ref_path}」不存在。",
                action="review", needs_semantic=True,
            ))


def _readme_parent(storage: Storage, layer: str) -> str:
    """Read the ``parent`` frontmatter value of an existing layer readme.

    Used by the index comparison so the in-memory ``rebuild(dry_run=True)``
    reproduces the same ``parent`` field as the on-disk readme.  Falls back to
    ``""`` when the readme is absent or lacks a ``parent`` field.
    """
    try:
        meta = storage.read_frontmatter(
            f"{layer}/readme.md" if layer else "readme.md")
    except FileNotFoundError:
        return ""
    return str(meta.get("parent") or "")


def _check_indexes(storage: Storage, gen, report: ValidationReport) -> int:
    """Compare each layer's ``readme.md`` against ``rebuild(dry_run=True)``.

    Root layer + every project layer (recursively under ``projects/`` and
    ``archive/``) is rebuilt in-memory and compared to the on-disk readme.
    Inconsistent → ``index`` issue.  Never writes, never commits.
    """
    if gen is None:
        return 0
    # Collect all project layers (dirs that are direct children of a
    # projects/ or archive/ container, recursively).
    layers = [""]  # root
    _collect_project_layers(storage, "projects", layers)
    _collect_project_layers(storage, "archive", layers)

    for layer in layers:
        parent = _readme_parent(storage, layer)
        expected = gen.rebuild(layer, dry_run=True, parent=parent)
        readme_rel = f"{layer}/readme.md" if layer else "readme.md"
        try:
            existing = storage.read_content(readme_rel)
        except FileNotFoundError:
            # readme missing → system issue (missing system file)
            report.add(ValidationIssue(
                path=readme_rel, type="system", severity="medium",
                message="readme.md 缺失（系统索引未生成）。",
                action="rebuild", needs_semantic=False,
            ))
            continue
        if existing != expected:
            report.add(ValidationIssue(
                path=readme_rel, type="index", severity="medium",
                message="readme.md 过时（内容与当前目录结构不一致，需重建）。",
                action="rebuild_index", needs_semantic=False,
            ))
    return len(layers)


def _collect_project_layers(storage: Storage, container: str,
                            out: list[str]) -> None:
    """Collect every project layer under a ``projects/``/``archive/`` container.

    ``projects/`` → ``projects/P``, ``projects/P/projects/C``, etc.
    """
    for entry in storage.list_children(container):
        if not entry.is_dir:
            continue
        layer = f"{container}/{entry.name}"
        if _is_noise(entry.name):
            continue
        out.append(layer)
        # sub-projects container
        sub = f"{layer}/projects"
        if storage.path_exists(sub):
            _collect_project_layers(storage, sub, out)


def _check_project_status(storage: Storage, gen,
                          report: ValidationReport) -> None:
    """Compare ``project-status.md`` against ``rebuild_project_status(dry_run=True)``."""
    if gen is None:
        return
    try:
        expected = gen.rebuild_project_status(dry_run=True)
    except Exception:
        return
    try:
        existing = storage.read_content("project-status.md")
    except FileNotFoundError:
        report.add(ValidationIssue(
            path="project-status.md", type="system", severity="medium",
            message="project-status.md 缺失（系统状态文件未生成）。",
            action="rebuild", needs_semantic=False,
        ))
        return
    if existing != expected:
        report.add(ValidationIssue(
            path="project-status.md", type="index", severity="medium",
            message="project-status.md 过时（与当前项目状态不一致，需重建）。",
            action="rebuild_index", needs_semantic=False,
        ))


def _count_md_files(storage: Storage) -> int:
    """Count knowledge ``.md`` documents (excluding readme/system files)."""
    count = 0

    def _recurse(rel: str, is_root: bool = False) -> None:
        nonlocal count
        for entry in storage.list_children(rel):
            if _is_noise(entry.name):
                continue
            child = f"{rel}/{entry.name}" if rel else entry.name
            if entry.is_dir:
                if entry.name == "common-knowledge":
                    _count_ck(child)
                elif entry.name in ("projects", "archive"):
                    _recurse(child)
                elif is_root:
                    pass
                else:
                    _recurse(child)
            else:
                if (entry.name.endswith(".md")
                        and entry.name != "readme.md"
                        and entry.name != "project-status.md"):
                    count += 1

    def _count_ck(ck_rel: str) -> None:
        nonlocal count
        for entry in storage.list_children(ck_rel):
            if _is_noise(entry.name) or entry.is_dir:
                continue
            if entry.name.endswith(".md"):
                count += 1

    _recurse("", is_root=True)
    return count


def format_report(report: ValidationReport) -> str:
    """Render a :class:`ValidationReport` as human-readable Chinese text."""
    if not report.issues:
        return "知识库结构健康，未发现问题"
    lines = ["## 知识库结构诊断结果\n"]
    by_type = report.by_type()
    order = ["position", "metadata", "index", "ref", "illegal", "system"]
    labels = {
        "position": "位置问题（文档落在错误层）",
        "metadata": "元信息问题（frontmatter 缺陷）",
        "index": "索引问题（readme 过时）",
        "ref": "死链问题（引用目标不存在）",
        "illegal": "非法结构（非法文件/空目录/嵌套）",
        "system": "系统文件问题（缺失或位置错误）",
    }
    for t in order:
        group = by_type.get(t)
        if not group:
            continue
        lines.append(f"### {labels.get(t, t)}（{len(group)}）\n")
        for issue in group:
            lines.append(f"- **{issue.path}** [{issue.severity}] {issue.message}")
        lines.append("")
    lines.append("---")
    s = report.summary
    lines.append(
        f"扫描文件 {s.get('total_files', 0)} 个，发现 {s.get('total_issues', 0)} 个问题。"
    )
    return "\n".join(lines)
