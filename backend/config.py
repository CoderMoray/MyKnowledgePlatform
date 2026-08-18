"""Configuration helpers — no singleton, no global state."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def resolve_root(root_arg: Optional[str] = None) -> Path:
    """Determine the knowledge base root directory.

    Resolution order:
      1. ``root_arg`` if provided via CLI
      2. ``MYKNOWLEDGE_ROOT`` environment variable
      3. ``~/.myknowledge/`` (global, independent of cwd)

    The directory does **not** need to exist yet (``init`` creates it).
    """
    if root_arg:
        return Path(root_arg).expanduser().resolve()
    env_root = os.environ.get("MYKNOWLEDGE_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return (Path.home() / ".myknowledge").resolve()


def load_oss_env(env_path: Optional[Path] = None) -> dict:
    """Read OSS credentials from a ``.env`` file.

    Returns a dict with keys ``bucket``, ``endpoint``, ``access_key_id``,
    ``access_key_secret``.  Any missing keys default to ``""``.
    """
    if env_path is None:
        env_path = Path.home() / ".myknowledge" / ".env"
    elif env_path.is_dir():
        env_path = env_path / ".env"

    keys = {
        "OSS_BUCKET": "bucket",
        "OSS_ENDPOINT": "endpoint",
        "OSS_ACCESS_KEY_ID": "access_key_id",
        "OSS_ACCESS_KEY_SECRET": "access_key_secret",
        "OSS_BUCKET_REGION": "region",
        "KNOWLEDGE_SHARE_CODE": "share_code",
        "SHARE_MAP": "share_map",
    }
    result = {v: "" for v in keys.values()}

    if not env_path.exists():
        return result

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip("\"'")
        if k in keys:
            result[keys[k]] = v

    return result


# ══════════════════════════════════════════════════════════════
#  Share config — KNOWLEDGE_SHARE_CODE + SHARE_MAP（聚焦分享，不涉 OSS 键）
#
#  读取优先级：backend/.env 存在优先 → ~/.myknowledge/.env fallback → 都无则空。
#  CLI config 子命令写入 ~/.myknowledge/.env（用户级可写）；backend/.env 存在时
#  提示「backend/.env 存在且优先，配置可能不生效」。
# ══════════════════════════════════════════════════════════════


def backend_env_file() -> Path:
    """Package-adjacent ``.env`` (``backend/.env``) — read-priority source.

    In development it lives at the repo's ``backend/.env``; when installed it is
    the package's ``backend/.env``.  Holding both OSS keys and the share keys.
    """
    return Path(__file__).resolve().parent / ".env"


def user_env_file() -> Path:
    """User-level ``.env`` (``~/.myknowledge/.env``) — CLI ``config`` writes here."""
    return Path.home() / ".myknowledge" / ".env"


def effective_env_file() -> tuple[Path, str]:
    """The env file that takes effect + its source id.

    Priority: ``backend/.env`` → ``~/.myknowledge/.env`` → none (fallback target
    is the user file so a later write becomes effective).  Returns
    ``(path, source)`` with source in ``{"backend", "myknowledge", "none"}``.
    """
    if backend_env_file().is_file():
        return backend_env_file(), "backend"
    if user_env_file().is_file():
        return user_env_file(), "myknowledge"
    return user_env_file(), "none"


def share_env_source() -> str:
    """Current share-config source id: ``backend`` / ``myknowledge`` / ``none``."""
    return effective_env_file()[1]


def load_share_env() -> dict:
    """Load the effective share config with priority.

    Returns ``{"share_code": str, "share_map": str}`` (share_map defaults to
    ``"000"`` when unset).  Only share keys — OSS keys are out of scope here.
    """
    path, _ = effective_env_file()
    env = load_oss_env(path)
    return {
        "share_code": env.get("share_code", ""),
        "share_map": env.get("share_map", "") or "000",
    }


# 分享配置键 → 说明（用于 .env 注释模板 / 键校验）。
SHARE_KEYS = {
    "KNOWLEDGE_SHARE_CODE": "项目知识库分享鉴权码",
    "SHARE_MAP": "分享三位正整数（用于解钥字段池重定向）",
}

_ENV_TEMPLATE = (
    "# MyKnowledge 分享配置（用户级）\n"
    "# 由 `myknowledge config` 管理；读取优先级：backend/.env 存在优先。\n"
    "# KNOWLEDGE_SHARE_CODE = 分享鉴权码；SHARE_MAP = 三位正整数。\n"
)


def _load_env_lines(path: Path) -> tuple[list[str], dict[str, str]]:
    """Read a .env into (non-empty/comment lines, current key→value map).

    Lines are preserved verbatim (blank/comment lines kept) so an existing user
    .env is rewritten without destroying unrelated content or comments.
    """
    lines: list[str] = []
    current: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            lines.append(raw)
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                if k in SHARE_KEYS:
                    current[k] = v.strip().strip("\"'")
    return lines, current


def write_share_env(key: str, value: str) -> Path:
    """Set one share key in ``~/.myknowledge/.env`` (creating it if missing).

    ``key`` must be one of ``SHARE_KEYS``; ``value`` is stripped.  Updates the
    key in place if present, else appends it (with the template on first
    creation).  Returns the written path.
    """
    if key not in SHARE_KEYS:
        raise ValueError(
            f"不支持的分享配置键: {key}（仅 {'/'.join(SHARE_KEYS)}）")
    path = user_env_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines, current = _load_env_lines(path)
    value = value.strip()

    if not lines:
        # 首次创建：模板 + 键值。
        body = _ENV_TEMPLATE + f"{key} = {value}\n"
    elif key in current:
        # 就地更新已有键（保留其他行）。
        body = "\n".join(
            f"{k} = {value}" if raw.strip().startswith(f"{key}") and k == key
            else raw
            for k, raw in zip(_keys_in_order(lines), lines)
        ) + "\n"
    else:
        body = "\n".join(lines) + f"\n{key} = {value}\n"

    path.write_text(body, encoding="utf-8")
    return path


def _keys_in_order(lines: list[str]) -> list[str]:
    """Key present at each line position ('' for blank/comment/non-key)."""
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, _ = line.partition("=")
            out.append(k.strip())
        else:
            out.append("")
    return out


def unset_share_env(key: str) -> Path:
    """Remove a share key from ``~/.myknowledge/.env`` (idempotent)."""
    if key not in SHARE_KEYS:
        raise ValueError(
            f"不支持的分享配置键: {key}（仅 {'/'.join(SHARE_KEYS)}）")
    path = user_env_file()
    if not path.exists():
        return path
    kept = [raw for raw in path.read_text(encoding="utf-8").splitlines()
            if not raw.strip().startswith(f"{key}")]
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return path


def mask_share_code(code: str) -> str:
    """Mask a share code for display (show first 2 + last 2, middle ***).

    Short values (≤4 chars) collapse to ``****``.
    """
    if not code:
        return "(未设置)"
    if len(code) <= 4:
        return "****"
    return f"{code[:2]}***{code[-2:]}"


# ══════════════════════════════════════════════════════════════
#  Identity
# ══════════════════════════════════════════════════════════════


def identity_file() -> Path:
    return Path.home() / ".myknowledge" / "config.yaml"


def get_identity() -> tuple[str, str]:
    """Return ``(nickname, email)`` from config, or raise ``FileNotFoundError``."""
    import yaml
    cfg = identity_file()
    if not cfg.exists():
        raise FileNotFoundError(
            "身份未设置，请运行: myknowledge login <邮箱> <昵称>"
        )
    data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    identity = data.get("identity") or {}
    email = identity.get("email", "")
    nickname = identity.get("nickname", "")
    if not email or not nickname:
        raise ValueError("身份信息不完整")
    return nickname, email


def set_identity(email: str, nickname: str) -> None:
    """Write identity to config."""
    import yaml
    Path.home().joinpath(".myknowledge").mkdir(parents=True, exist_ok=True)
    data = {"identity": {"email": email, "nickname": nickname}}
    identity_file().write_text(
        yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
    )
