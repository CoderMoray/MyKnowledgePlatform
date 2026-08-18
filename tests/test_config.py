"""Tests for backend/config.py."""

from pathlib import Path

import pytest

from backend.config import (
    resolve_root,
    load_oss_env,
    backend_env_file,
    user_env_file,
    effective_env_file,
    share_env_source,
    load_share_env,
    write_share_env,
    unset_share_env,
    mask_share_code,
    SHARE_KEYS,
)


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Point backend/.env + ~/.myknowledge/.env at temp paths (no real writes)."""
    b_env = tmp_path / "backend" / ".env"
    u_env = tmp_path / "home" / ".myknowledge" / ".env"
    monkeypatch.setattr("backend.config.backend_env_file", lambda: b_env)
    monkeypatch.setattr("backend.config.user_env_file", lambda: u_env)
    return b_env, u_env


class TestResolveRoot:
    def test_default_is_home_dot_myknowledge(self) -> None:
        root = resolve_root()
        assert root == (Path.home() / ".myknowledge").resolve()

    def test_custom_root(self) -> None:
        root = resolve_root("/tmp/my_kb")
        assert root == Path("/tmp/my_kb").resolve()

    def test_custom_root_resolves_tilde(self) -> None:
        root = resolve_root("~/custom_kb")
        assert root == (Path.home() / "custom_kb").resolve()


class TestLoadOssEnv:
    def test_no_env_file_returns_empty(self) -> None:
        cfg = load_oss_env(Path("/nonexistent/path"))
        assert cfg == {"bucket": "", "endpoint": "", "access_key_id": "",
                       "access_key_secret": "", "region": "",
                       "share_code": "", "share_map": ""}

    def test_reads_all_keys(self, env_file: Path) -> None:
        cfg = load_oss_env(env_file)
        assert cfg["bucket"] == "my-test-bucket"
        assert cfg["endpoint"] == "oss-cn-test.aliyuncs.com"
        assert cfg["access_key_id"] == "LTAI_test"
        assert cfg["access_key_secret"] == "secret_test"

    def test_unknown_keys_ignored(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text(
            "OSS_BUCKET=my-bucket\n"
            "UNKNOWN_KEY=should_be_ignored\n"
            "OSS_ENDPOINT=my-endpoint\n",
        )
        cfg = load_oss_env(env)
        assert cfg["bucket"] == "my-bucket"
        assert cfg["endpoint"] == "my-endpoint"

    def test_comments_and_blanks_skipped(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text(
            "# this is a comment\n"
            "\n"
            "OSS_BUCKET=my-bucket\n"
        )
        cfg = load_oss_env(env)
        assert cfg["bucket"] == "my-bucket"

    def test_quotes_stripped(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text(
            'OSS_BUCKET="my-bucket"\n'
            "OSS_ENDPOINT='my-endpoint'\n"
        )
        cfg = load_oss_env(env)
        assert cfg["bucket"] == "my-bucket"
        assert cfg["endpoint"] == "my-endpoint"


class TestShareEnvPriority:
    """backend/.env → ~/.myknowledge/.env → none read priority."""

    def test_backend_wins_over_user(self, isolated_env) -> None:
        b_env, u_env = isolated_env
        b_env.parent.mkdir(parents=True, exist_ok=True)
        u_env.parent.mkdir(parents=True, exist_ok=True)
        b_env.write_text("KNOWLEDGE_SHARE_CODE = back\nSHARE_MAP = 111\n")
        u_env.write_text("KNOWLEDGE_SHARE_CODE = user\nSHARE_MAP = 222\n")
        path, source = effective_env_file()
        assert source == "backend"
        assert path == b_env
        env = load_share_env()
        assert env["share_code"] == "back"
        assert env["share_map"] == "111"
        assert share_env_source() == "backend"

    def test_user_fallback_when_no_backend(self, isolated_env) -> None:
        b_env, u_env = isolated_env
        u_env.parent.mkdir(parents=True, exist_ok=True)
        u_env.write_text("KNOWLEDGE_SHARE_CODE = user\nSHARE_MAP = 222\n")
        path, source = effective_env_file()
        assert source == "myknowledge"
        assert path == u_env
        assert load_share_env()["share_code"] == "user"

    def test_none_when_no_file(self, isolated_env) -> None:
        _, u_env = isolated_env
        path, source = effective_env_file()
        assert source == "none"
        assert path == u_env  # fallback target = user file
        env = load_share_env()
        assert env["share_code"] == ""
        assert env["share_map"] == "000"  # default


class TestShareEnvWrite:
    """config set/unset write to ~/.myknowledge/.env."""

    def test_set_creates_file_with_template(self, isolated_env) -> None:
        _, u_env = isolated_env
        write_share_env("KNOWLEDGE_SHARE_CODE", "Apple Mono Retail")
        assert u_env.is_file()
        text = u_env.read_text(encoding="utf-8")
        assert "MyKnowledge 分享配置" in text  # template comment
        assert "KNOWLEDGE_SHARE_CODE = Apple Mono Retail" in text

    def test_set_updates_existing_key_in_place(self, isolated_env) -> None:
        _, u_env = isolated_env
        u_env.parent.mkdir(parents=True, exist_ok=True)
        u_env.write_text("# comment\nKNOWLEDGE_SHARE_CODE = old\nSHARE_MAP = 365\n")
        write_share_env("KNOWLEDGE_SHARE_CODE", "new-code")
        text = u_env.read_text(encoding="utf-8")
        assert "# comment" in text  # unrelated line preserved
        assert "SHARE_MAP = 365" in text
        assert "KNOWLEDGE_SHARE_CODE = new-code" in text
        assert "KNOWLEDGE_SHARE_CODE = old" not in text

    def test_set_appends_when_key_missing(self, isolated_env) -> None:
        _, u_env = isolated_env
        u_env.parent.mkdir(parents=True, exist_ok=True)
        u_env.write_text("SHARE_MAP = 365\n")
        write_share_env("KNOWLEDGE_SHARE_CODE", "code")
        text = u_env.read_text(encoding="utf-8")
        assert "SHARE_MAP = 365" in text
        assert "KNOWLEDGE_SHARE_CODE = code" in text

    def test_set_invalid_key_raises(self, isolated_env) -> None:
        with pytest.raises(ValueError, match="不支持的分享配置键"):
            write_share_env("OSS_BUCKET", "x")

    def test_unset_removes_key(self, isolated_env) -> None:
        _, u_env = isolated_env
        u_env.parent.mkdir(parents=True, exist_ok=True)
        u_env.write_text("KNOWLEDGE_SHARE_CODE = a\nSHARE_MAP = 365\n")
        unset_share_env("KNOWLEDGE_SHARE_CODE")
        text = u_env.read_text(encoding="utf-8")
        assert "KNOWLEDGE_SHARE_CODE" not in text
        assert "SHARE_MAP = 365" in text

    def test_unset_missing_file_idempotent(self, isolated_env) -> None:
        unset_share_env("SHARE_MAP")  # no file → no error
        unset_share_env("SHARE_MAP")  # still fine


class TestMaskShareCode:
    def test_empty(self) -> None:
        assert mask_share_code("") == "(未设置)"

    def test_short_collapses(self) -> None:
        assert mask_share_code("ab") == "****"

    def test_masks_middle(self) -> None:
        assert mask_share_code("Apple Mono Retail") == "Ap***il"
