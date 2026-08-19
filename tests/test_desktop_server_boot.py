"""Tests for desktop_server boot behavior — auto-init + health-check robustness.

Covers two regressions found during 0.7.6 desktop validation:

1. ``desktop_server.main()`` previously started uvicorn without ensuring the
   default KB (``~/.myknowledge``) existed → ``/api/status`` raised
   ``FileNotFoundError`` (missing ``_templates/readme.md``) → 500 → the
   Electron shell's ``waitForBackend`` poll never saw ``res.ok`` → false
   "后端启动超时 30s".  Fix: auto-init the KB before serving.

2. ``api_status`` (health-check) must stay 200 even when the KB is
   uninitialized — the shell only checks ``res.ok`` and a 500 would be
   misreported as a startup timeout.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


class TestDesktopServerAutoInit:
    """desktop_server.main() auto-initializes a missing KB before serving."""

    def test_init_creates_full_kb(self, tmp_path: Path, monkeypatch) -> None:
        """A brand-new root (no templates) gets fully initialized."""
        root = tmp_path / "fresh"
        root.mkdir()

        uvicorn_calls: list = []

        def fake_uvicorn(app, **kwargs):  # noqa: ANN001
            uvicorn_calls.append(kwargs)
            # 模拟 uvicorn 长期阻塞 → 用异常跳出 main()
            raise KeyboardInterrupt

        import backend.desktop_server as ds

        with patch("backend.desktop_server.uvicorn.run", fake_uvicorn):
            with pytest.raises(KeyboardInterrupt):
                ds.main(["--port", "8099", "--root", str(root)])

        # 初始化产物必须齐全
        assert (root / "_templates" / "readme.md").is_file()
        assert (root / "_templates" / "common-knowledge.md").is_file()
        assert (root / "common-knowledge").is_dir()
        assert (root / "projects").is_dir()
        assert (root / "archive").is_dir()
        assert (root / "publish").is_dir()
        assert (root / "project-status.md").is_file()
        assert (root / ".git").is_dir()

    def test_init_does_not_overwrite_existing_templates(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """半初始化 root（有 _templates/readme.md）不会被重复覆盖/重建提交."""
        root = tmp_path / "half"
        (root / "_templates").mkdir(parents=True)
        (root / "_templates" / "readme.md").write_text(
            "# Custom Template", encoding="utf-8"
        )

        import backend.desktop_server as ds

        with patch("backend.desktop_server.uvicorn.run", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                ds.main(["--port", "8099", "--root", str(root)])

        # 已有模板保持原样（不被 _auto_init 覆盖）
        assert (root / "_templates" / "readme.md").read_text(
            encoding="utf-8"
        ) == "# Custom Template"


class TestApiStatusHealthCheck:
    """GET /api/status stays 200 even when the KB is uninitialized.

    NOTE: 直接调用 ``api_status()`` 并显式 ``monkeypatch.get_storage``，不依赖
    TestClient 与全局 app 状态 —— 其它测试文件（如 test_connection.py）会直接
    赋值 ``backend.main.get_storage`` 且不恢复，全量跑时会污染 TestClient 路径。
    """

    def test_status_200_when_kb_missing(self, monkeypatch) -> None:
        """模板缺失 → 健康检查返回 200 + 可读提示（不能 500）。"""
        import backend.main as bm

        def boom():
            raise FileNotFoundError("/x/_templates/readme.md")

        monkeypatch.setattr(bm, "get_storage", boom)

        resp = bm.api_status()
        assert resp.status_code == 200
        assert "尚未初始化" in resp.body.decode("utf-8")

    def test_status_200_after_init(self, tmp_path: Path, monkeypatch) -> None:
        """正常初始化后健康检查返回真实 project-status 内容。"""
        import backend.main as bm
        from backend.readme_generator import ReadmeGenerator
        from backend.storage import Storage

        root = tmp_path / "ok"
        storage = Storage(kb_root=root)
        template = root / "_templates" / "readme.md"
        template.parent.mkdir(parents=True, exist_ok=True)
        shipped = Path(__file__).resolve().parent.parent / "backend" / "templates" / "readme.md"
        template.write_text(shipped.read_text(encoding="utf-8"), encoding="utf-8")
        gen = ReadmeGenerator(storage=storage, template_path=template)

        monkeypatch.setattr(bm, "get_storage", lambda: (storage, gen))

        resp = bm.api_status()
        assert resp.status_code == 200
        assert "# 项目状态" in resp.body.decode("utf-8")
