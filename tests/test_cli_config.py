"""Tests for ``myknowledge config`` CLI command (share config management)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from backend.cli import cmd_config, build_parser


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Point backend/.env + ~/.myknowledge/.env at temp paths."""
    b_env = tmp_path / "backend" / ".env"
    u_env = tmp_path / "home" / ".myknowledge" / ".env"
    monkeypatch.setattr("backend.config.backend_env_file", lambda: b_env)
    monkeypatch.setattr("backend.config.user_env_file", lambda: u_env)
    return b_env, u_env


def _make_args(action: str | None = None, kv: str = "") -> argparse.Namespace:
    p = build_parser()
    argv = ["config"]
    if action:
        argv.append(action)
    if kv:
        argv.append(kv)
    return p.parse_args(argv)


class TestCmdConfigShow:
    def test_show_when_none(self, isolated_env, capsys) -> None:
        rc = cmd_config(_make_args("show"))
        assert rc == 0
        out = capsys.readouterr().out
        assert "(未设置)" in out
        assert "未设置" in out  # guidance

    def test_show_masks_share_code(self, isolated_env, capsys) -> None:
        _, u_env = isolated_env
        u_env.parent.mkdir(parents=True, exist_ok=True)
        u_env.write_text("KNOWLEDGE_SHARE_CODE = Apple Mono Retail\nSHARE_MAP = 365\n")
        cmd_config(_make_args("show"))
        out = capsys.readouterr().out
        assert "Apple Mono Retail" not in out  # never plaintext
        assert "Ap***il" in out  # masked
        assert "365" in out

    def test_show_warns_when_backend_present(self, isolated_env, capsys) -> None:
        b_env, _ = isolated_env
        b_env.parent.mkdir(parents=True, exist_ok=True)
        b_env.write_text("KNOWLEDGE_SHARE_CODE = back\nSHARE_MAP = 111\n")
        cmd_config(_make_args("show"))
        out = capsys.readouterr().out
        assert "backend/.env 存在且优先" in out

    def test_default_action_is_show(self, isolated_env, capsys) -> None:
        cmd_config(_make_args())
        out = capsys.readouterr().out
        assert "(未设置)" in out


class TestCmdConfigSet:
    def test_set_writes_user_env(self, isolated_env, capsys) -> None:
        _, u_env = isolated_env
        rc = cmd_config(_make_args("set", "KNOWLEDGE_SHARE_CODE=My Code"))
        assert rc == 0
        assert u_env.is_file()
        assert "KNOWLEDGE_SHARE_CODE = My Code" in u_env.read_text(encoding="utf-8")
        out = capsys.readouterr().out
        assert "已写入" in out

    def test_set_share_map(self, isolated_env) -> None:
        _, u_env = isolated_env
        cmd_config(_make_args("set", "SHARE_MAP=365"))
        assert "SHARE_MAP = 365" in u_env.read_text(encoding="utf-8")

    def test_set_share_code_hints_old_packages(self, isolated_env,
                                               capsys) -> None:
        cmd_config(_make_args("set", "KNOWLEDGE_SHARE_CODE=x"))
        out = capsys.readouterr().out
        assert "旧包失效" in out  # hint that old .mkpkg no longer decrypts

    def test_set_warns_when_backend_present(self, isolated_env, capsys) -> None:
        b_env, _ = isolated_env
        b_env.parent.mkdir(parents=True, exist_ok=True)
        b_env.write_text("KNOWLEDGE_SHARE_CODE = back\n")
        cmd_config(_make_args("set", "KNOWLEDGE_SHARE_CODE=new"))
        out = capsys.readouterr().out
        assert "可能不生效" in out

    def test_set_invalid_key(self, isolated_env, capsys) -> None:
        rc = cmd_config(_make_args("set", "OSS_BUCKET=x"))
        assert rc == 1
        out = capsys.readouterr().err
        assert "不支持的键" in out

    def test_set_missing_equals(self, isolated_env, capsys) -> None:
        rc = cmd_config(_make_args("set", "KNOWLEDGE_SHARE_CODE"))
        assert rc == 1
        assert "格式应为" in capsys.readouterr().err


class TestCmdConfigUnset:
    def test_unset_removes_key(self, isolated_env, capsys) -> None:
        _, u_env = isolated_env
        u_env.parent.mkdir(parents=True, exist_ok=True)
        u_env.write_text("KNOWLEDGE_SHARE_CODE = a\nSHARE_MAP = 365\n")
        rc = cmd_config(_make_args("unset", "KNOWLEDGE_SHARE_CODE"))
        assert rc == 0
        text = u_env.read_text(encoding="utf-8")
        assert "KNOWLEDGE_SHARE_CODE" not in text
        assert "SHARE_MAP = 365" in text
        assert "已移除" in capsys.readouterr().out

    def test_unset_invalid_key(self, isolated_env, capsys) -> None:
        rc = cmd_config(_make_args("unset", "NOPE"))
        assert rc == 1
        assert "不支持的键" in capsys.readouterr().err
