"""Tests for backend.desktop_server — the macOS Electron backend launcher.

Covers the ``--mcp`` stdio-server branch (added to let the frozen desktop
binary act as an MCP server for agent clients) plus the existing ``--port`` /
``--hooks-forward`` dispatch.  We never actually bind a socket or start the MCP
loop here — the heavy paths are mocked so the tests only verify argument
parsing and correct routing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import backend.desktop_server as ds


class TestMainDispatch:
    def test_mcp_routes_to_cmd_mcp(self, monkeypatch) -> None:
        """``--mcp`` builds a ``--root`` namespace and calls cli.cmd_mcp.

        The branch must reuse ``cli.cmd_mcp`` (auto-init / identity / GC /
        heartbeat / stdio) rather than reimplementing it, and must not touch the
        webserver path (no uvicorn).
        """
        captured: dict = {}

        def fake_cmd_mcp(ns) -> int:
            captured["root"] = ns.root
            return 7  # sentinel: the branch must return cmd_mcp's value

        monkeypatch.setattr(
            "backend.desktop_server.hooks_forward.main",
            lambda: -1,  # should never be reached in --mcp mode
        )
        import backend.cli as cli
        monkeypatch.setattr(cli, "cmd_mcp", fake_cmd_mcp)
        monkeypatch.setattr(ds, "uvicorn", None, raising=False)

        rc = ds.main(["--mcp", "--root", "/tmp/Some KB"])
        assert rc == 7
        assert captured == {"root": "/tmp/Some KB"}

    def test_mcp_without_root_defaults_none(self, monkeypatch) -> None:
        """``--mcp`` with no ``--root`` passes root=None so resolve_root falls
        through to MYKNOWLEDGE_ROOT env / ~/.myknowledge (matches webserver)."""
        captured: dict = {}

        def fake_cmd_mcp(ns) -> int:
            captured["root"] = ns.root
            return 0

        import backend.cli as cli
        monkeypatch.setattr(cli, "cmd_mcp", fake_cmd_mcp)
        monkeypatch.setattr(ds, "uvicorn", None, raising=False)

        rc = ds.main(["--mcp"])
        assert rc == 0
        assert captured["root"] is None

    def test_mcp_ignores_port(self, monkeypatch) -> None:
        """``--mcp --port 9999``: --mcp wins, port is ignored (stdio, no HTTP)."""
        captured: dict = {}

        def fake_cmd_mcp(ns) -> int:
            captured["root"] = ns.root
            return 0

        import backend.cli as cli
        monkeypatch.setattr(cli, "cmd_mcp", fake_cmd_mcp)
        monkeypatch.setattr(ds, "uvicorn", None, raising=False)

        rc = ds.main(["--mcp", "--port", "9999"])
        assert rc == 0
        assert captured["root"] is None

    def test_mcp_positional_routes_to_cmd_mcp(self, monkeypatch) -> None:
        """Bare positional ``mcp`` (no leading ``--``) also routes to cmd_mcp.

        Some MCP client integrations (e.g. an Enchante config copied from the
        pip-installed ``myknowledge mcp`` docs) spawn the frozen binary with
        ``mcp`` as a plain positional instead of the ``--mcp`` flag — this
        previously hit ``error: unrecognized arguments: mcp`` since the parser
        only defined ``--mcp``. Both forms must work identically.
        """
        captured: dict = {}

        def fake_cmd_mcp(ns) -> int:
            captured["root"] = ns.root
            return 7

        import backend.cli as cli
        monkeypatch.setattr(cli, "cmd_mcp", fake_cmd_mcp)
        monkeypatch.setattr(ds, "uvicorn", None, raising=False)

        rc = ds.main(["mcp", "--root", "/tmp/Some KB"])
        assert rc == 7
        assert captured == {"root": "/tmp/Some KB"}

    def test_unknown_positional_still_rejected(self) -> None:
        """Only ``mcp`` is accepted as a positional — typos still error out."""
        with pytest.raises(SystemExit):
            ds.main(["nonsense"])

    def test_hooks_forward_still_routes(self, monkeypatch) -> None:
        """Existing --hooks-forward branch is untouched by the --mcp addition."""
        monkeypatch.setattr(
            "backend.desktop_server.hooks_forward.main", lambda: 3)
        monkeypatch.setattr(ds, "uvicorn", None, raising=False)
        assert ds.main(["--hooks-forward"]) == 3

    def test_no_flag_goes_webserver(self, monkeypatch, tmp_path: Path) -> None:
        """Default (no --mcp/--hooks-forward) still starts uvicorn on the port."""
        class FakeUvicorn:
            @staticmethod
            def run(app, **kwargs):
                FakeUvicorn.captured = kwargs

        FakeUvicorn.captured = {}
        monkeypatch.setattr(ds, "uvicorn", FakeUvicorn)

        kb = tmp_path / "kb"
        (kb / "_templates").mkdir(parents=True)
        (kb / "_templates" / "readme.md").write_text("# t", encoding="utf-8")

        ds.main(["--port", "8123", "--root", str(kb)])
        assert FakeUvicorn.captured["port"] == 8123
