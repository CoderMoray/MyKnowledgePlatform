"""Shared fixtures for storage/git tests."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from backend.config import identity_file
from backend.storage import Storage


@pytest.fixture(autouse=True)
def _test_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set a dummy identity for every test.

    Stored outside all test ``tmp_path`` dirs so it doesn't interfere
    with git state or KB init.
    """
    import yaml, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="mkn_identity_"))
    cfg = tmp / "config.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {"identity": {"email": "test@example.com", "nickname": "TestUser"}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("backend.config.identity_file", lambda: cfg)


@pytest.fixture
def tmp_kb_root() -> Iterator[Path]:
    """Create a temporary directory as the knowledge base root.

    Yields the path; cleans up after test.
    """
    tmp = Path(tempfile.mkdtemp(prefix="myknowledge_test_"))
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def storage(tmp_kb_root: Path) -> Storage:
    """A Storage instance pointing at the temporary KB root."""
    return Storage(kb_root=tmp_kb_root)


@pytest.fixture
def env_file(tmp_kb_root: Path) -> Path:
    """Create a minimal .env file in the KB root."""
    env = tmp_kb_root / ".env"
    env.write_text(
        "OSS_BUCKET=my-test-bucket\n"
        "OSS_ENDPOINT=oss-cn-test.aliyuncs.com\n"
        "OSS_ACCESS_KEY_ID=LTAI_test\n"
        "OSS_ACCESS_KEY_SECRET=secret_test\n",
        encoding="utf-8",
    )
    return env
