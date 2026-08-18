"""PreToolUse hook handler — guards "bare AI operations" on the knowledge base.

AI clients (Claude Code / Cursor / CodeBuddy) POST their tool calls here
(``/hooks/pre-tool-use``).  We decide allow/deny based on whether the call
touches the MyKnowledge KB root destructively.

Protocol (Claude PreToolUse + Cursor preToolUse, mutually compatible):
  - Input JSON: ``{tool_name, tool_input, cwd, ...}``
  - Output JSON: ``{"hookSpecificOutput": {"permissionDecision": "allow"|"deny",
      ...}, "permission": ..., "agent_message": ..., "user_message": ...}``
  (Claude reads ``hookSpecificOutput.permissionDecision``; Cursor reads
  ``permission`` + messages.  We return both so one handler serves all.)

Judgement rules:
  1. ``tool_name`` is an MCP call (``mcp:`` / ``mcp__``) → allow (AI using MCP is correct).
  2. Not pointing at the KB root → allow (project code / elsewhere).
  3. KB root + write op → deny + guidance.
  4. KB root + read op (Read/Grep) → allow (reads don't destroy data).
"""

from __future__ import annotations

from pathlib import Path

from backend.config import resolve_root

# MCP tool names referenced in the guidance proposal (for the "use MCP instead" hint).
WRITE_TOOLS = {
    "create": "write__create_document",
    "update": "write__update_document",
    "delete": "write__delete_document",
    "move": "maint__move_document",
    "rebuild": "maint__rebuild_index",
}

# 引导文案（已定稿）。
# 每个键对应被拦截的写操作类型；值为返回给 AI 的 agent_message 最终版。
GUIDANCE_PROPOSAL = {
    "bash_destructive": (
        "检测到你试图用裸命令（rm/mv/cp/mkdir/重定向）直接操作 MyKnowledge 知识库文件。"
        "知识库必须通过 MCP 工具管理：删除请用 write__delete_document，移动请用 "
        "maint__move_document，重建索引请用 maint__rebuild_index。"
        "请改用对应 MCP 工具执行。"
    ),
    "file_write": (
        "检测到你试图直接写入/编辑/删除知识库文件。知识库文档请通过 MCP 工具管理："
        "新建 write__create_document、更新 write__update_document、删除 "
        "write__delete_document。请改用对应 MCP 工具执行。"
    ),
}


def _path_in_kb(raw_path: str, cwd: str, kb_root: Path) -> bool:
    """True if *raw_path* (absolute or relative to *cwd*) resolves under kb_root."""
    p = Path(str(raw_path)).expanduser()
    try:
        p = p.resolve() if p.is_absolute() else (Path(cwd or ".") / p).resolve()
    except OSError:
        return False
    try:
        p.relative_to(Path(kb_root).resolve())
        return True
    except ValueError:
        return False


import re as _re

# Bash 破坏性命令：仅当命令同时引用 KB 路径才判 deny。
_DESTRUCTIVE_PATTERNS = [
    _re.compile(r"(^|[;&|]\s*)\s*rm\b"),
    _re.compile(r"(^|[;&|]\s*)\s*mv\b"),
    _re.compile(r"(^|[;&|]\s*)\s*cp\b"),
    _re.compile(r"(^|[;&|]\s*)\s*mkdir\b"),
    _re.compile(r">"),
    _re.compile(r"(^|[;&|]\s*)\s*truncate\b"),
    _re.compile(r"(^|[;&|]\s*)\s*shred\b"),
]


def _tool_name_is_mcp(tool_name: str) -> bool:
    """MCP tool calls are named ``mcp:`` / ``mcp__`` (server__tool)."""
    return tool_name.startswith("mcp:") or tool_name.startswith("mcp__")


# CodeBuddy IDE tool names → internal canonical names (reused by the judgement).
_TOOL_ALIASES = {
    "execute_command": "Bash",
    "write_to_file": "Write",
    "edit_file": "Edit",
    "apply_patch": "Edit",
    "delete_file": "Delete",
}


def _normalize_tool_name(tool_name: str) -> str:
    """Map CodeBuddy IDE tool names to the internal canonical names.

    CodeBuddy's PreToolUse reports IDE tool names (``execute_command`` /
    ``write_to_file`` / ``edit_file`` / ``delete_file``) instead of Claude's
    ``Bash`` / ``Write`` / ``Edit`` / ``Delete``.  Normalizing lets the existing
    judgement logic reuse the same Bash/file_write classification unchanged.
    """
    return _TOOL_ALIASES.get(tool_name, tool_name)


def evaluate(payload: dict) -> dict:
    """Decide allow/deny for a PreToolUse tool-call payload.

    Returns a Claude + Cursor compatible response dict.  ``*_message`` fields
    carry the finalized guidance text (see ``GUIDANCE_PROPOSAL``).
    """
    tool_name = _normalize_tool_name(str(payload.get("tool_name") or ""))
    tool_input = payload.get("tool_input") or {}
    cwd = str(payload.get("cwd") or "")
    kb_root = resolve_root()

    # 规则 1：MCP 工具调用 → 放行（AI 用 MCP 是对的）。
    if _tool_name_is_mcp(tool_name):
        return _decide("allow", "MCP 工具调用，放行。")

    # 规则 2：不指向 KB 根 → 放行。
    points_at_kb = _points_at_kb(tool_name, tool_input, cwd, kb_root)
    if not points_at_kb:
        return _decide("allow", "不涉及知识库，放行。")

    # 规则 3/4：KB 根 → 写操作 deny，读操作 allow。
    write_kind = _write_op_kind(tool_name, tool_input, cwd, kb_root)
    if write_kind:
        reason = ("拦截对知识库的裸" + ("写命令" if write_kind == "bash_destructive"
                                       else "文件操作") + "。")
        return _decide("deny", reason, proposal=write_kind)
    return _decide("allow", "知识库读取操作，放行。")


def _command_references_kb(cmd: str, kb_root: Path) -> bool:
    """True if a Bash command string references the KB root (symlink-tolerant).

    We check both the unresolved and resolved KB root strings, because on
    macOS ``/var`` is a symlink to ``/private/var`` and a command may contain
    either form.
    """
    return str(kb_root) in cmd or str(kb_root.resolve()) in cmd


def _points_at_kb(tool_name: str, tool_input: dict, cwd: str,
                  kb_root: Path) -> bool:
    """Does this tool call reference a path under the KB root?"""
    tool_input = tool_input or {}
    # Bash 命令：直接看命令串是否引用 KB 根（不能把整条命令当路径解析）。
    if tool_name == "Bash":
        cmd = str(tool_input.get("command") or "")
        return bool(cmd) and _command_references_kb(cmd, kb_root)
    # 文件类工具：校验 file_path 是否落在 KB 内。
    for field in ("file_path",):
        raw = tool_input.get(field)
        if isinstance(raw, str) and raw and _path_in_kb(raw, cwd, kb_root):
            return True
    # 也扫描任意含路径语义的输入字段（防 Edit 旧格式等）
    for v in tool_input.values():
        if isinstance(v, str) and ("/" in v or v.startswith("~")) \
                and _path_in_kb(v, cwd, kb_root):
            return True
    return False


def _write_op_kind(tool_name: str, tool_input: dict, cwd: str,
                   kb_root: Path) -> str | None:
    """Classify a destructive KB write, or ``None`` if it is a read / safe call.

    Returns ``"bash_destructive"`` for a Bash command referencing the KB root
    plus a destructive pattern, or ``"file_write"`` for a Write/Edit/Delete
    tool whose target is inside the KB root.
    """
    if tool_name == "Bash":
        cmd = str((tool_input or {}).get("command") or "")
        if cmd and _command_references_kb(cmd, kb_root):
            return "bash_destructive" if any(
                p.search(cmd) for p in _DESTRUCTIVE_PATTERNS) else None
        return None
    if tool_name in ("Write", "Edit", "Delete"):
        return "file_write"
    return None


def _decide(decision: str, reason: str,
            proposal: str | None = None) -> dict:
    """Build the Claude + Cursor compatible response.

    When *proposal* names a key in ``GUIDANCE_PROPOSAL``, ``agent_message`` /
    ``user_message`` carry the corresponding guidance text (finalized).
    """
    agent_message = reason
    if proposal:
        agent_message = GUIDANCE_PROPOSAL.get(proposal, reason)
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        },
        "permission": decision,
        "agent_message": agent_message,
        "user_message": agent_message,
    }
