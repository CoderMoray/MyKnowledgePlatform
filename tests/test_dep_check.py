"""Tests for dependency checking (git, Python packages)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.cli import _check_git, _check_python_deps


class TestCheckGit:
    def test_git_available(self) -> None:
        assert _check_git() is None

    @patch("subprocess.run")
    def test_git_not_found(self, mock_run) -> None:
        mock_run.side_effect = FileNotFoundError()
        err = _check_git()
        assert err is not None
        assert "未安装" in err

    @patch("subprocess.run")
    def test_git_other_error(self, mock_run) -> None:
        mock_run.side_effect = PermissionError()
        err = _check_git()
        assert err is not None


class TestCheckPythonDeps:
    def test_all_available(self) -> None:
        hints = _check_python_deps()
        assert hints == []

    @patch("builtins.__import__")
    def test_yaml_missing(self, mock_import) -> None:
        def _import(name, *a, **kw):
            if name == "yaml":
                raise ImportError("no yaml")
            return object()  # any real import
        mock_import.side_effect = _import

        hints = _check_python_deps()
        assert len(hints) == 1
        assert "pyyaml" in hints[0]

    @patch("builtins.__import__")
    def test_mcp_missing(self, mock_import) -> None:
        def _import(name, *a, **kw):
            if name == "mcp":
                raise ImportError("no mcp")
            return object()
        mock_import.side_effect = _import

        hints = _check_python_deps()
        assert len(hints) == 1
        assert "mcp" in hints[0]

    @patch("builtins.__import__")
    def test_multiple_missing(self, mock_import) -> None:
        def _import(name, *a, **kw):
            if name in ("yaml", "mcp"):
                raise ImportError(f"no {name}")
            return object()
        mock_import.side_effect = _import

        hints = _check_python_deps()
        assert len(hints) == 2

    @patch("builtins.__import__")
    def test_mirror_included(self, mock_import) -> None:
        def _import(name, *a, **kw):
            if name == "yaml":
                raise ImportError("no yaml")
            return object()
        mock_import.side_effect = _import

        hints = _check_python_deps(mirror="https://my.mirror/simple")
        assert len(hints) == 1
        assert "-i https://my.mirror/simple" in hints[0]
