"""Tests for the grouped friendly help (like ``git``)."""

from __future__ import annotations

import argparse
import pytest

from backend.cli import main, build_parser, _GROUPS, _CMD_HELP


class TestGroupedHelp:
    def test_no_args_prints_grouped_help_exit0(self, capsys) -> None:
        rc = main([])
        out = capsys.readouterr().out
        assert rc == 0
        assert "用法: myknowledge <command>" in out
        # every group heading present
        for group, _ in _GROUPS:
            assert f"{group}:" in out

    def test_no_args_none_defaults_exit0(self, capsys) -> None:
        """main() with no argv (sys.argv[1:] empty) → grouped help, exit 0."""
        import backend.cli as cli
        old_argv = cli.sys.argv
        cli.sys.argv = ["myknowledge"]
        try:
            rc = main()
            out = capsys.readouterr().out
            assert rc == 0
            assert "用法: myknowledge <command>" in out
        finally:
            cli.sys.argv = old_argv

    def test_help_flag_prints_grouped_help(self, capsys) -> None:
        for flag in ("-h", "--help"):
            rc = main([flag])
            out = capsys.readouterr().out
            assert rc == 0
            assert "用法: myknowledge <command>" in out

    def test_all_commands_listed(self, capsys) -> None:
        main([])
        out = capsys.readouterr().out
        for cmd in _CMD_HELP:
            assert cmd in out
            assert _CMD_HELP[cmd] in out  # description reused

    def test_subcommand_help_normal(self, capsys) -> None:
        """<cmd> -h still shows the subcommand's own argparse help."""
        parser = build_parser()
        for argv in (["config", "-h"], ["doctor", "-h"], ["init", "-h"]):
            capsys.readouterr()  # clear
            with pytest.raises(SystemExit) as e:
                parser.parse_args(argv)
            assert e.value.code == 0
            out = capsys.readouterr().out
            assert f"usage: myknowledge {argv[0]}" in out

    def test_main_subcommand_help(self, capsys) -> None:
        """main(['doctor', '-h']) shows doctor's own argparse help."""
        with pytest.raises(SystemExit) as e:
            main(["doctor", "-h"])
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "usage: myknowledge doctor" in out
        assert "用法: myknowledge <command>" not in out

    def test_groups_cover_all_commands(self) -> None:
        """Every registered command appears in exactly one group."""
        grouped = [c for _, cmds in _GROUPS for c in cmds]
        assert sorted(grouped) == sorted(_CMD_HELP)
        assert len(grouped) == len(set(grouped))  # no duplicates


class TestConfigGroupedHelp:
    """config 子命令复用分组帮助风格（config -h / --help → 子表单清单）。"""

    def test_config_help_flag_shows_grouped(self, capsys) -> None:
        for flag in ("-h", "--help"):
            rc = main(["config", flag])
            out = capsys.readouterr().out
            assert rc == 0
            assert "用法: myknowledge config <action>" in out
            for action in ("show", "set", "unset"):
                assert action in out
            # not the top-level grouped help
            assert "用法: myknowledge <command>" not in out

    def test_config_no_action_still_show(self, capsys) -> None:
        """config 无 action 仍显示分享配置（backward-compatible default=show）。"""
        # 无 action → 走 cmd_config → show（不显示分组帮助）
        rc = main(["config"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "用法: myknowledge config <action>" not in out  # 不是帮助
        assert "分享配置" in out  # 实际是 show 输出

    def test_config_show_still_works(self, capsys) -> None:
        rc = main(["config", "show"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "分享配置" in out
