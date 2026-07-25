"""FastAPI application — REST API for MyKnowledge Web UI.

Shared backend code with the MCP server (``mcp_server.py``) via
``Storage`` / ``ReadmeGenerator`` — same data, same tools, different
protocol.

Security: the server binds to **127.0.0.1 only** so only local processes
can reach it.  No authentication needed because no external network
access is possible.
"""

from __future__ import annotations

import asyncio, os, time, json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from backend.config import resolve_root
from backend.events import poll_version
from backend.mcp_server import _lock_file, _LOCK_TIMEOUT
from backend.readme_generator import ReadmeGenerator
from backend.storage import Storage

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
    lock = _lock_file(resolve_root())
    if not lock.exists():
        return
    try:
        ts = int(lock.read_text(encoding="utf-8").split(":")[1])
        if time.time() - ts < _LOCK_TIMEOUT:
            raise HTTPException(
                423,
                "AI 正在操作知识库，当前为只读模式。请稍后再试。",
            )
    except (ValueError, IndexError, OSError):
        pass  # corrupt lock — ignore


# ── Document content validation ────────────────────────────


def _validate_doc(payload: DocumentPayload, storage: Storage) -> list[dict]:
    """Validate document content before saving.

    Returns a list of issues (empty = valid).  Raise 400 if non-empty.
    """
    import re
    issues: list[dict] = []

    if not payload.summary.strip():
        issues.append({"type": "empty_summary", "message": "摘要不能为空"})

    if not payload.content.strip():
        issues.append({"type": "empty_body", "message": "正文不能为空"})
        return issues

    from backend.mcp_server import _resolve_ref, _extract_section

    refs = re.findall(r'\]\(ref:([^\s)]+?)(?:::([^)]*))?\)', payload.content)
    for ref_path, section in refs:
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
            issues.append({
                "type": "ref_not_found",
                "message": f"引用路径不存在: {ref_path}",
            })

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
        last_version = poll_version(kb_root)
        last_keepalive = time.monotonic()
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            current = poll_version(kb_root)
            if current != last_version:
                last_version = current
                yield f"event: updated\ndata: {current}\n\n"
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
    storage, _ = get_storage()
    entries = storage.list_children(project_rel)
    return {
        "items": [
            {
                "name": e.name,
                "path": f"{project_rel}/{e.name}" if project_rel else e.name,
                "is_dir": e.is_dir,
                "modified": e.modified,
            }
            for e in entries
        ]
    }


@app.get("/api/document/{path:path}/meta")
def api_get_document_meta(path: str):
    """Get document frontmatter as JSON."""
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
        raise HTTPException(404, "document not found")


@app.get("/api/document/{path:path}/refs")
def api_get_document_with_refs(path: str):
    """Get document + refs as JSON.

    Returns ``{content, refs: [{path, title, content}]}``.
    """
    storage, _ = get_storage()
    from backend.mcp_server import _resolve_ref, _yaml_dump, _extract_section
    import re

    try:
        meta, body = storage.read_document(path)
    except FileNotFoundError:
        raise HTTPException(404, "document not found")

    content = f"---\n{_yaml_dump(meta)}---\n\n{body}"
    refs = re.findall(r'\]\(ref:([^\s)]+?)(?:::([^)]*))?\)', body)
    seen = {path}
    ref_list = [(r, s) for r, s in refs if r not in seen and not seen.add(r)]

    resolved_refs: list[dict] = []
    for ref_path, section in ref_list:
        entry: dict = {"path": ref_path, "title": section or ""}
        try:
            ref_meta, ref_body = _resolve_ref(path, ref_path, storage)
            entry["content"] = ref_body
            entry["resolved"] = True
        except FileNotFoundError:
            entry["content"] = "⚠ 引用路径不存在"
            entry["resolved"] = False
        resolved_refs.append(entry)

    return {"content": content, "refs": resolved_refs}


@app.get("/api/document/{path:path}")
def api_get_document(path: str):
    """Get document content + metadata as JSON (without resolving refs).

    ⚠ Must be registered AFTER /meta and /refs to avoid route conflict.
    """
    storage, _ = get_storage()
    try:
        meta, body = storage.read_document(path)
        return {
            "content": body,
            "meta": {k: v for k, v in meta.items()
                     if k in ("id", "type", "summary", "author",
                              "maintainer", "created", "updated", "template")},
        }
    except FileNotFoundError:
        raise HTTPException(404, "document not found")


# ══════════════════════════════════════════════════════════════
#  Write
# ══════════════════════════════════════════════════════════════

from pydantic import BaseModel


class DocumentPayload(BaseModel):
    content: str
    summary: str = ""
    doc_type: str = "knowledge"


@app.post("/api/document/{path:path}", status_code=201)
def api_create_document(path: str, payload: DocumentPayload):
    """Create a new knowledge document."""
    _check_write_allowed()
    storage, gen = get_storage()
    _check_doc(payload, storage)
    meta = {"type": payload.doc_type, "summary": payload.summary}
    from backend.mcp_server import _attach_identity
    _attach_identity(meta, True)
    storage.write_document(path, meta, payload.content)
    from backend.mcp_server import _parent_rel
    gen.rebuild(_parent_rel(path))
    gen.rebuild_project_status()
    from backend.events import broadcast
    broadcast(storage.kb_root)
    return {"status": "ok", "id": meta.get("id", "")}


@app.put("/api/document/{path:path}")
def api_update_document(path: str, payload: DocumentPayload):
    """Update an existing knowledge document."""
    _check_write_allowed()
    storage, gen = get_storage()
    _check_doc(payload, storage)
    try:
        old_meta, _ = storage.read_document(path)
    except FileNotFoundError:
        raise HTTPException(404, "document not found")

    new_meta = dict(old_meta)
    if payload.summary:
        new_meta["summary"] = payload.summary
    if payload.content:
        body = payload.content
    else:
        _, body = storage.read_document(path)

    from backend.mcp_server import _attach_identity
    _attach_identity(new_meta, False)
    storage.write_document(path, new_meta, body, auto_id=False)
    from backend.mcp_server import _parent_rel
    gen.rebuild(_parent_rel(path))
    gen.rebuild_project_status()
    from backend.events import broadcast
    broadcast(storage.kb_root)
    return {"status": "ok", "id": new_meta.get("id", "")}


@app.delete("/api/document/{path:path}")
def api_delete_document(path: str):
    """Delete a knowledge document."""
    _check_write_allowed()
    storage, gen = get_storage()
    full = storage.kb_root / path
    if not full.exists():
        raise HTTPException(404, "document not found")
    full.unlink()
    from backend.mcp_server import _parent_rel
    gen.rebuild(_parent_rel(path))
    gen.rebuild_project_status()
    from backend.events import broadcast
    broadcast(storage.kb_root)
    return {"status": "deleted"}


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
    storage, _ = get_storage()
    readme_path = f"{project_rel}/readme.md" if project_rel else "readme.md"
    try:
        meta, _ = storage.read_document(readme_path)
        return {
            "id": meta.get("id", ""),
            "name": meta.get("name", ""),
            "summary": meta.get("summary", ""),
            "status": meta.get("status", "active"),
            "updated": meta.get("updated", ""),
            "author": meta.get("author", ""),
            "maintainer": meta.get("maintainer", ""),
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
    gen.rebuild(parent if parent else "")
    gen.rebuild_project_status()
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
    new_name: str


@app.put("/api/document/{path:path}/rename")
def api_rename_document(path: str, payload: DocRenamePayload):
    """Rename a single document (file mv + refs + rebuild)."""
    from backend.mcp_server import rename_document as _rd
    _check_write_allowed()
    storage, gen = get_storage()
    try:
        result = _rd(storage, path, payload.new_name)
        return {"status": "ok", "message": result}
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        raise HTTPException(400, str(e))


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
#  Lock status
# ══════════════════════════════════════════════════════════════


@app.get("/api/lock")
def api_lock():
    """Return current lock status as JSON."""
    lock = _lock_file(resolve_root())
    if not lock.exists():
        return {"locked": False}

    try:
        content = lock.read_text(encoding="utf-8")
        pid, ts_str = content.strip().split(":")
        ts = int(ts_str)
        since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))
        expires_ts = ts + _LOCK_TIMEOUT
        expires_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(expires_ts))
        expired = time.time() > expires_ts
        return {
            "locked": not expired,
            "pid": int(pid),
            "since": since,
            "expires_at": expires_at,
            "expired": expired,
        }
    except (ValueError, IndexError, OSError):
        return {"locked": False, "corrupt": True}


@app.post("/api/check")
def api_check():
    """Run integrity check."""
    storage, gen = get_storage()
    removed = gen.garbage_collect()
    gen.rebuild_project_status()
    return {"removed": removed}


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
#  Entry point
# ══════════════════════════════════════════════════════════════

# Not run directly — started via `myknowledge serve`
