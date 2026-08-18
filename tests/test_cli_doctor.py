"""Tests for the share-config check in ``myknowledge doctor``."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from backend.cli import cmd_doctor, build_parser


@pytest.fixture
def doctor_env(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Point backend/.env + ~/.myknowledge/.env at temp paths."""
    b_env = tmp_path / "backend" / ".env"
    u_env = tmp_path / "home" / ".myknowledge" / ".env"
    monkeypatch.setattr("backend.config.backend_env_file", lambda: b_env)
    monkeypatch.setattr("backend.config.user_env_file", lambda: u_env)
    return b_env, u_env


def _make_args(root: str) -> argparse.Namespace:
    p = build_parser()
    return p.parse_args(["doctor", "--root", root])


def _run(tmp_path: Path, capsys) -> str:
    args = _make_args(str(tmp_path / "kb"))
    cmd_doctor(args)
    return capsys.readouterr().out


def _share_line(out: str) -> str:
    """Extract the 分享配置 line from doctor output."""
    for line in out.splitlines():
        if "分享配置" in line:
            return line
    raise AssertionError("doctor 输出缺少分享配置检查行")


class TestDoctorShareConfig:
    def test_configured_from_backend(self, tmp_path: Path, capsys,
                                     doctor_env) -> None:
        b_env, _ = doctor_env
        b_env.parent.mkdir(parents=True, exist_ok=True)
        b_env.write_text("KNOWLEDGE_SHARE_CODE = Apple Code\nSHARE_MAP = 365\n")
        out = _run(tmp_path, capsys)
        line = _share_line(out)
        assert "✓" in line  # optional → always ok mark
        assert "backend/.env" in line
        assert "Ap***de" in line  # masked share code
        assert "Apple Code" not in line  # never plaintext
        assert "365" in line
        assert "KNOWLEDGE_SHARE_CODE=" not in out  # no setup hint when configured

    def test_configured_from_user(self, tmp_path: Path, capsys,
                                  doctor_env) -> None:
        _, u_env = doctor_env
        u_env.parent.mkdir(parents=True, exist_ok=True)
        u_env.write_text("KNOWLEDGE_SHARE_CODE = UserKey\nSHARE_MAP = 111\n")
        out = _run(tmp_path, capsys)
        line = _share_line(out)
        assert "~/.myknowledge/.env" in line
        assert "Us***ey" in line

    def test_not_configured_guides_setup(self, tmp_path: Path, capsys,
                                         doctor_env) -> None:
        out = _run(tmp_path, capsys)
        line = _share_line(out)
        assert "未配置" in line
        assert "✓" in line  # optional → non-blocking
        assert "KNOWLEDGE_SHARE_CODE=<鉴权码>" in out  # setup hint
        assert "SHARE_MAP=<三位正整数>" in out
        assert "backend/.env 存在" not in out  # no backend file → no existence hint

    def test_not_configured_backend_exists_shows_hint(self, tmp_path: Path,
                                                      capsys,
                                                      doctor_env) -> None:
        """backend/.env present + not configured → setup guide + backend hint."""
        b_env, _ = doctor_env
        b_env.parent.mkdir(parents=True, exist_ok=True)
        b_env.write_text("OSS_BUCKET=x\n")  # backend/.env exists, no share keys
        out = _run(tmp_path, capsys)
        assert "未配置" in _share_line(out)
        assert "KNOWLEDGE_SHARE_CODE=<鉴权码>" in out  # setup guide
        # backend existence hint explains why user-level config may not take effect
        assert "backend/.env 存在" in out
        assert "可能不生效" in out

    def test_partial_config_shows_not_configured(self, tmp_path: Path,
                                                 capsys, doctor_env) -> None:
        _, u_env = doctor_env
        u_env.parent.mkdir(parents=True, exist_ok=True)
        u_env.write_text("SHARE_MAP = 365\n")  # share_code missing
        out = _run(tmp_path, capsys)
        assert "未配置" in _share_line(out)
        assert "KNOWLEDGE_SHARE_CODE=<鉴权码>" in out
