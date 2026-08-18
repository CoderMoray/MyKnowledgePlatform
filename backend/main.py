"""FastAPI application — REST API for MyKnowledge Web UI.

Shared backend code with the MCP server (``mcp_server.py``) via
``Storage`` / ``ReadmeGenerator`` — same data, same tools, different
protocol.

Security: the server binds to **127.0.0.1 only** so only local processes
can reach it.  No authentication needed because no external network
access is possible.
"""

from __future__ import annotations

import asyncio, os, re, subprocess, sys, threading, time, json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.config import resolve_root
from backend.events import poll_event
from backend.mcp_server import _lock_file, _lock_timeout, _pid_alive, _read_lock
from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage


def _extract_all_refs(body: str) -> list[tuple[str, str, str]]:
    """Extract all reference links from markdown body.

    Returns a list of ``(type, path, title)`` tuples where *type* is
    ``ref`` (internal KB ref) or ``external`` (http(s) URL).
    Code blocks and inline code are stripped before scanning.

    Handles edge cases:
    - URLs/paths inside ``` fenced code blocks — skipped
    - URLs/paths inside `` `inline code` `` — skipped
    - Matches only ``[text](url)`` and ``[text](ref:path)`` syntax
    - ``[text](<bare>@<bare>)`` (email-like) — excluded
    - ``[text](http(s)://...)`` — type: ``external``
    - ``[text](ref:...)`` — type: ``ref``
    - Parentheses in URLs are handled with balanced bracket matching
    """
    import re

    # Step 1: strip fenced code blocks (``` ... ```)
    body = re.sub(r'```.*?```', '', body, flags=re.DOTALL)
    # Step 2: strip inline code (`...`)
    body = re.sub(r'`[^`]+`', '', body)

    results: list[tuple[str, str, str]] = []

    # Step 3: extract markdown links [text](url), skip image links ![text](url)
    for m in re.finditer(r'(?<!!)\[([^\]]*)\]\(', body):
        start = m.end()  # position after '('
        link_text = m.group(1).strip()
        if not link_text:
            continue

        # Balanced parentheses matching for the URL/path
        depth = 1
        i = start
        while i < len(body) and depth > 0:
            if body[i] == '(':
                depth += 1
            elif body[i] == ')':
                depth -= 1
            i += 1
        raw_path = body[start:i - 1].strip()

        if raw_path.startswith(('http://', 'https://')):
            results.append(('external', raw_path, link_text))
        elif raw_path.startswith('ref:'):
            ref_path = raw_path[4:]
            section = ''
            if '::' in ref_path:
                ref_path, section = ref_path.split('::', 1)
            # %20 → 空格：所有读取路径统一拿到真实路径（unquote 幂等，空格原样）
            from urllib.parse import unquote
            results.append(('ref', unquote(ref_path), section))

    return results


# ── ref 写入规范化 + 存在性校验（S16）───────────────────────────

_REF_LINK_RE = re.compile(r'(\[[^\]]*\]\()(ref:)([^)\n]*)(\))')


def normalize_ref_content(content: str) -> str:
    """ref: 链接路径内的空格 → %20（幂等；% 不是空格，不会二次编码）。

    只在 ``[text](ref:...)`` 链接内替换，不碰普通文本/外链/代码块。
    ``::章节`` 内的空格一并编码（与前端 ``replace(/ /g, "%20")`` 一致）。
    """
    def _sub(m: re.Match) -> str:
        return m.group(1) + m.group(2) + m.group(3).replace(" ", "%20") + m.group(4)
    return _REF_LINK_RE.sub(_sub, content)


def _extract_ref_links(content: str) -> list[tuple[str, str]]:
    """提取所有 ref: 链接的 (目标路径, 链接文本)，供 check_ref_targets 使用。

    与 _extract_all_refs 的区别：额外保留 [文本] 部分（空 target 文案需要）。
    剥离代码块/行内代码后扫描（与 _extract_all_refs 一致）。
    """
    body = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
    body = re.sub(r'`[^`]+`', '', body)
    from urllib.parse import unquote
    out: list[tuple[str, str]] = []
    for m in _REF_LINK_RE.finditer(body):
        text_part = m.group(1)               # "[文本]("
        link_text = text_part[1:-2].strip()  # 去掉 "[" 与 "]("
        raw = m.group(3)
        if "::" in raw:
            raw = raw.split("::", 1)[0]
        out.append((unquote(raw), link_text))
    return out


def _days_in_trash(storage, target: str) -> str:
    """返回目标已删除的天数文案（如 "3 天"）；匹配不到/解析失败返回空串。"""
    from backend.trash import list_trash
    from datetime import datetime
    for item in list_trash(storage):
        if item.get("original_path") == target:
            deleted_at = item.get("deleted_at", "")
            try:
                dt = datetime.fromisoformat(deleted_at)
                days = (datetime.now() - dt).days
                return f"{days} 天"
            except Exception:
                return ""
    return ""


def _classify_ref_targets(storage, content: str,
                          old_content: str | None = None) -> list[dict]:
    """扫描 content 中 ref: 链接，返回结构化目标分类（不阻断写入）。

    返回 ``[{type, ref_path, display_text, days}]``：
      - type: ``"dead"``（目标不存在）| ``"in_trash"``（在垃圾箱）| ``"empty"``（空 target）
      - ref_path: 目标路径（``empty`` 时为空字符串）
      - display_text: 链接显示文本（引用意图证据）
      - days: 仅 in_trash 且可计算时给出（如 ``"3 天"``），否则 ``None``
    外链（http/https）跳过；normal（目标存在）无条目。

    old_content 非空时（update 场景）：只检查「新 - 旧」差集里本次引入的
    ref 目标，用户原有内容里的问题不返回。
    """
    def _key(target: str, link_text: str) -> str:
        # 非空目标用路径做 key（链接文本改了不算新引用）；
        # 空目标路径都是空串无法区分，用链接文本做 key。
        return target if target.strip() else f"<empty>:{link_text}"

    refs = _extract_ref_links(content)
    if old_content is not None:
        old_keys = {_key(t, l) for t, l in _extract_ref_links(old_content)}
        refs = [(t, l) for t, l in refs if _key(t, l) not in old_keys]

    out: list[dict] = []
    for ref_path, link_text in refs:
        if not ref_path.strip():
            out.append({
                "type": "empty", "ref_path": "", "display_text": link_text,
                "days": None,
            })
            continue
        from backend.trash import ref_status
        status = ref_status(storage, ref_path)
        if status == "in_trash":
            out.append({
                "type": "in_trash", "ref_path": ref_path,
                "display_text": link_text,
                "days": _days_in_trash(storage, ref_path) or None,
            })
        elif status == "dead":
            out.append({
                "type": "dead", "ref_path": ref_path,
                "display_text": link_text, "days": None,
            })
    return out


def check_ref_targets(storage, content: str,
                      old_content: str | None = None) -> list[str]:
    """扫描 content 中 ref: 链接，返回给 AI 看的文本警告列表（不阻断写入）。

    - 外链（http/https）→ 跳过（外部可达性不检查）
    - normal（目标存在）→ 无提示
    - in_trash（目标在垃圾箱）→ 警告「可恢复」（含已删除天数）
    - dead（目标不存在）→ 警告「死链」
    - 空/纯空格 target → 提示「ref 目标为空」（含链接文本）

    old_content 非空时（update 场景）：只检查「新 - 旧」差集里本次引入的
    ref 目标，用户原有内容里的问题不警告。
    """
    warnings: list[str] = []
    for item in _classify_ref_targets(storage, content, old_content):
        ref_path = item["ref_path"]
        link_text = item["display_text"]
        if item["type"] == "empty":
            warnings.append(
                f"⚠ ref 目标为空（未填写路径）: 「{link_text}」\n"
                f"  该引用的链接文本表明你有引用意图，按序处理：\n"
                f"  1. 用链接文本自查：nav__find(keyword=\"{link_text}\") 找到目标 → 补全路径\n"
                f"  2. 自查找不到 → 该目标可能来自用户上下文 → 向用户确认应引用的文档（勿直接移除）\n"
                f"  3. 仅在确认该引用为笔误/多余时 → 移除"
            )
        elif item["type"] == "in_trash":
            head = (f"⚠ 引用目标在垃圾箱中（可恢复，已删除 {item['days']}）: {ref_path}"
                    if item["days"] else
                    f"⚠ 引用目标在垃圾箱中（可恢复）: {ref_path}")
            warnings.append(
                f"{head}\n"
                f"  该文档可能是用户有意删除的；如用户明确需要，先确认再调 "
                f"write__restore_document 恢复\n"
                f"  · 引用应指向其他文档 → 更新引用\n"
                f"  · 该引用为误写/非必需 → 移除\n"
                f"  · 用户未提及 → 保留现状（前端显示\"可恢复\"），交付时提醒用户"
            )
        elif item["type"] == "dead":
            warnings.append(
                f"⚠ 引用目标不存在（将显示为死链）: {ref_path}\n"
                f"  自查：nav__exists / nav__find 确认是否路径写错；"
                f"找到正确路径 → 修正后重新保存\n"
                f"  · 该引用为误写/多余 → 直接移除\n"
                f"  · 用户指令明确要求引用该文档 → 告知用户后创建目标文档，"
                f"或向用户确认应引用的文档\n"
                f"  · 用户未提及 → 保留现状，交付时提醒用户"
            )
    return warnings


def _rest_ref_warnings(storage, content: str,
                       old_content: str | None = None) -> list[dict]:
    """REST 返回给前端的结构化 ref_warnings（契约 [{type, ref_path, display_text}]）。

    内部 days 字段不下发（前端契约未定义；AI 文本文案在 check_ref_targets 里用）。
    """
    return [
        {"type": it["type"], "ref_path": it["ref_path"],
         "display_text": it["display_text"]}
        for it in _classify_ref_targets(storage, content, old_content)
    ]

# ── App creation ───────────────────────────────────────────

app = FastAPI(title="MyKnowledge", version="0.5.0")

# CORS — 允许前端在开发时从不同端口访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_storage() -> tuple[Storage, ReadmeGenerator]:
    """Get the KB storage and generator for the current request."""
    kb_root = resolve_root()
    storage = Storage(kb_root=kb_root)
    template = kb_root / "_templates" / "readme.md"
    gen = ReadmeGenerator(storage=storage, template_path=template)
    return storage, gen


# ── Lock check dependency ──────────────────────────────────


def _check_write_allowed():
    """Raise 423 if another process holds a valid write lock."""
    from fastapi import HTTPException
    info = _read_lock(resolve_root())
    if info is None:
        return  # 无锁 / 空锁（已释放）→ 放行
    # 锁的持有进程已死（死锁）→ 视为无锁，不拦（与 acquire_lock 的死锁检测一致）
    if time.time() - info["ts"] < _lock_timeout() and _pid_alive(info["pid"]):
        holder = info.get("agent", "")
        detail = "AI 正在操作知识库，当前为只读模式。请稍后再试。"
        if holder:
            detail += f"（持有者: {holder}）"
        raise HTTPException(423, detail)


def _guard_doc_write_path(path: str) -> None:
    """Reject invalid document write paths before they reach storage.

    Enforces the full MCP ``_validate_path`` rules for file paths:
    whitelist prefixes, no readme.md (owned by the readme generator),
    and correct project-tree layout (projects/P/common-knowledge/…).
    """
    from backend.mcp_server import _validate_path
    try:
        _validate_path(path, kind="file")
    except ValueError as e:
        raise HTTPException(400, str(e))


def _guard_read_path(path: str) -> None:
    """Reject read paths that escape the KB (absolute / ``..`` traversal).

    Read access is looser than write (system files like readme/trash are
    readable), but absolute paths and traversal would read files outside
    the KB — an information leak.  ``storage._abs`` also enforces
    containment at the last mile.
    """
    from backend.mcp_server import _validate_read_path
    try:
        _validate_read_path(path)
    except ValueError:
        raise HTTPException(400, f"非法路径: {path}")


# ── Document content validation ────────────────────────────


def _validate_doc(payload: DocumentPayload, storage: Storage) -> list[dict]:
    """Validate document content before saving.

    Returns a list of issues (empty = valid). Dead refs (``ref_not_found``)
    are logged as warnings but do NOT block saving — the frontend already
    displays them as ``resolved: false`` in the refs list.
    """
    import logging
    logger = logging.getLogger(__name__)

    issues: list[dict] = []

    if not payload.summary.strip():
        issues.append({"type": "empty_summary", "message": "摘要不能为空"})

    if not payload.content.strip():
        issues.append({"type": "empty_body", "message": "正文不能为空"})
        return issues

    from backend.mcp_server import _resolve_ref, _extract_section

    all_refs = _extract_all_refs(payload.content)
    dead_refs = 0
    for ref_type, ref_path, section in all_refs:
        if ref_type == "external":
            continue  # external URLs can't be validated
        try:
            if section:
                meta, ref_body = _resolve_ref("", ref_path, storage)
                excerpt = _extract_section(ref_body, section)
                if excerpt is None:
                    issues.append({
                        "type": "section_not_found",
                        "message": f"引用段落不存在: {ref_path} 中的「{section}」",
                    })
        except FileNotFoundError:
            dead_refs += 1  # log but don't block

    if dead_refs:
        logger.info("document saved with %d unresolved ref(s)", dead_refs)

    return issues


def _check_doc(payload: DocumentPayload, storage: Storage) -> None:
    """Raise 400 if document content has issues."""
    from fastapi import HTTPException
    issues = _validate_doc(payload, storage)
    if issues:
        raise HTTPException(400, detail={"status": "error", "issues": issues})


# ══════════════════════════════════════════════════════════════
#  SSE — real-time KB change notifications
# ══════════════════════════════════════════════════════════════


POLL_INTERVAL = 2  # seconds between version checks
_KEEPALIVE_INTERVAL = 15  # seconds between SSE comment keep-alive pings


@app.get("/api/events")
async def api_events():
    """Server-Sent Events endpoint — notifies the frontend of KB updates.

    The frontend connects via ``EventSource``. The server polls the
    version file every 2 seconds and sends an ``updated`` event when
    the version changes.  A periodic comment (``: keepalive``) prevents
    proxies from closing idle connections.

    Works identically in local and cloud deployments — swap the
    underlying ``poll_version()`` implementation for Redis/DB if needed.
    """
    kb_root = resolve_root()

    async def event_stream():
        last_event = poll_event(kb_root)
        last_keepalive = time.monotonic()
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            current = poll_event(kb_root)
            if current.get("version") != last_event.get("version"):
                last_event = current
                # 下发 {version, type}，前端可据此只响应特定事件类型（如 diagnose）。
                yield f"event: updated\ndata: {json.dumps(current, ensure_ascii=False)}\n\n"
            if time.monotonic() - last_keepalive >= _KEEPALIVE_INTERVAL:
                last_keepalive = time.monotonic()
                yield ": keepalive\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx proxy compatibility
        },
    )


# ══════════════════════════════════════════════════════════════
#  Navigation
# ══════════════════════════════════════════════════════════════


@app.get("/api/readme/{project_rel:path}", response_class=PlainTextResponse)
def api_read_readme(project_rel: str = ""):
    """Get the routing index of a KB layer."""
    _guard_read_path(project_rel)
    storage, _ = get_storage()
    try:
        return PlainTextResponse(storage.read_content(
            f"{project_rel}/readme.md" if project_rel else "readme.md"
        ))
    except FileNotFoundError:
        raise HTTPException(404, "readme not found")


@app.get("/api/list/{project_rel:path}")
def api_list_dir(project_rel: str = ""):
    """List files and directories in a KB layer."""
    _guard_read_path(project_rel)
    storage, _ = get_storage()
    entries = storage.list_children(project_rel)
    items = []
    for e in entries:
        entry = {
            "name": e.name,
            "path": f"{project_rel}/{e.name}" if project_rel else e.name,
            "is_dir": e.is_dir,
            "modified": e.modified,
        }
        if e.is_dir:
            try:
                meta, _ = storage.read_document(f"{entry['path']}/readme.md")
                entry["status"] = meta.get("status") or "active"
                entry["summary"] = meta.get("summary") or ""
            except FileNotFoundError:
                entry["summary"] = ""
        elif e.name.endswith(".md"):
            try:
                meta, _ = storage.read_document(entry["path"])
                entry["summary"] = meta.get("summary") or ""
            except Exception:
                entry["summary"] = ""
        items.append(entry)
    return {"items": items}


@app.get("/api/document/{path:path}/meta")
def api_get_document_meta(path: str):
    """Get document frontmatter as JSON."""
    _guard_read_path(path)
    storage, gen = get_storage()
    try:
        meta, body = storage.read_document(path)
        return {
            "id": meta.get("id", ""),
            "type": meta.get("type", ""),
            "summary": meta.get("summary", ""),
            "author": meta.get("author", ""),
            "maintainer": meta.get("maintainer", ""),
            "created": meta.get("created", ""),
            "updated": meta.get("updated", ""),
            "template": meta.get("template", ""),
        }
    except FileNotFoundError:
        raise HTTPException(404, _deleted_detail(storage, path))


def _deleted_detail(storage: Storage, path: str) -> dict:
    """Distinguish a trashed/deleted doc from a never-existed path.

    Returns ``{"detail": "deleted", "deleted_at": "<ISO>"}`` if the path was
    tracked in git and later deleted, otherwise ``{"detail": "not_found"}``.
    """
    import subprocess

    kb = storage.kb_root
    git_dir = kb / ".git"
    if not git_dir.is_dir():
        return {"detail": "not_found"}

    try:
        r = subprocess.run(
            ["git", "-C", str(kb), "log", "--diff-filter=D",
             "--format=%ci", "--", path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            first = r.stdout.strip().splitlines()[0]
            return {"detail": "deleted", "deleted_at": first.strip()}
    except Exception:
        pass
    return {"detail": "not_found"}


@app.get("/api/document/{path:path}/refs")
def api_get_document_with_refs(path: str):
    """Get document + refs as JSON.

    Returns ``{content, refs: [{path, title, content}]}``.
    """
    _guard_read_path(path)
    storage, _ = get_storage()
    from backend.mcp_server import _resolve_ref, _yaml_dump, _extract_section
    from backend.trash import ref_status

    try:
        meta, body = storage.read_document(path)
    except FileNotFoundError:
        raise HTTPException(404, "document not found")

    content = f"---\n{_yaml_dump(meta)}---\n\n{body}"
    all_refs = _extract_all_refs(body)
    seen = {path}
    resolved_refs: list[dict] = []
    for ref_type, ref_path, title in all_refs:
        dedup_key = ref_type + ":" + ref_path
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        entry: dict = {"path": ref_path, "title": title, "type": ref_type}
        if ref_type == "external":
            entry["resolved"] = True
            entry["ref_status"] = "normal"
            resolved_refs.append(entry)
            continue

        try:
            ref_meta, ref_body = _resolve_ref(path, ref_path, storage)
            entry["content"] = ref_body
            entry["resolved"] = True
            entry["ref_status"] = "normal"
        except FileNotFoundError:
            entry["content"] = "⚠ 引用路径不存在"
            entry["resolved"] = False
            entry["ref_status"] = ref_status(storage, ref_path)
        resolved_refs.append(entry)

    return {"content": content, "refs": resolved_refs}


@app.get("/api/document/{path:path}")
def api_get_document(path: str):
    """Get document content + metadata as JSON (without resolving refs).

    ⚠ Must be registered AFTER /meta and /refs to avoid route conflict.
    """
    _guard_read_path(path)
    storage, _ = get_storage()
    try:
        meta, body = storage.read_document(path)
        return {
            "content": body,
            "summary": meta.get("summary", ""),
            "version": _doc_version(body, meta.get("summary", "")),
            "meta": {k: v for k, v in meta.items()
                     if k in ("id", "type", "summary", "author",
                              "maintainer", "created", "updated", "template")},
        }
    except FileNotFoundError:
        # 404 区分：① 旧路径有 rename 映射且目标存在 → renamed（前端自动跳转）
        #         ② 已删除(可恢复) → deleted  ③ 从未存在 → not_found
        from backend.renames import resolve_rename
        redirect = resolve_rename(storage, path)
        if redirect:
            raise HTTPException(404, {"detail": "renamed", "redirect_to": redirect})
        raise HTTPException(404, _deleted_detail(storage, path))


# ══════════════════════════════════════════════════════════════
#  Write
# ══════════════════════════════════════════════════════════════

from pydantic import BaseModel


class DocumentPayload(BaseModel):
    content: str
    summary: str = ""
    doc_type: str = "knowledge"
    expected_version: str = ""


def _doc_version(content: str, summary: str = "") -> str:
    """Optimistic-lock version fingerprint.

    ``sha256(f"{summary}\\x00{content}")[:12]`` — content is the raw body
    (no frontmatter), summary is the explicit frontmatter summary field.
    The ``\\x00`` separator never appears in normal text so it's collision-free.
    """
    import hashlib
    return hashlib.sha256(f"{summary or ''}\x00{content}".encode("utf-8")).hexdigest()[:12]


@app.post("/api/document/{path:path}", status_code=201)
def api_create_document(path: str, payload: DocumentPayload):
    """Create a new knowledge document."""
    _check_write_allowed()
    _guard_doc_write_path(path)
    storage, gen = get_storage()
    # S16: ref 路径空格 → %20 规范化（幂等）后，再校验与写入。
    # REST ref_warnings 为结构化数组 [{type, ref_path, display_text}]（前端契约）。
    payload.content = normalize_ref_content(payload.content)
    _check_doc(payload, storage)
    ref_warnings = _rest_ref_warnings(storage, payload.content)
    meta = {"type": payload.doc_type, "summary": payload.summary}
    from backend.mcp_server import _attach_identity
    _attach_identity(meta, True)
    storage.write_document(path, meta, payload.content)
    from backend.mcp_server import _parent_rel
    gen.rebuild(_parent_rel(path))
    gen.rebuild_project_status()
    from backend.events import broadcast
    broadcast(storage.kb_root)
    return {"status": "ok", "id": meta.get("id", ""),
            "ref_warnings": ref_warnings}


class DocRenamePayload(BaseModel):
    path: str
    new_name: str


@app.put("/api/document/rename")
def api_rename_document(payload: DocRenamePayload):
    """Rename a single document (file mv + refs + rebuild).

    必须定义在 {path:path} 端点之前：{path:path} 会贪婪匹配 "rename"，
    后定义的精确端点永远匹配不到。
    """
    from backend.mcp_server import rename_document as _rd
    _check_write_allowed()
    _guard_doc_write_path(payload.path)
    storage, gen = get_storage()
    try:
        result = _rd(storage, payload.path, payload.new_name)
        return {"status": "ok", "message": result}
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        raise HTTPException(400, str(e))


@app.put("/api/document/{path:path}")
def api_update_document(path: str, payload: DocumentPayload):
    """Update an existing knowledge document.

    If content and summary are both unchanged, the write is skipped —
    ``maintainer`` and ``updated`` are not touched.
    """
    _check_write_allowed()
    _guard_doc_write_path(path)
    storage, gen = get_storage()
    try:
        old_meta, old_body = storage.read_document(path)
    except FileNotFoundError:
        raise HTTPException(404, "document not found")

    # ── Optimistic lock check (409 takes precedence over 400) ──
    if payload.expected_version:
        current_version = _doc_version(old_body, old_meta.get("summary", ""))
        if current_version != payload.expected_version:
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=409,
                content={
                    "error": "conflict",
                    "message": "文档已被其他会话修改",
                    "current_version": current_version,
                    "content": old_body,
                    "current_summary": old_meta.get("summary", ""),
                },
            )

    # If content/summary are empty they mean "keep existing", so fill before validate
    if not payload.content:
        payload.content = old_body
    if not payload.summary:
        payload.summary = old_meta.get("summary", "")
    # S16: ref 路径空格 → %20 规范化（幂等）后，再校验与写入
    payload.content = normalize_ref_content(payload.content)
    _check_doc(payload, storage)

    new_content = payload.content
    new_summary = payload.summary
    # REST update：与 MCP 一致，只检查本次改动引入的引用（old_content 差集）
    ref_warnings = _rest_ref_warnings(storage, new_content, old_content=old_body)

    # ── No-op: skip write if nothing changed ──────────────
    if new_content == old_body and new_summary == old_meta.get("summary", ""):
        return {
            "status": "ok",
            "id": old_meta.get("id", ""),
            "unchanged": True,
            "version": _doc_version(old_body, old_meta.get("summary", "")),
            "ref_warnings": ref_warnings,
        }

    new_meta = dict(old_meta)
    new_meta["summary"] = payload.summary

    from backend.mcp_server import _attach_identity
    _attach_identity(new_meta, False)
    storage.write_document(path, new_meta, new_content, auto_id=False)
    from backend.mcp_server import _parent_rel
    gen.rebuild(_parent_rel(path))
    gen.rebuild_project_status()
    from backend.events import broadcast
    broadcast(storage.kb_root)
    return {
        "status": "ok",
        "id": new_meta.get("id", ""),
        "unchanged": False,
        "version": _doc_version(new_content, new_summary),
        "ref_warnings": ref_warnings,
    }


@app.delete("/api/document/{path:path}")
def api_delete_document(path: str):
    """Move a knowledge document into trash (recoverable, 30 days)."""
    _check_write_allowed()
    _guard_doc_write_path(path)
    storage, gen = get_storage()
    full = storage.kb_root / path
    if not full.exists():
        raise HTTPException(404, "document not found")

    from backend.trash import move_doc_to_trash
    trash_rel = move_doc_to_trash(storage, path)
    from backend.mcp_server import _parent_rel
    gen.rebuild(_parent_rel(path))
    gen.rebuild_project_status()
    from backend.events import broadcast
    broadcast(storage.kb_root)
    return {"status": "trashed", "trash_path": trash_rel}


@app.delete("/api/project/{project_rel:path}")
def api_delete_project(project_rel: str):
    """Move a whole project tree into trash (recoverable, 30 days).

    Mirrors ``api_delete_document``: no permanent removal.  The project
    is moved to ``trash/projects/``; refs pointing into it are left as-is
    so ``ref_status`` reports ``in_trash`` (recoverable).  Restoring a
    single doc whose containing project is in trash is rejected by
    ``trash.restore`` until the project is restored first.
    """
    _check_write_allowed()
    storage, gen = get_storage()
    from backend.trash import move_project_to_trash
    try:
        trash_rel = move_project_to_trash(storage, project_rel)
    except FileNotFoundError:
        raise HTTPException(404, _deleted_detail(storage, project_rel))

    # Rebuild affected readmes (parent project + root + project-status)
    parent_parts = project_rel.rstrip("/").split("/")
    if len(parent_parts) > 2 and parent_parts[-2] == "projects":
        parent_rel = "/".join(parent_parts[:-2])
    else:
        parent_rel = "/".join(parent_parts[:-1])
    if parent_rel and parent_rel not in ("projects", "archive", ""):
        gen.rebuild(parent_rel)
    gen.rebuild("")
    gen.rebuild_project_status()
    from backend.events import broadcast
    broadcast(storage.kb_root)
    return {"status": "trashed", "trash_path": trash_rel}


# ══════════════════════════════════════════════════════════════
#  Project meta
# ══════════════════════════════════════════════════════════════


class ProjectMetaPayload(BaseModel):
    name: str = ""
    summary: str = ""
    status: str = ""


@app.get("/api/project/{project_rel:path}")
def api_get_project_meta(project_rel: str):
    """Get project metadata from its readme frontmatter."""
    _guard_read_path(project_rel)
    storage, _ = get_storage()
    readme_path = f"{project_rel}/readme.md" if project_rel else "readme.md"
    try:
        meta, _ = storage.read_document(readme_path)
        return {
            "id": meta.get("id", ""),
            "name": meta.get("name", ""),
            "summary": meta.get("summary", ""),
            "status": meta.get("status", "active"),
            "author": meta.get("author", ""),
            "maintainer": meta.get("maintainer", ""),
            "created": meta.get("created", ""),
            "updated": meta.get("updated", ""),
        }
    except FileNotFoundError:
        raise HTTPException(404, "project not found")


@app.put("/api/project/{project_rel:path}")
def api_update_project_meta(project_rel: str, payload: ProjectMetaPayload):
    """Update project-level metadata."""
    storage, gen = get_storage()
    readme_path = f"{project_rel}/readme.md" if project_rel else "readme.md"
    from datetime import date

    try:
        old_meta, old_body = storage.read_document(readme_path)
    except FileNotFoundError:
        raise HTTPException(404, "project not found")

    new_meta = dict(old_meta)
    if payload.name:
        new_meta["name"] = payload.name
    if payload.summary:
        new_meta["summary"] = payload.summary
    if payload.status:
        new_meta["status"] = payload.status
    new_meta["updated"] = date.today().isoformat()

    storage.write_document(readme_path, new_meta, old_body, auto_id=False)
    parent = "/".join(project_rel.split("/")[:-1]) if project_rel else ""
    # projects/ 是根级系统目录，不是项目层，应重建根 readme
    rebuild_rel = "" if parent == "projects" else (parent or "")
    gen.rebuild(rebuild_rel)
    gen.rebuild_project_status()

    # Auto-archive non-active projects
    from backend.mcp_server import _auto_archive
    _auto_archive(project_rel, storage, gen)

    from backend.events import broadcast
    broadcast(storage.kb_root)
    return {"status": "ok"}


class RenamePayload(BaseModel):
    new_name: str


@app.put("/api/project/{project_rel:path}/rename")
def api_rename_project(project_rel: str, payload: RenamePayload):
    """Rename a project (dir + refs + indices)."""
    from backend.mcp_server import rename_project as _rename
    _check_write_allowed()
    storage, gen = get_storage()
    try:
        result = _rename(storage, project_rel, payload.new_name)
        return {"status": "ok", "message": result}
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        raise HTTPException(400, str(e))


class DocRenamePayload(BaseModel):
    path: str
    new_name: str





# ══════════════════════════════════════════════════════════════
#  Status
# ══════════════════════════════════════════════════════════════


@app.get("/api/status", response_class=PlainTextResponse)
def api_status():
    """Get project status overview."""
    storage, gen = get_storage()
    return PlainTextResponse(gen.rebuild_project_status())


@app.get("/api/status/detail")
def api_status_detail():
    """Return structured status JSON for the dashboard."""
    storage, gen = get_storage()
    doc_count = 0
    project_count = {"total": 0, "active": 0, "completed": 0,
                     "cancelled": 0, "abandoned": 0}
    recent: list[dict] = []

    def _walk_docs(rel_dir: str, project_name: str = ""):
        nonlocal doc_count
        for entry in storage.list_children(rel_dir):
            if entry.name.endswith(".md") and entry.name != "readme.md":
                doc_count += 1
                child = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
                try:
                    meta = storage.read_frontmatter(child)
                    recent.append({
                        "path": child,
                        "name": entry.name.replace(".md", ""),
                        "updated_at": meta.get("updated", entry.modified),
                        "summary": meta.get("summary", ""),
                        "project": project_name,
                    })
                except FileNotFoundError:
                    pass

    _walk_docs("common-knowledge")
    _walk_docs("archive")

    for entry in storage.list_children("projects"):
        if not entry.is_dir:
            continue
        rel = f"projects/{entry.name}"
        try:
            meta = storage.get_readme_meta(rel)
        except FileNotFoundError:
            continue
        project_count["total"] += 1
        status = meta.status
        if status in project_count:
            project_count[status] += 1
        _walk_docs(f"{rel}/common-knowledge", project_name=meta.name)
        # 递归子项目
        for sub in storage.list_children(f"{rel}/projects"):
            if sub.is_dir:
                sub_rel = f"{rel}/projects/{sub.name}"
                try:
                    sub_meta = storage.get_readme_meta(sub_rel)
                except FileNotFoundError:
                    continue
                _walk_docs(f"{sub_rel}/common-knowledge",
                           project_name=f"{meta.name} / {sub_meta.name}")

    recent.sort(key=lambda d: d["updated_at"], reverse=True)
    return {
        "projects": project_count,
        "documents": doc_count,
        "recent": recent[:10],
    }

    return {
        "projects": project_count,
        "documents": doc_count,
    }


# ══════════════════════════════════════════════════════════════
#  Version
# ══════════════════════════════════════════════════════════════


def _kb_version(kb_root: Path) -> str:
    """Return the AI-processed checkpoint commit hash (``agent-commit.txt``).

    Returns empty string if no checkpoint exists (no AI has ever processed).
    """
    try:
        from backend.git_manager import GitManager
        gm = GitManager(kb_root)
        cp = gm.read_checkpoint(kb_root / "agent-commit.txt")
        return (cp[:7] + "...") if cp and len(cp) > 7 else (cp or "")
    except Exception:
        return ""


@app.get("/api/version")
def api_version():
    """Return system version + KB git commit hash."""
    kb_root = resolve_root()
    from backend.__version__ import __version__
    return {
        "system": __version__,
        "kb": _kb_version(kb_root),
    }


# ══════════════════════════════════════════════════════════════
#  MCP connection status
# ══════════════════════════════════════════════════════════════


@app.get("/api/mcp")
def api_mcp():
    """Return MCP server connection status.

    Reads ``.mcp-heartbeat`` written by every MCP tool invocation.
    Returns one of: ``disconnected`` / ``reading`` / ``writing`` / ``connected``.
    """
    kb_root = resolve_root()
    hb = kb_root / ".mcp-heartbeat"
    lock = _lock_file(kb_root)

    if not hb.exists():
        return {"status": "disconnected", "detail": "MCP 未连接"}

    try:
        raw = hb.read_text(encoding="utf-8").strip()
        kind, ts_str = raw.split(":", 1)
        ts = float(ts_str)
    except (ValueError, OSError):
        return {"status": "disconnected", "detail": "心跳文件损坏"}

    elapsed = time.time() - ts

    if elapsed > 60:
        return {"status": "disconnected", "detail": "MCP 已断开（超过 60 秒无心跳）"}

    if kind == "write":
        return {"status": "writing", "detail": "AI 正在写入知识库"}
    if kind == "nav":
        return {"status": "reading", "detail": "AI 正在读取知识库"}

    return {"status": "connected", "detail": "AI 已连接"}


# ══════════════════════════════════════════════════════════════
#  Lock status
# ══════════════════════════════════════════════════════════════


def _iso_local(ts: float) -> str:
    """Format epoch seconds as local-timezone ISO 8601, e.g. ``2026-08-07T20:19:45+08:00``."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat()


@app.get("/api/lock")
def api_lock():
    """Return current lock status as JSON."""
    info = _read_lock(resolve_root())
    if info is None:
        # 无锁 / 空锁（已释放）/ 损坏 → 未锁
        return {"locked": False, "corrupt": False}
    ts = info["ts"]
    expires_ts = ts + _lock_timeout()
    expired = time.time() > expires_ts
    dead = not _pid_alive(info["pid"])  # 死锁：持有进程已死 → 视为未锁
    return {
        "locked": not expired and not dead,
        "pid": info["pid"],
        "agent": info.get("agent", ""),
        # epoch 秒 — 跨时区安全，前端 new Date(since_ts*1000) 直接可用
        "since_ts": ts,
        "expires_ts": expires_ts,
        # 人类可读：带本地时区偏移的 ISO 8601
        "since": _iso_local(ts),
        "expires_at": _iso_local(expires_ts),
        "expired": expired,
        "deadlock": dead,
        "corrupt": False,
    }


@app.post("/api/check")
def api_check():
    """Run integrity check."""
    storage, gen = get_storage()
    removed = gen.garbage_collect()
    gen.rebuild_project_status()
    return {"removed": removed}


_DIAGNOSE_RESULT_FILE = ".diagnose-result.json"


def _diagnose_result_path(storage: Storage) -> Path:
    """KB root result file path (dot-prefixed → skipped by validator noise)."""
    return storage.kb_root / _DIAGNOSE_RESULT_FILE


def _read_saved_diagnose(storage: Storage) -> dict:
    """Read the last persisted diagnose result, or ``{"saved": False}``.

    Never raises on a missing/corrupt file — callers get an empty state so
    the endpoint stays 200 rather than 500.
    """
    p = _diagnose_result_path(storage)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {"saved": False}
    if not isinstance(data, dict):
        return {"saved": False}
    data.setdefault("saved", True)
    return data


def _write_saved_diagnose(storage: Storage, payload: dict) -> None:
    """Atomically persist the diagnose result (tmp + replace).

    Atomicity prevents half-written files being read by ``/diagnose/saved``
    if two requests race or the process is interrupted mid-write.
    """
    p = _diagnose_result_path(storage)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, p)


@app.get("/api/diagnose")
def api_diagnose():
    """Run a read-only structural diagnosis and persist the result.

    Returns ``{"issues": [...], "summary": {...}}`` where each issue carries
    ``path / type / severity / message / action / needs_semantic``.  The
    KB-scan itself is pure read-only (``validate_kb`` uses ``dry_run=True``
    and never writes/commits); only the persisted result file is written so
    the frontend can reload the last check without re-scanning.
    """
    from backend.validator import validate_kb
    import datetime
    storage, gen = get_storage()
    report = validate_kb(storage, gen)
    payload = {
        "issues": [i.__dict__ for i in report.issues],
        "summary": report.summary,
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
    }
    _write_saved_diagnose(storage, payload)
    return {
        "issues": payload["issues"],
        "summary": payload["summary"],
        "generated_at": payload["generated_at"],
    }


@app.get("/api/diagnose/saved")
def api_diagnose_saved():
    """Return the last persisted diagnose result (read/compute separation).

    ``{"saved": True, "issues": [...], "summary": {...}, "generated_at": ...}``
    when a previous ``/api/diagnose`` run saved a result, otherwise
    ``{"saved": False}``.  Missing/corrupt file → empty state (200), not 500.
    """
    storage, _gen = get_storage()
    return _read_saved_diagnose(storage)


# ══════════════════════════════════════════════════════════════
#  Heal (frontend 一键修复：move 孤儿文档 + rebuild 索引)
# ══════════════════════════════════════════════════════════════


class HealMovePayload(BaseModel):
    paths: list[str]
    target_rel: str = ""


@app.post("/api/heal/move")
def api_heal_move(payload: HealMovePayload):
    """Move orphan documents into a ``common-knowledge/`` directory.

    Calls the same shared ``move_document`` used by the
    ``maint__move_document`` MCP tool (single kernel).  Each path is moved
    individually; a failure on one does not abort the others.

    Body: ``{"paths": [...], "target_rel"?: "<目标目录，缺省=同级 common-knowledge>"}``

    Returns ``{"moved": [<新路径>], "failed": [{"path":..., "error":...}]}``.
    """
    from backend.mcp_server import move_document, _peer_ck_dir
    storage, _gen = get_storage()
    moved: list[str] = []
    failed: list[dict] = []
    for src in payload.paths:
        dst_dir = payload.target_rel or _peer_ck_dir(src)
        dst = f"{dst_dir}/{src.split('/')[-1]}"
        try:
            move_document(storage, src, dst)
            moved.append(dst)
        except Exception as exc:  # noqa: BLE001 — 部分失败需标记而非整体 500
            failed.append({"path": src, "error": str(exc)})
    return {"moved": moved, "failed": failed}


class HealRebuildPayload(BaseModel):
    layers: list[str] = []
    all: bool = False


@app.post("/api/heal/rebuild")
def api_heal_rebuild(payload: HealRebuildPayload):
    """Rebuild readme index layers and project-status.

    Merges the ``rebuild_index`` and ``rebuild`` actions (both re-create the
    readme/system index).  ``layers`` lists the affected project layers
    (``""`` for root); ``all: True`` rebuilds every project layer recursively.

    Returns ``{"rebuilt": [<层>], "project_status": true}``.
    """
    storage, gen = get_storage()
    rebuilt: list[str] = []

    layers: list[str] = list(payload.layers)
    if payload.all or not layers:
        # collect every project layer (root + recursive projects/archive)
        def _collect(container: str, out: list[str]) -> None:
            for e in storage.list_children(container):
                if not e.is_dir:
                    continue
                layer = f"{container}/{e.name}"
                out.append(layer)
                if storage.path_exists(f"{layer}/projects"):
                    _collect(f"{layer}/projects", out)
        layers = [""]
        _collect("projects", layers)
        _collect("archive", layers)

    for layer in layers:
        # 项目层先于根层重建（根 readme 读取项目摘要）
        if layer and gen is not None:
            gen.rebuild(layer)
            rebuilt.append(layer)
    if gen is not None:
        gen.rebuild("")
        rebuilt.append("")
        gen.rebuild_project_status()
    return {"rebuilt": rebuilt, "project_status": True}


# ══════════════════════════════════════════════════════════════
#  AI Client Config (阶段三：Claude / CodeBuddy 协作配置生成与检测)
# ══════════════════════════════════════════════════════════════


@app.get("/api/client-config")
def api_client_config_detect():
    """Detect MyKnowledge config presence in each AI client.

    Returns ``{ClaudeCode: {mcp, hooks, agent}, ClaudeDesktop: {...},
    CodeBuddyIDE: {...}, WorkBuddy: {...}}`` — read-only, no writes.
    Platform identifiers are PascalCase (ClaudeCode/ClaudeDesktop/CodeBuddyIDE/WorkBuddy),
    consistent with the frontend store and URL-safe (no spaces).
    """
    from backend.client_config import detect_all
    return detect_all()


@app.post("/api/mcp/heartbeat")
def api_mcp_heartbeat(request: Request):
    """MCP server liveness report.

    The MCP stdio process identifies its platform via the ``MYKNOWLEDGE_CLIENT``
    env it was launched with, and sends it as the ``X-MYKNOWLEDGE-CLIENT`` header.
    A missing/unknown platform is ignored (backward-compatible with older configs
    that lack the env) and returns ``{"status": "ignored"}`` — it is not treated
    as a connection.
    """
    import os
    from backend.client_config import PLATFORMS
    from backend.connection import report, mark_lost
    client = (request.headers.get("X-MYKNOWLEDGE-CLIENT", "")
              or os.environ.get("MYKNOWLEDGE_CLIENT", ""))
    if not client or client not in PLATFORMS:
        return {"status": "ignored"}
    if request.headers.get("X-MYKNOWLEDGE-DISCONNECT") == "1":
        mark_lost(client)
        return {"status": "lost", "platform": client}
    report(client)
    return {"status": "ok", "platform": client}


@app.post("/api/client-config/{platform}/{kind}")
def api_client_config_write(platform: str, kind: str):
    """Incrementally write MyKnowledge config for one platform/kind.

    ``platform``: ``ClaudeCode`` | ``ClaudeDesktop`` | ``CodeBuddyIDE`` | ``WorkBuddy``;
    ``kind``: ``mcp`` | ``hooks`` | ``agent`` (ClaudeDesktop is MCP-only).
    Writes the user's **global** config files (``~/.claude`` / ``~/.codebuddy``),
    merging incrementally without overwriting unrelated existing entries.

    Returns ``{platform, kind, file, status, detected}`` where ``status`` is
    ``"written"`` or ``"exists"`` (agent already present, not overwritten).
    """
    from backend.client_config import write_kind
    try:
        return write_kind(platform, kind)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/client-config/{platform}/{kind}")
def api_client_config_remove(platform: str, kind: str):
    """Remove the MyKnowledge config entry for one platform/kind.

    ``platform``: ``ClaudeCode`` | ``ClaudeDesktop`` | ``CodeBuddyIDE`` | ``WorkBuddy``;
    ``kind``: ``mcp`` | ``hooks`` | ``agent`` (ClaudeDesktop is MCP-only).
    Removes **only** the MyKnowledge entries (the user's other mcpServers /
    hooks / settings are preserved).  Idempotent — removing an already-absent
    entry succeeds.

    Returns ``{platform, kind, file, status: "removed"}``.
    """
    from backend.client_config import remove_kind
    try:
        return remove_kind(platform, kind)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ══════════════════════════════════════════════════════════════
#  Hooks (PreToolUse 管控 AI 裸操作知识库)
# ══════════════════════════════════════════════════════════════


class HookPayload(BaseModel):
    tool_name: str = ""
    tool_input: dict = {}
    cwd: str = ""


@app.post("/hooks/pre-tool-use")
def api_hooks_pre_tool_use(payload: HookPayload):
    """Decide allow/deny for an AI client tool call on the knowledge base.

    Serves Claude PreToolUse + Cursor preToolUse (mutually compatible).  Judgement:
    MCP calls → allow; non-KB targets → allow; KB root + write → deny (+ guidance);
    KB root + read → allow.  Guidance messages are proposals pending confirmation.
    """
    from backend.hooks import evaluate
    return evaluate(payload.model_dump())


# ══════════════════════════════════════════════════════════════
#  Identity (读/写 ~/.myknowledge/config.yaml)
# ══════════════════════════════════════════════════════════════

from backend.config import get_identity, set_identity


class IdentityPayload(BaseModel):
    email: str
    nickname: str


@app.get("/api/identity")
def api_get_identity():
    """Get current user identity."""
    try:
        nick, email = get_identity()
        return {"nickname": nick, "email": email}
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "身份未设置。请运行 myknowledge login 或在此设置。")


@app.put("/api/identity")
def api_set_identity(payload: IdentityPayload):
    """Update user identity (nickname + email)."""
    if not payload.email.strip() or not payload.nickname.strip():
        raise HTTPException(400, "昵称和邮箱不能为空")
    set_identity(payload.email.strip(), payload.nickname.strip())
    return {"status": "ok", "nickname": payload.nickname, "email": payload.email}


# ══════════════════════════════════════════════════════════════
#  Static frontend (mount after all API routes)
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
#  Export
# ══════════════════════════════════════════════════════════════


class ExportPayload(BaseModel):
    projects: list[str]


@app.post("/api/export")
def api_export(payload: ExportPayload):
    """Export one or more projects as encrypted .mkpkg file(s).

    Single project → returns a ``.mkpkg`` binary blob.
    Multiple projects → returns a ``.zip`` containing each .mkpkg.
    """
    import io, json, struct, tarfile, tempfile, zipfile
    from backend.share import publish as share_publish, _build_manifest, _derive_key, _encrypt

    storage, _ = get_storage()
    kb_root = storage.kb_root
    pkg_data: list[tuple[str, bytes]] = []  # (name, raw_bytes)

    for proj_rel in payload.projects:
        from backend.mcp_server import _validate_path
        try:
            _validate_path(proj_rel, kind="dir", storage=storage)
        except ValueError:
            raise HTTPException(400, f"project not found: {proj_rel}")
        proj_path = kb_root / proj_rel
        if not proj_path.is_dir():
            raise HTTPException(400, f"project not found: {proj_rel}")

        manifest = _build_manifest(storage, proj_rel)
        key = _derive_key(manifest)

        buf = tempfile.TemporaryFile()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(str(proj_path), arcname=manifest["name"])
        buf.seek(0)
        raw_data = buf.read()
        buf.close()

        encrypted = _encrypt(raw_data, key)
        manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        header = struct.pack(">I", len(manifest_bytes))
        pkg_data.append((f"{manifest['name']}.mkpkg", header + manifest_bytes + encrypted))

    from urllib.parse import quote as _url_quote

    if len(pkg_data) == 1:
        name, data = pkg_data[0]
        from starlette.responses import Response
        ascii_name = name.encode("ascii", errors="replace").decode("ascii")
        return Response(
            content=data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=\"{ascii_name}\"; "
                    f"filename*=UTF-8''{_url_quote(name)}"
                ),
            },
        )

    # Multiple projects → zip
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in pkg_data:
            zf.writestr(name, data)
    zip_buf.seek(0)
    from starlette.responses import Response
    return Response(
        content=zip_buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=\"myknowledge-export.zip\""},
    )


# ══════════════════════════════════════════════════════════════
#  Search
# ══════════════════════════════════════════════════════════════


@app.get("/api/search")
def api_search(q: str = "", limit: int = 20, kind: str = "all"):
    """Full-KB search.

    Returns ``{"results": [{path, title, summary, snippet}], "total": N}``.

    ``kind``:
      - ``all`` (default): document search.  Title/summary/body hit
        combinations are ranked:
        title+summary+body > title+summary > title+body > summary+body
        > title > summary > body.  readme.md (layer indexes), trash/,
        _templates/, _refs/, publish/ are excluded.
      - ``projects``: project-level search.  Matches each project's
        ``readme.md`` (project name / summary / body) and returns the
        *project directory* as ``path`` — never matches documents under
        ``common-knowledge``.  Root ``readme.md`` is included as ``path=""``.
    """
    storage, _ = get_storage()
    q = (q or "").strip()
    if not q:
        return {"results": [], "total": 0}
    if len(q) > 200:
        raise HTTPException(400, "关键词过长（≤200）")

    want = "project" if kind == "projects" else "doc"
    all_hits = storage.search_documents(q, limit=None)
    hits = [h for h in all_hits if h["type"] == want]
    total = len(hits)
    top = hits[: max(1, min(int(limit), 50))]
    results = [{
        "path": h["path"],
        "title": h["name"],
        "summary": h["summary"],
        "snippet": h["snippet"],
    } for h in top]
    return {"results": results, "total": total}


# ══════════════════════════════════════════════════════════════
#  Trash
# ══════════════════════════════════════════════════════════════


@app.get("/api/trash")
def api_trash_list(offset: int = 0, limit: int = 50):
    """List trash items, paginated.

    ``offset``/``limit`` (default ``limit=50``) enable half-lazy loading: first
    screen 50, scroll-to-bottom loads +50.  Returns ``{items, total, has_more}``.
    """
    storage, _ = get_storage()
    from backend.trash import list_trash
    all_items = list_trash(storage)
    total = len(all_items)
    offset = max(offset, 0)
    limit = max(limit, 1)
    page = all_items[offset:offset + limit]
    return {"items": page, "total": total,
            "has_more": (offset + len(page)) < total}


class TrashRestorePayload(BaseModel):
    trash_path: str


@app.post("/api/trash/restore")
def api_trash_restore(payload: TrashRestorePayload):
    """Restore a trashed item to its original path."""
    storage, gen = get_storage()
    from backend.trash import restore
    try:
        original = restore(storage, payload.trash_path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, detail=str(e))
    # Rebuild indices
    from backend.mcp_server import _parent_rel
    gen.rebuild(_parent_rel(original))
    gen.rebuild("")
    gen.rebuild_project_status()
    from backend.events import broadcast
    broadcast(storage.kb_root)
    return {"status": "restored", "original_path": original}


class TrashEmptyPayload(BaseModel):
    trash_paths: list[str] = []


@app.post("/api/trash/empty")
def api_trash_empty(payload: TrashEmptyPayload = None,
                    all: bool = False):
    """Empty the trash.

    Priority:
      1. body ``trash_paths`` non-empty → precise delete of those items only
         (frontend checkbox multi-select), returns ``{status, removed}``.
      2. else ``?all=true`` → clear **everything** immediately (frontend
         "清空垃圾箱" button; user-triggered with a confirmation dialog).
      3. else → GC: only purge items older than 30 days (backward-compatible,
         used by auto-cleanup).

    Always returns ``{"status": "ok", "removed": N}``.
    """
    storage, gen = get_storage()
    from backend.trash import gc_trash, empty_trash, delete_trash_items

    if payload is not None and payload.trash_paths:
        try:
            n = delete_trash_items(storage, payload.trash_paths)
        except ValueError as e:
            raise HTTPException(400, str(e))
    elif all:
        n = empty_trash(storage)
    else:
        n = gc_trash(storage)

    gen.rebuild("")
    gen.rebuild_project_status()
    from backend.events import broadcast
    broadcast(storage.kb_root)
    return {"status": "ok", "removed": n}


def _frontend_dir() -> Path:
    """Locate the frontend static assets.

    Resolution order:
      1. ``MYKNOWLEDGE_FRONTEND_DIR`` env var — Electron shell / tests override
      2. PyInstaller bundle dir (``sys._MEIPASS/frontend``) — shipped inside
         the desktop backend binary
      3. ``frontend`` package (wheel 随包安装，含 index.standalone.html + vendor/；
         源码开发时同样定位到仓库 frontend/) — PyPI 安装 + 源码两种场景统一
      4. ``./frontend`` relative to cwd — 兼容旧行为兜底
    """
    env_dir = os.environ.get("MYKNOWLEDGE_FRONTEND_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    if getattr(sys, "_MEIPASS", None):
        return (Path(sys._MEIPASS) / "frontend").resolve()
    # PyPI 安装 / 本地源码：frontend 是包（wheel 带 package-data 资源）→ 用包路径定位
    try:
        import frontend as _fe_pkg
        pkg_dir = Path(_fe_pkg.__file__).parent.resolve()
        if pkg_dir.is_dir():
            return pkg_dir
    except Exception:
        pass
    return (Path.cwd() / "frontend").resolve()


_FRONTEND_DIR = _frontend_dir()

# clone 源码后 index.standalone.html 不在 git（被 .gitignore 忽略）→ 首次 serve 自动 build。
# 锁防并发重复 build（多请求同时发现缺失时只 build 一次）。
_standalone_build_lock = threading.Lock()


def _ensure_standalone() -> tuple[bool, str]:
    """standalone 缺失时自动运行 frontend/build.py（需 python3 + node，build.py 内置 node --check）。

    返回 (成功?, 失败原因)。幂等：产物已存在 → 直接成功；并发用锁 + 双检。
    """
    idx = _FRONTEND_DIR / "index.standalone.html"
    if idx.exists():
        return True, ""
    with _standalone_build_lock:
        if idx.exists():  # 等待锁期间其他请求已完成 build
            return True, ""
        try:
            r = subprocess.run(
                [sys.executable, "build.py"],
                cwd=_FRONTEND_DIR, capture_output=True, text=True, timeout=180,
            )
        except Exception as e:  # 超时/权限等
            return False, f"build 执行异常: {e}"
        if r.returncode == 0 and idx.exists():
            return True, ""
        tail = (r.stderr or r.stdout or "").strip()[-400:]
        return False, tail or f"build 退出码 {r.returncode}"


if _FRONTEND_DIR.is_dir():
    @app.get("/")
    def _serve_index():
        idx = _FRONTEND_DIR / "index.standalone.html"
        if not idx.exists():
            ok, err = _ensure_standalone()
            if not ok:
                return PlainTextResponse(
                    f"Frontend build failed (需要 python3 + node 执行 build.py): {err}",
                    status_code=500,
                )
        # no-cache：保证每次刷新拿到最新构建产物（子资源已带 ?v= 版本号，URL 变化即破缓存）
        return PlainTextResponse(
            idx.read_text(encoding="utf-8"),
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")


# ══════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════

# Not run directly — started via `myknowledge serve`
