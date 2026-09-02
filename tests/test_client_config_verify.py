"""验收测试：MVP AI 平台 MCP / Hooks / Agent 配置写入 + 设置页开关双向联动。

覆盖平台：**ClaudeCode** + **CodeBuddyIDE**（``backend/client_config.py`` 注释里
写明的 MVP 两平台，共用同一套 ``configureClient`` 增量合并逻辑，仅落盘目录不同：
Claude Code → ``~/.claude*``；CodeBuddy IDE → ``~/.codebuddy*``）。
WorkBuddy（代码标 not built）/ Cursor / ClaudeDesktop / Enchante 本模块不覆盖。

配套测试方案文档：``docs/test-plan-claude-code-config.md``。

本模块是**纯本地后端验证**——不需要真的把 Claude Code / CodeBuddy IDE 跑起来
（国内网络下它们本就无法联网）。要验的是：
  1. 初始化写入后，两平台各自的三类配置文件内容正确；
  2. 设置页开关调用的 API（``POST`` / ``DELETE /api/client-config/<platform>/<kind>``）
     能正确写入 / 移除 / 恢复配置；
  3. 三个开关互相独立，互不串扰。

设置页开关的「开 / 关」视觉态直接来自 ``store.clientStatus(platform, kind)``，
其值 = 后端 ``GET /api/client-config`` 的 ``detect_platform`` 结果。因此
「开关状态 ↔ 配置文件」一致性 == 「``detect_platform`` 是否如实反映
``write_kind`` / ``remove_kind`` 对配置文件的改动」——本模块正是逐条核验这一点，
既走 ``client_config`` 函数层，也走前端真正调用的 HTTP 路由层（``TestClient``）。

所有测试 monkeypatch ``Path.home()`` 到临时目录，绝不触碰真实
``~/.claude`` / ``~/.claude.json`` / ``~/.codebuddy``。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.client_config import (
    _hooks_cmd_for,
    _matcher_is_mine,
    _platform_paths,
    detect_platform,
    remove_kind,
    write_kind,
)

KINDS = ("mcp", "hooks", "agent")

# 每个 MVP 平台的落盘位置与内容特征（AiClientConfig/platforms.json，macOS）。
#   mcp   → <mcp_file>            键 mcpServers.MyKnowledge
#   hooks → <hooks_file>          键 hooks.PreToolUse[]（matcher 由平台决定）
#   agent → <agents_dir>/MyKnowledge-agent.md   （frontmatter + 正文的 md 文件）
SPECS = {
    "ClaudeCode": {
        "mcp_file": "~/.claude.json",
        "hooks_file": "~/.claude/settings.json",
        "agents_dir": "~/.claude/agents",
        "hook_matcher": "Bash|Write|Edit",
        # ClaudeCode hook = curl 读 stdin（-d @-）打 /hooks/pre-tool-use
        "hook_cmd_check": lambda c: c.startswith("curl -s -X POST") and c.endswith("-d @-"),
        "agent_frontmatter_keys": ("name:", "description:", "tools:", "model:"),
    },
    "CodeBuddyIDE": {
        "mcp_file": "~/.codebuddy/mcp.json",
        "hooks_file": "~/.codebuddy/settings.json",
        "agents_dir": "~/.codebuddy/agents",
        "hook_matcher": "*",
        # CodeBuddyIDE hook = hooks_forward 转发脚本（dev: python3 -m backend.hooks_forward；
        # frozen: "<二进制>" --hooks-forward）——两种形态都含 hooks_forward / --hooks-forward
        "hook_cmd_check": lambda c: ("hooks_forward" in c) or ("--hooks-forward" in c),
        # CodeBuddy agent 额外带 agentMode/enabled/enabledAutoRun/mcpServers frontmatter
        "agent_frontmatter_keys": ("name:", "description:", "tools:", "model:",
                                   "agentMode:", "enabled:", "mcpServers:"),
    },
}
MVP_PLATFORMS = tuple(SPECS)


# ──────────────────────────────────────────────────────────────────────────
#  fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(params=MVP_PLATFORMS)
def platform(request) -> str:
    """参数化：ClaudeCode / CodeBuddyIDE，两平台跑同一套检验。"""
    return request.param


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把 ``Path.home()`` 指到临时目录，隔离真实用户配置。返回该目录。"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def client(fake_home: Path) -> TestClient:
    """FastAPI TestClient —— 打前端真正调用的 HTTP 路由。"""
    from backend.main import app
    return TestClient(app)


def mcp_file(platform: str) -> Path:
    return _platform_paths(platform)["mcp_file"]


def hooks_file(platform: str) -> Path:
    return _platform_paths(platform)["hooks_file"]


def agent_file(platform: str) -> Path:
    return _platform_paths(platform)["agents_dir"] / "MyKnowledge-agent.md"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def mcp_has_myknowledge(platform: str) -> bool:
    return "MyKnowledge" in (read_json(mcp_file(platform)).get("mcpServers") or {})


def hooks_has_myknowledge(platform: str) -> bool:
    """与 detect_platform 同源：按 command 签名识别我们的 matcher。"""
    cmd = _hooks_cmd_for(platform)
    pre = (read_json(hooks_file(platform)).get("hooks") or {}).get("PreToolUse") or []
    return any(_matcher_is_mine(m, cmd) for m in pre)


def file_state(platform: str) -> dict:
    """当前磁盘上三类配置各自是否存在 MyKnowledge 条目。"""
    return {
        "mcp": mcp_has_myknowledge(platform),
        "hooks": hooks_has_myknowledge(platform),
        "agent": agent_file(platform).exists(),
    }


def detect_state(platform: str) -> dict:
    d = detect_platform(platform)
    return {k: d[k] for k in KINDS}


def api_switch_state(client: TestClient, platform: str) -> dict:
    st = client.get("/api/client-config").json()[platform]
    return {k: st[k] for k in KINDS}


def init_all_via_api(client: TestClient, platform: str) -> None:
    for kind in KINDS:
        r = client.post(f"/api/client-config/{platform}/{kind}")
        assert r.status_code == 200, r.text


# ══════════════════════════════════════════════════════════════════════════
#  检验一：初始化后 —— 三种配置都已写入；设置页三个开关都应显示为「开」
# ══════════════════════════════════════════════════════════════════════════


class TestCheck1_InitializedState:
    def test_init_writes_all_three_config_files(self, fake_home: Path, platform: str) -> None:
        for kind in KINDS:
            res = write_kind(platform, kind)
            assert res["status"] in ("written", "exists"), res
        assert file_state(platform) == {"mcp": True, "hooks": True, "agent": True}

    def test_mcp_file_content_correct(self, fake_home: Path, platform: str) -> None:
        write_kind(platform, "mcp")
        data = read_json(mcp_file(platform))
        srv = data["mcpServers"]["MyKnowledge"]
        assert srv["type"] == "stdio"
        assert srv["args"] == ["-m", "backend.cli", "mcp"]  # 非 frozen 开发路径
        assert "python" in srv["command"]
        assert srv["env"]["MYKNOWLEDGE_CLIENT"] == platform
        assert "MYKNOWLEDGE_ROOT" in srv["env"]
        # 落盘到该平台约定的文件
        assert str(mcp_file(platform)).endswith(SPECS[platform]["mcp_file"].lstrip("~"))

    def test_hooks_file_content_correct(self, fake_home: Path, platform: str) -> None:
        write_kind(platform, "hooks")
        spec = SPECS[platform]
        pre = read_json(hooks_file(platform))["hooks"]["PreToolUse"]
        cmd = _hooks_cmd_for(platform)
        mine = [m for m in pre if _matcher_is_mine(m, cmd)]
        assert len(mine) == 1, pre
        assert mine[0]["matcher"] == spec["hook_matcher"]
        hook_cmd = mine[0]["hooks"][0]["command"]
        assert spec["hook_cmd_check"](hook_cmd), hook_cmd
        assert str(hooks_file(platform)).endswith(spec["hooks_file"].lstrip("~"))

    def test_agent_file_content_correct(self, fake_home: Path, platform: str) -> None:
        write_kind(platform, "agent")
        text = agent_file(platform).read_text(encoding="utf-8")
        assert text.startswith("---\n")  # YAML frontmatter
        assert "name: MyKnowledge" in text
        assert "# MyKnowledge Agent" in text
        for key in SPECS[platform]["agent_frontmatter_keys"]:
            assert key in text, f"{platform} agent frontmatter 缺 {key}"

    def test_detect_reports_all_on_after_init(self, fake_home: Path, platform: str) -> None:
        for kind in KINDS:
            write_kind(platform, kind)
        assert detect_state(platform) == {"mcp": True, "hooks": True, "agent": True}

    def test_switch_state_matches_files_after_init(
        self, client: TestClient, platform: str
    ) -> None:
        """设置页开关状态（= GET /api/client-config）↔ 磁盘配置文件，两者一致且都为「开」。"""
        init_all_via_api(client, platform)
        assert api_switch_state(client, platform) == {"mcp": True, "hooks": True, "agent": True}
        assert file_state(platform) == {"mcp": True, "hooks": True, "agent": True}


# ══════════════════════════════════════════════════════════════════════════
#  检验二：关掉某开关 —— 配置文件对应项被「移除」（不是保留停用）；开关显示为「关」
# ══════════════════════════════════════════════════════════════════════════


class TestCheck2_ToggleOff:
    @pytest.mark.parametrize("kind", KINDS)
    def test_toggle_off_removes_from_config_and_switch(
        self, client: TestClient, platform: str, kind: str
    ) -> None:
        init_all_via_api(client, platform)
        r = client.delete(f"/api/client-config/{platform}/{kind}")
        assert r.status_code == 200
        assert r.json()["status"] == "removed"

        assert file_state(platform)[kind] is False           # 配置文件层：条目消失
        assert api_switch_state(client, platform)[kind] is False  # 开关层：False

    def test_off_is_removal_not_disabled_flag(self, fake_home: Path, platform: str) -> None:
        """「关」= 物理删除条目，而非写一个 enabled:false 之类的停用标记。"""
        write_kind(platform, "mcp")
        remove_kind(platform, "mcp")
        servers = read_json(mcp_file(platform)).get("mcpServers", {})
        assert "MyKnowledge" not in servers
        assert servers == {}  # 没有残留的停用形态

        write_kind(platform, "hooks")
        remove_kind(platform, "hooks")
        pre = (read_json(hooks_file(platform)).get("hooks") or {}).get("PreToolUse")
        assert pre == []  # matcher 被移除，不是标记停用

        write_kind(platform, "agent")
        remove_kind(platform, "agent")
        assert not agent_file(platform).exists()  # 文件被删除

    def test_toggle_off_preserves_user_other_config(
        self, fake_home: Path, platform: str
    ) -> None:
        """关开关只动 MyKnowledge 条目——用户自己的 mcpServers / hooks / 设置项保留。"""
        write_kind(platform, "mcp")
        data = read_json(mcp_file(platform))
        data["mcpServers"]["RAPID"] = {"type": "stdio", "command": "rapid"}
        data["someUserSetting"] = 42
        mcp_file(platform).write_text(json.dumps(data), encoding="utf-8")

        write_kind(platform, "hooks")
        h = read_json(hooks_file(platform))
        h["hooks"]["PreToolUse"].append(
            {"matcher": "Foo", "hooks": [{"type": "command", "command": "user-own-hook"}]})
        h["hooks"]["PostToolUse"] = [
            {"matcher": "*", "hooks": [{"type": "command", "command": "user-post"}]}]
        hooks_file(platform).write_text(json.dumps(h), encoding="utf-8")

        remove_kind(platform, "mcp")
        remove_kind(platform, "hooks")

        mcp_data = read_json(mcp_file(platform))
        assert "RAPID" in mcp_data["mcpServers"] and "MyKnowledge" not in mcp_data["mcpServers"]
        assert mcp_data["someUserSetting"] == 42

        h2 = read_json(hooks_file(platform))
        pre_cmds = [x["hooks"][0]["command"] for x in h2["hooks"]["PreToolUse"]]
        assert pre_cmds == ["user-own-hook"]
        assert "PostToolUse" in h2["hooks"]

    def test_toggle_off_idempotent(self, client: TestClient, platform: str) -> None:
        init_all_via_api(client, platform)
        for _ in range(3):
            r = client.delete(f"/api/client-config/{platform}/mcp")
            assert r.status_code == 200 and r.json()["status"] == "removed"
        assert api_switch_state(client, platform)["mcp"] is False


# ══════════════════════════════════════════════════════════════════════════
#  检验三：再次打开 —— 配置文件对应项恢复写入；开关显示为「开」
# ══════════════════════════════════════════════════════════════════════════


class TestCheck3_ToggleBackOn:
    @pytest.mark.parametrize("kind", KINDS)
    def test_off_then_on_restores_config_and_switch(
        self, client: TestClient, platform: str, kind: str
    ) -> None:
        init_all_via_api(client, platform)
        client.delete(f"/api/client-config/{platform}/{kind}")
        assert file_state(platform)[kind] is False

        r = client.post(f"/api/client-config/{platform}/{kind}")
        assert r.status_code == 200
        assert r.json()["status"] in ("written", "exists")

        assert file_state(platform)[kind] is True
        assert api_switch_state(client, platform)[kind] is True

    def test_restored_content_equivalent_to_original(
        self, fake_home: Path, platform: str
    ) -> None:
        """恢复写入的内容与初次写入逐字段等价（不是残缺/损坏的条目）。"""
        write_kind(platform, "mcp")
        first = read_json(mcp_file(platform))["mcpServers"]["MyKnowledge"]
        remove_kind(platform, "mcp")
        write_kind(platform, "mcp")
        assert read_json(mcp_file(platform))["mcpServers"]["MyKnowledge"] == first

        write_kind(platform, "hooks")
        h1 = read_json(hooks_file(platform))["hooks"]["PreToolUse"]
        remove_kind(platform, "hooks")
        write_kind(platform, "hooks")
        assert read_json(hooks_file(platform))["hooks"]["PreToolUse"] == h1

        write_kind(platform, "agent")
        a1 = agent_file(platform).read_text(encoding="utf-8")
        remove_kind(platform, "agent")
        write_kind(platform, "agent")
        assert agent_file(platform).read_text(encoding="utf-8") == a1

    def test_multiple_off_on_cycles_stable(self, client: TestClient, platform: str) -> None:
        init_all_via_api(client, platform)
        for _ in range(3):
            for kind in KINDS:
                client.delete(f"/api/client-config/{platform}/{kind}")
            assert file_state(platform) == {"mcp": False, "hooks": False, "agent": False}
            for kind in KINDS:
                client.post(f"/api/client-config/{platform}/{kind}")
            assert file_state(platform) == {"mcp": True, "hooks": True, "agent": True}


# ══════════════════════════════════════════════════════════════════════════
#  补充：三个开关各自独立、互不影响
# ══════════════════════════════════════════════════════════════════════════


class TestCheck4_SwitchIndependence:
    @pytest.mark.parametrize("toggled", KINDS)
    def test_toggling_one_off_does_not_touch_others(
        self, client: TestClient, platform: str, toggled: str
    ) -> None:
        init_all_via_api(client, platform)
        others = [k for k in KINDS if k != toggled]

        client.delete(f"/api/client-config/{platform}/{toggled}")
        state = api_switch_state(client, platform)
        assert state[toggled] is False
        for o in others:
            assert state[o] is True, f"关 {toggled} 影响了 {o}"
            assert file_state(platform)[o] is True

    @pytest.mark.parametrize("toggled", KINDS)
    def test_toggling_one_back_on_does_not_touch_others(
        self, client: TestClient, platform: str, toggled: str
    ) -> None:
        init_all_via_api(client, platform)
        others = [k for k in KINDS if k != toggled]
        for o in others:
            client.delete(f"/api/client-config/{platform}/{o}")
        client.delete(f"/api/client-config/{platform}/{toggled}")

        client.post(f"/api/client-config/{platform}/{toggled}")
        state = api_switch_state(client, platform)
        assert state[toggled] is True
        for o in others:
            assert state[o] is False, f"开 {toggled} 顺带打开了 {o}"

    def test_mcp_hooks_agent_use_distinct_files(self, fake_home: Path, platform: str) -> None:
        """三类配置落在三个不同文件——天然隔离，不存在「改一个动另一个」。"""
        p = _platform_paths(platform)
        assert len({str(p["mcp_file"]), str(p["hooks_file"]),
                    str(p["agents_dir"] / "MyKnowledge-agent.md")}) == 3

    def test_independent_state_matrix(self, client: TestClient, platform: str) -> None:
        """8 种开/关组合逐一核验：设置页开关矩阵 ↔ 配置文件矩阵完全一致。"""
        init_all_via_api(client, platform)
        for bits in range(8):
            want = {"mcp": bool(bits & 1), "hooks": bool(bits & 2), "agent": bool(bits & 4)}
            for kind, on in want.items():
                if on:
                    client.post(f"/api/client-config/{platform}/{kind}")
                else:
                    client.delete(f"/api/client-config/{platform}/{kind}")
            assert api_switch_state(client, platform) == want
            assert file_state(platform) == want


# ══════════════════════════════════════════════════════════════════════════
#  两平台互不干扰（同一 home 下 ClaudeCode 与 CodeBuddyIDE 配置各写各的）
# ══════════════════════════════════════════════════════════════════════════


class TestCrossPlatformIsolation:
    def test_claudecode_and_codebuddy_independent(self, client: TestClient) -> None:
        init_all_via_api(client, "ClaudeCode")
        init_all_via_api(client, "CodeBuddyIDE")

        # 关掉 ClaudeCode 全部，CodeBuddyIDE 不受影响
        for kind in KINDS:
            client.delete(f"/api/client-config/ClaudeCode/{kind}")
        assert api_switch_state(client, "ClaudeCode") == {"mcp": False, "hooks": False, "agent": False}
        assert api_switch_state(client, "CodeBuddyIDE") == {"mcp": True, "hooks": True, "agent": True}
        assert file_state("CodeBuddyIDE") == {"mcp": True, "hooks": True, "agent": True}

    def test_mcp_files_are_separate_paths(self, fake_home: Path) -> None:
        assert mcp_file("ClaudeCode") != mcp_file("CodeBuddyIDE")
        assert hooks_file("ClaudeCode") != hooks_file("CodeBuddyIDE")


# ══════════════════════════════════════════════════════════════════════════
#  初始化引导（rerunGuide → guideExecute）回归：不能把已配置项误删 / 一个都写不进
#  —— 见 docs/test-plan-claude-code-config.md「发现的问题」#1、#2
# ══════════════════════════════════════════════════════════════════════════


class TestGuideExecuteContract:
    """``store.guideExecute()`` 对后端的调用契约（前端 bug 的后端侧护栏，两平台都盯）。"""

    def test_object_like_kind_is_rejected(self, client: TestClient, platform: str) -> None:
        r = client.post(f"/api/client-config/{platform}/%5Bobject%20Object%5D")
        assert r.status_code == 400

    def test_reinit_keeps_config_on(self, client: TestClient, platform: str) -> None:
        """已配置平台再跑一次初始化（POST 幂等）——配置仍在，不被关闭。"""
        init_all_via_api(client, platform)
        init_all_via_api(client, platform)  # 第二次「初始化」
        assert file_state(platform) == {"mcp": True, "hooks": True, "agent": True}
        assert api_switch_state(client, platform) == {"mcp": True, "hooks": True, "agent": True}
