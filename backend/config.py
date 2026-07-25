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
