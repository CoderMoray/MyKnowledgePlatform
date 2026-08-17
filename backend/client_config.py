"""AI-client collaboration configuration — generation & detection.

Semi-automated onboarding: the frontend triggers config generation, the
backend **incrementally merges** MyKnowledge entries into the user's global
AI-client config files (``~/.claude`` / ``~/.codebuddy``).

Critical safety constraint: we never overwrite the user's existing config —
we only add/update the ``MyKnowledge`` MCP server entry, our ``hooks``
matcher, and our ``MyKnowledge-agent.md`` agent file.  Existing servers
(e.g. RAPID / CodeGraph) and unrelated settings are preserved untouched.

MVP platforms: Claude + CodeBuddy IDE. WorkBuddy is the fallback (not built).

The webserver runs on ``127.0.0.1:8080`` (``cli.py serve``); the generated
hook points at its ``/hooks/pre-tool-use`` handler.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.config import resolve_root

WEBSERVER_BASE = "http://127.0.0.1:8080"
HOOK_ENDPOINT = f"{WEBSERVER_BASE}/hooks/pre-tool-use"


# ══════════════════════════════════════════════════════════════
#  平台 → 配置路径映射（扩展 WorkBuddy 时在此追加）
# ══════════════════════════════════════════════════════════════
def _platform_paths(platform: str) -> dict:
    """Return the resolved config paths for a platform.

    Global (user-wide) locations only — we never write project files.
    """
    home = Path.home()
    if platform == "claude":
        return {
            "mcp_file": home / ".claude.json",             # global MCP servers
            "settings_file": home / ".claude" / "settings.json",  # hooks
            "agents_dir": home / ".claude" / "agents",
        }
    if platform == "codebuddy":
        return {
            "mcp_file": home / ".codebuddy" / "mcp.json",   # mcpServers
            "settings_file": home / ".codebuddy" / "settings.json",  # hooks
            "agents_dir": home / ".codebuddy" / "agents",
        }
    raise ValueError(f"不支持的平台: {platform}（仅 claude/codebuddy，WorkBuddy 未实现）")


PLATFORMS = ("claude", "codebuddy")
KINDS = ("mcp", "hooks", "agent")


# ══════════════════════════════════════════════════════════════
#  条目构建
# ══════════════════════════════════════════════════════════════
def mcp_entry() -> dict:
    """The MyKnowledge MCP stdio server entry (points at the global KB)."""
    return {
        "type": "stdio",
        "command": sys.executable,
        "args": ["-m", "backend.cli", "mcp"],
        "env": {"MYKNOWLEDGE_ROOT": str(resolve_root())},
    }


def hooks_matcher() -> dict:
    """The PreToolUse hook matcher (guards bare AI operations via HTTP)."""
    return {
        "matcher": "Bash",
        "hooks": [
            {
                "type": "command",
                "command": (
                    f"curl -s -X POST {HOOK_ENDPOINT} "
                    "-H 'Content-Type: application/json' "
                    "-d '$CLAUDE_TOOL_USE_INPUT'"
                ),
            }
        ],
    }


def agent_content(platform: str) -> str:
    """MyKnowledge agent markdown body, formatted per platform."""
    tools = ("mcp_get_tool_description, mcp_call_tool, "
             "nav__list_dir, nav__get_document, nav__find, write__create_document, "
             "write__update_document, maint__knowledgebase_diagnose")
    prompt = (
        "# MyKnowledge Agent\n\n"
        "你是 MyKnowledge 知识管理平台的专业 Agent。通过 MyKnowledge MCP 服务器操作 "
        "本地知识库：检索、读写文档、维护结构。\n\n"
        "## 能力\n"
        "- 检索：nav__list_dir / nav__get_document / nav__find\n"
        "- 写入：write__create_document / write__update_document\n"
        "- 维护：maint__knowledgebase_diagnose 结构诊断\n"
    )
    if platform == "codebuddy":
        return (
            "---\n"
            f"name: MyKnowledge Agent\n"
            f"description: MyKnowledge 知识管理平台协作 Agent\n"
            f"model: inherit\n"
            f"tools: {tools}\n"
            f"agentMode: manual\n"
            f"enabled: true\n"
            f"enabledAutoRun: true\n"
            f"mcpServers: MyKnowledge\n"
            "---\n"
            f"\n{prompt}"
        )
    # claude
    return (
        "---\n"
        f"name: MyKnowledge Agent\n"
        f"description: MyKnowledge 知识管理平台协作 Agent\n"
        f"tools: {tools}\n"
        f"model: inherit\n"
        "---\n"
        f"\n{prompt}"
    )


# ══════════════════════════════════════════════════════════════
#  JSON 读写（增量合并）
# ══════════════════════════════════════════════════════════════
def _load_json(path: Path) -> dict:
    """Read a JSON dict; missing/corrupt → ``{}`` (never raises)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8")


# ══════════════════════════════════════════════════════════════
#  检测
# ══════════════════════════════════════════════════════════════
def detect_platform(platform: str) -> dict:
    """Return ``{mcp, hooks, agent}`` detection for one platform."""
    p = _platform_paths(platform)
    mcp_data = _load_json(p["mcp_file"])
    mcp = "MyKnowledge" in (mcp_data.get("mcpServers") or {})

    settings = _load_json(p["settings_file"])
    hk = settings.get("hooks") or {}
    hooks = any(
        isinstance(m, dict) and m.get("matcher") == "Bash"
        for lst in hk.values()
        if isinstance(lst, list)
        for m in lst
    )

    agent = (p["agents_dir"] / "MyKnowledge-agent.md").exists()
    return {"mcp": mcp, "hooks": hooks, "agent": agent}


def detect_all() -> dict:
    return {pl: detect_platform(pl) for pl in PLATFORMS}


# ══════════════════════════════════════════════════════════════
#  生成（增量合并写）
# ══════════════════════════════════════════════════════════════
def write_kind(platform: str, kind: str) -> dict:
    """Incrementally write one config kind for a platform."""
    if platform not in PLATFORMS:
        raise ValueError(f"不支持的平台: {platform}")
    if kind not in KINDS:
        raise ValueError(f"不支持的配置类型: {kind}（mcp/hooks/agent）")
    p = _platform_paths(platform)

    if kind == "mcp":
        path = p["mcp_file"]
        data = _load_json(path)
        servers = data.setdefault("mcpServers", {})
        servers["MyKnowledge"] = mcp_entry()
        _save_json(path, data)
        return {"platform": platform, "kind": "mcp", "file": str(path),
                "status": "written", "detected": True}

    if kind == "hooks":
        path = p["settings_file"]
        data = _load_json(path)
        hooks = data.setdefault("hooks", {})
        existing = hooks.get("PreToolUse") or []
        if not any(isinstance(m, dict) and m.get("matcher") == "Bash"
                   for m in existing):
            existing.append(hooks_matcher())
        hooks["PreToolUse"] = existing
        _save_json(path, data)
        return {"platform": platform, "kind": "hooks", "file": str(path),
                "status": "written", "detected": True}

    # agent
    path = p["agents_dir"] / "MyKnowledge-agent.md"
    if path.exists():
        return {"platform": platform, "kind": "agent", "file": str(path),
                "status": "exists", "detected": True,
                "message": "Agent 文件已存在，未覆盖"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(agent_content(platform), encoding="utf-8")
    return {"platform": platform, "kind": "agent", "file": str(path),
            "status": "written", "detected": True}
