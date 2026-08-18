"""AI-client collaboration configuration — generation & detection.

Semi-automated onboarding: the frontend triggers config generation, the
backend **incrementally merges** MyKnowledge entries into the user's global
AI-client config files (``~/.claude`` / ``~/.codebuddy``).

Critical safety constraint: we never overwrite the user's existing config —
we only add/update the ``MyKnowledge`` MCP server entry, our ``hooks``
matcher, and our ``MyKnowledge-agent.md`` agent file.  Existing servers
(e.g. RAPID / CodeGraph) and unrelated settings are preserved untouched.

MVP platforms: ClaudeCode + CodeBuddyIDE. WorkBuddy is the fallback (not built).
``ClaudeDesktop`` is MCP-only (Claude Desktop does not support hooks / custom
agents), so its KINDS are restricted to ``mcp``.

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
#  平台定义（平台标识符与前端 store.clientPlatforms 的 key 严格一致）
# ══════════════════════════════════════════════════════════════
# 平台标识符用 PascalCase（无空格/下划线，URL 无需编码），读起来即展示名
# 去掉空格：ClaudeCode → "Claude Code"、CodeBuddyIDE → "CodeBuddy IDE"。
# 磁盘配置目录（~/.claude、~/.codebuddy…）是厂商事实标准，与标识符解耦，
# 全部路径与 mcp_only / cli_names 由 AiClientConfig/platforms.json 单一来源管理。
PLATFORMS: tuple
KINDS = ("mcp", "hooks", "agent")
MCP_ONLY_PLATFORMS: tuple
_platforms_cache: dict | None = None


def _aiclient_config_dir() -> Path:
    """Path to the AI-client config data (``backend/AiClientConfig``).

    Holds ``platforms.json`` (per-OS vendor config paths) and ``agents/``
    (agent prompt + per-platform frontmatter). Shipped with the package
    (PyInstaller datas / wheel package-data).
    """
    return Path(__file__).resolve().parent / "AiClientConfig"


def _load_platforms_data() -> dict:
    """Load (and cache) the whole ``platforms.json`` dict."""
    global _platforms_cache
    if _platforms_cache is None:
        jf = _aiclient_config_dir() / "platforms.json"
        if not jf.is_file():
            raise RuntimeError(
                f"缺失平台配置: {jf}（backend/AiClientConfig/platforms.json）")
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"平台配置格式错误: {jf}: {e}") from e
        platforms = data.get("platforms")
        if not isinstance(platforms, dict):
            raise RuntimeError(f"平台配置缺少 platforms 字典: {jf}")
        _platforms_cache = data
    return _platforms_cache


# 平台枚举从 platforms.json 派生（单一来源）。
_platforms_data = _load_platforms_data()
PLATFORMS = tuple(_platforms_data["platforms"].keys())


def _kinds_for(platform: str) -> tuple:
    """Kinds applicable to a platform (from platforms.json ``kinds``).

    E.g. ClaudeDesktop → ``("mcp",)`` (no hooks/agent); Enchante →
    ``("mcp", "agent")`` (no hooks).  Unknown platforms raise ``ValueError``.
    """
    if platform not in PLATFORMS:
        raise ValueError(
            f"不支持的平台: {platform}（仅 {'/'.join(PLATFORMS)}）")
    kinds = _platform_spec(platform).get("kinds") or list(KINDS)
    return tuple(kinds)


def _current_os() -> str:
    """The current OS key (macos / windows / linux)."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _platform_spec(platform: str) -> dict:
    """Return a platform's spec from ``AiClientConfig/platforms.json``.

    Raises ``ValueError`` for an unknown platform.
    """
    platforms = _load_platforms_data()["platforms"]
    if platform not in platforms:
        raise ValueError(
            f"不支持的平台: {platform}（仅 {'/'.join(PLATFORMS)}）")
    return platforms[platform]


def _resolve_path(template: str) -> Path:
    """Resolve a path template (``~`` / ``%APPDATA%`` / ``%USERPROFILE%``)."""
    if template.startswith("~"):
        return Path.home() / template.lstrip("~/")
    import os
    for var in ("APPDATA", "USERPROFILE"):
        prefix = f"%{var}%"
        if template.startswith(prefix):
            base = os.environ.get(var)
            if base:
                return Path(base) / template[len(prefix):].lstrip("/\\")
    return Path(template)


def _platform_paths(platform: str) -> dict:
    """Return the resolved config paths for a platform on the current OS.

    Reads the vendor config locations from ``platforms.json`` (per-OS), so the
    platform identifier stays display-name-readable while the real config dir
    (~/.claude, ~/.codebuddy, …) is a fixed factual path.  Global (user-wide)
    locations only — we never write project files.
    """
    spec = _platform_spec(platform)
    paths = spec.get("paths", {})
    os_key = _current_os()
    # Fall back to macOS if the current OS isn't yet mapped in platforms.json.
    entry = paths.get(os_key) or paths.get("macos") or {}
    # 平台可能不提供某类路径（如 Enchante 无 mcp_file/settings_file/agents_dir，
    # 其 MCP 走 deeplink、skill 走 skills_dir）——缺省为空 Path。
    return {
        "mcp_file": _resolve_path(entry.get("mcp_file", "")),
        "settings_file": _resolve_path(entry.get("settings_file", "")),
        "agents_dir": _resolve_path(entry.get("agents_dir", "")),
    }


def _config_dir(platform: str) -> Path:
    """The vendor config dir used for client_installed detection.

    From ``platforms.json`` ``config_dir`` (per-OS); the vendor's own home
    folder, not derived from the display-name identifier.
    """
    entry = (_platform_spec(platform).get("paths", {})
             .get(_current_os()) or _platform_spec(platform).get("paths", {}).get("macos"))
    return _resolve_path(entry["config_dir"])


def _cli_name(platform: str) -> str:
    """CLI name for PATH-based install detection (``""`` if none)."""
    return (_platform_spec(platform).get("cli_names", {})
            .get(_current_os(), ""))


def _enchante_installed() -> bool:
    """Enchante app present under /Applications or ~/Applications."""
    for base in (Path("/Applications"), Path.home() / "Applications"):
        for name in ("Enchanté.app", "Enchante.app"):
            if (base / name).exists():
                return True
    return False


def enchante_deeplink() -> str:
    """Build the Enchante MCP install deeplink (returns the link string).

    ``enchante://mcp/install?name=MyKnowledge&config=<base64 MCPServerBundle>``
    The ``config`` is base64 of a JSON bundle: ``{displayName, description,
    icon, config: {type, command, args, env}}``.  Generation only — the actual
    deeplink capture is handled by the Enchante client, not the backend.

    The base64 is URL-quoted (with the unreserved/reserved-query safe set) so
    ``+`` becomes ``%2B`` — Enchanté's Swift ``URLComponents`` would otherwise
    parse a raw ``+`` as a space and corrupt the payload.
    """
    import base64
    import urllib.parse
    bundle = {
        "displayName": "MyKnowledge",
        "description": "MyKnowledge 知识管理平台",
        "icon": "book.closed",
        "config": mcp_entry("Enchante"),
    }
    enc = base64.b64encode(json.dumps(bundle, ensure_ascii=False)
                           .encode("utf-8")).decode("ascii")
    # 强制 '+'→'%2B'（base64 可能含 +），保留 base64 其他安全字符与 query 分隔符。
    quoted = urllib.parse.quote(
        enc, safe="-._~!$&'()*,;=:@/?")
    return f"enchante://mcp/install?name=MyKnowledge&config={quoted}"


# ══════════════════════════════════════════════════════════════
#  条目构建
# ══════════════════════════════════════════════════════════════
def mcp_entry(platform: str) -> dict:
    """The MyKnowledge MCP stdio server entry (points at the global KB).

    Injects ``MYKNOWLEDGE_CLIENT=<platform>`` so the MCP server process can
    identify which client launched it when reporting heartbeats.  Each platform
    gets its own entry (env is per-server, so platforms never overwrite one
    another).
    """
    return {
        "type": "stdio",
        "command": sys.executable,
        "args": ["-m", "backend.cli", "mcp"],
        "env": {
            "MYKNOWLEDGE_ROOT": str(resolve_root()),
            "MYKNOWLEDGE_CLIENT": platform,
        },
    }


def _hooks_command_claude() -> str:
    """Claude/WorkBuddy: curl the hook with $CLAUDE_TOOL_USE_INPUT."""
    return (
        f"curl -s -X POST {HOOK_ENDPOINT} "
        "-H 'Content-Type: application/json' "
        "-d '$CLAUDE_TOOL_USE_INPUT'"
    )


def _hooks_command_codebuddy() -> str:
    """CodeBuddy: forward stdin JSON via the ``backend.hooks_forward`` module.

    CodeBuddy passes PreToolUse data on **stdin** and uses IDE tool names
    (execute_command / write_to_file / ...); ``hooks_forward.py`` reads stdin,
    POSTs to the hook endpoint, and prints the response JSON.

    We invoke it as ``python3 -m backend.hooks_forward`` (module form) instead
    of an absolute script path — the module is located by the installed
    ``backend`` package, so the hook survives moving/copying the KB config to
    another machine or an installed distribution.
    """
    return "python3 -m backend.hooks_forward"


def hooks_matcher(platform: str) -> dict:
    """The PreToolUse hook matcher (guards bare AI operations via HTTP).

    Platform-differentiated command:
      - ClaudeCode / WorkBuddy: curl with ``$CLAUDE_TOOL_USE_INPUT``, matcher ``Bash``.
      - CodeBuddyIDE: helper script reading stdin, matcher ``*`` (match all tools —
        ``hooks.py`` allows MCP calls internally, so a broad matcher is safe).
    """
    if platform == "CodeBuddyIDE":
        return {
            "matcher": "*",
            "hooks": [{"type": "command",
                       "command": _hooks_command_codebuddy()}],
        }
    return {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": _hooks_command_claude()}],
    }


def _matcher_is_mine(matcher: dict, cmd: str) -> bool:
    """True if a PreToolUse matcher is the MyKnowledge hook (by command signature).

    Recognises our hook by its command (claude/curl-$CLAUDE_TOOL_USE_INPUT or
    codebuddy/hooks_forward.py) so we never mistake a user's own hook for ours.
    """
    if not isinstance(matcher, dict):
        return False
    hooks = matcher.get("hooks")
    if not isinstance(hooks, list) or not hooks:
        return False
    first = hooks[0]
    return isinstance(first, dict) and first.get("command") == cmd


def _agents_dir() -> Path:
    """Path to the AI-client agent templates (``backend/AiClientConfig/agents``).

    Holds the agent prompt body (``MyKnowledge-agent.md``) plus the per-platform
    frontmatter map (``frontmatter.json``). Shipped with the package (PyInstaller
    datas / wheel package-data).
    """
    return _aiclient_config_dir() / "agents"


def _agent_template() -> str:
    """Read the agent prompt body from ``backend/AiClientConfig/agents/MyKnowledge-agent.md``.

    Content is separated from code so edits don't require a code change.
    Raises a clear ``RuntimeError`` if the template is missing.
    """
    tpl = _agents_dir() / "MyKnowledge-agent.md"
    if not tpl.is_file():
        raise RuntimeError(
            f"缺失 Agent 模板: {tpl}（backend/AiClientConfig/agents/MyKnowledge-agent.md）")
    return tpl.read_text(encoding="utf-8")


def _frontmatter_variants() -> list:
    """Load the per-platform frontmatter map from ``frontmatter.json``.

    Schema: ``{"agent_file": str, "variants": [{"platforms": [str, ...],
    "frontmatter": {k: v, ...}}, ...]}``. A platform's frontmatter is the
    ``frontmatter`` dict of the variant whose ``platforms`` list contains it.
    Raises ``RuntimeError`` if the map is missing/corrupt or a platform has no
    matching variant.
    """
    jf = _agents_dir() / "frontmatter.json"
    if not jf.is_file():
        raise RuntimeError(
            f"缺失 frontmatter 配置: {jf}（backend/AiClientConfig/agents/frontmatter.json）")
    try:
        data = json.loads(jf.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"frontmatter 配置格式错误: {jf}: {e}") from e
    variants = data.get("variants")
    if not isinstance(variants, list):
        raise RuntimeError(f"frontmatter 配置缺少 variants 列表: {jf}")
    return variants


def _frontmatter_for(platform: str) -> dict:
    """Return the frontmatter dict for a platform (from ``frontmatter.json``)."""
    for variant in _frontmatter_variants():
        if platform in (variant.get("platforms") or []):
            fm = variant.get("frontmatter")
            if isinstance(fm, dict):
                return fm
    raise RuntimeError(
        f"frontmatter 配置未覆盖平台: {platform}（检查 frontmatter.json 的 platforms）")


def _skills_dir(platform: str) -> Path:
    """The skills install dir for a platform (from platforms.json), or empty."""
    spec = _platform_spec(platform)
    entry = (spec.get("paths", {})
             .get(_current_os()) or spec.get("paths", {}).get("macos") or {})
    tpl = entry.get("skills_dir", "")
    return _resolve_path(tpl) if tpl else Path()


def _agent_target_path(platform: str) -> Path:
    """Where the agent/skill file is written for a platform (user's dir).

    Enchante uses a skill file at ``~/.agents/skills/myknowledge/SKILL.md``;
    all other platforms use ``<agents_dir>/MyKnowledge-agent.md``.
    """
    if platform == "Enchante":
        return _skills_dir(platform) / "SKILL.md"
    return _platform_paths(platform)["agents_dir"] / "MyKnowledge-agent.md"


def _agent_file_exists(platform: str, p: dict | None = None) -> bool:
    """True if the platform's agent/skill file already exists on disk."""
    if platform == "Enchante":
        target = _agent_target_path(platform)
        return target.is_file()
    path = (p or _platform_paths(platform))["agents_dir"] / "MyKnowledge-agent.md"
    return path.exists()


def _skill_template() -> str:
    """Read the Enchante SKILL.md prompt body from the templates dir."""
    tpl = _aiclient_config_dir() / "agents" / "SKILL.md"
    if not tpl.is_file():
        raise RuntimeError(
            f"缺失 SKILL 模板: {tpl}（backend/AiClientConfig/agents/SKILL.md）")
    return tpl.read_text(encoding="utf-8")


def _skill_content() -> str:
    """Enchante SKILL.md: minimal frontmatter (name+description) + body."""
    body = _skill_template()
    return (
        "---\n"
        "name: MyKnowledge\n"
        "description: MyKnowledge 知识管理平台协作 Skill：通过 MCP 检索与维护本地知识库\n"
        "---\n\n"
        f"{body}"
    )


def agent_content(platform: str) -> str:
    """MyKnowledge agent markdown: body from template + per-platform frontmatter.

    The frontmatter is read from ``frontmatter.json`` (not hardcoded), so adding
    a platform or changing its format requires only a data edit, no code change.
    Enchante uses the SKILL.md format (minimal frontmatter + body) instead.
    """
    if platform == "Enchante":
        return _skill_content()
    prompt = _agent_template()
    fm_lines = ["---"]
    for key, value in _frontmatter_for(platform).items():
        # Render YAML-ish frontmatter lines: booleans/None → lowercase YAML
        # literals (true/false/null); lists → comma-joined (tools: a, b, c).
        if isinstance(value, bool):
            fm_lines.append(f"{key}: {'true' if value else 'false'}")
        elif value is None:
            fm_lines.append(f"{key}: null")
        elif isinstance(value, (list, tuple)):
            fm_lines.append(f"{key}: {', '.join(map(str, value))}")
        else:
            fm_lines.append(f"{key}: {value}")
    fm_lines.append("---")
    return "\n".join(fm_lines) + "\n\n" + prompt


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
def client_installed(platform: str) -> bool:
    """Is the AI client installed / has a config environment?

    Platform-level (shared across mcp/hooks/agent kinds) — the vendor config
    dir comes from ``_config_dir`` (not derived from the display-name id):
      - ClaudeCode: ``~/.claude`` dir exists, or the ``claude`` CLI is on PATH.
      - ClaudeDesktop: ``~/Library/Application Support/Claude`` dir exists
        (where ``claude_desktop_config.json`` lives).
      - CodeBuddyIDE: ``~/.codebuddy`` dir exists.
      - WorkBuddy: ``~/.workbuddy`` dir exists.
      - Enchante: ``Enchanté.app`` / ``Enchante.app`` under ``/Applications`` or
        ``~/Applications``.
    Read-only detection — never writes anything.
    """
    import shutil
    if platform == "Enchante":
        return _enchante_installed()
    cfg_dir = _config_dir(platform)
    # Some clients also expose a CLI on PATH (e.g. ClaudeCode → ``claude``);
    # the CLI name comes from platforms.json ``cli_names`` (per-OS).
    cli = _cli_name(platform)
    if cli:
        return cfg_dir.exists() or shutil.which(cli) is not None
    return cfg_dir.exists()


def detect_platform(platform: str) -> dict:
    """Return detection for one platform: ``{client_installed, connection, mcp, hooks, agent}``.

    ``client_installed`` — whether the client is installed;
    ``connection`` — MCP liveness (not_connected/connected/inactive/lost);
    ``mcp``/``hooks``/``agent`` — whether our MyKnowledge entries exist (each
    only evaluated if the platform supports that kind, per platforms.json).
    """
    kinds = _kinds_for(platform)
    p = _platform_paths(platform)
    result = {
        "client_installed": client_installed(platform),
        "connection": _connection_status(platform),
        "mcp": False,
        "hooks": False,
        "agent": False,
    }

    if "mcp" in kinds:
        mcp_data = _load_json(p.get("mcp_file") or Path())
        result["mcp"] = "MyKnowledge" in (mcp_data.get("mcpServers") or {})

    if "hooks" in kinds:
        settings = _load_json(p["settings_file"])
        hk = settings.get("hooks") or {}
        cmd = hooks_matcher(platform)["hooks"][0]["command"]
        result["hooks"] = any(
            _matcher_is_mine(m, cmd)
            for lst in hk.values()
            if isinstance(lst, list)
            for m in lst
        )

    if "agent" in kinds:
        # Enchante uses a SKILL.md in its skills dir; others use MyKnowledge-agent.md.
        result["agent"] = _agent_file_exists(platform, p)
    return result


def _connection_status(platform: str) -> str:
    """Current MCP connection level for a platform (from in-process heartbeat)."""
    from backend.connection import status
    return status(platform)


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
    if kind not in _kinds_for(platform):
        raise ValueError(f"平台 {platform} 不支持 {kind} 配置（仅支持 {_kinds_for(platform)}）")
    p = _platform_paths(platform)

    if kind == "mcp":
        path = p["mcp_file"]
        data = _load_json(path)
        servers = data.setdefault("mcpServers", {})
        servers["MyKnowledge"] = mcp_entry(platform)
        _save_json(path, data)
        return {"platform": platform, "kind": "mcp", "file": str(path),
                "status": "written", "detected": True}

    if kind == "hooks":
        path = p["settings_file"]
        data = _load_json(path)
        hooks = data.setdefault("hooks", {})
        existing = hooks.get("PreToolUse") or []
        matcher = hooks_matcher(platform)
        cmd = matcher["hooks"][0]["command"]
        # 幂等：若已存在本平台的 MyKnowledge 钩子（按 command 签名识别），不重复追加。
        if not any(_matcher_is_mine(m, cmd) for m in existing):
            existing.append(matcher)
        hooks["PreToolUse"] = existing
        _save_json(path, data)
        return {"platform": platform, "kind": "hooks", "file": str(path),
                "status": "written", "detected": True}

    # agent
    path = _agent_target_path(platform)
    if path.exists():
        return {"platform": platform, "kind": "agent", "file": str(path),
                "status": "exists", "detected": True,
                "message": "Agent 文件已存在，未覆盖"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(agent_content(platform), encoding="utf-8")
    return {"platform": platform, "kind": "agent", "file": str(path),
            "status": "written", "detected": True}


def remove_kind(platform: str, kind: str) -> dict:
    """Remove the MyKnowledge config entry for one platform/kind.

    Only MyKnowledge-related entries are touched — the user's other config
    (other mcpServers, other hooks/matchers, unrelated settings) is preserved.
    Idempotent: removing an already-absent entry succeeds (no error).

    Returns ``{"platform", "kind", "file", "status": "removed"}``.
    """
    if platform not in PLATFORMS:
        raise ValueError(f"不支持的平台: {platform}")
    if kind not in KINDS:
        raise ValueError(f"不支持的配置类型: {kind}（mcp/hooks/agent）")
    if kind not in _kinds_for(platform):
        raise ValueError(f"平台 {platform} 不支持 {kind} 配置（仅支持 {_kinds_for(platform)}）")
    p = _platform_paths(platform)

    if kind == "mcp":
        path = p["mcp_file"]
        data = _load_json(path)
        servers = data.get("mcpServers")
        if isinstance(servers, dict):
            servers.pop("MyKnowledge", None)
            _save_json(path, data)
        return {"platform": platform, "kind": "mcp", "file": str(path),
                "status": "removed"}

    if kind == "hooks":
        path = p["settings_file"]
        data = _load_json(path)
        hooks = data.get("hooks")
        if isinstance(hooks, dict):
            existing = hooks.get("PreToolUse") or []
            cmd = hooks_matcher(platform)["hooks"][0]["command"]
            # 只移除 MyKnowledge 的钩子（按 command 签名识别），保留用户其他 matcher/hook
            kept = [m for m in existing if not _matcher_is_mine(m, cmd)]
            if len(kept) != len(existing):
                hooks["PreToolUse"] = kept
                _save_json(path, data)
        return {"platform": platform, "kind": "hooks", "file": str(path),
                "status": "removed"}

    # agent
    path = _agent_target_path(platform)
    if path.exists():
        path.unlink()
    return {"platform": platform, "kind": "agent", "file": str(path),
            "status": "removed"}
