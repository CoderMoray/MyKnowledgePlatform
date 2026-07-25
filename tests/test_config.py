"""Tests for backend/config.py."""

from pathlib import Path

from backend.config import resolve_root, load_oss_env


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
