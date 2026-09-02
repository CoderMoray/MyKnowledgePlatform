"""验收测试：Claude Code 平台 MCP / Hooks / Agent 配置写入 + 设置页开关双向联动。

配套测试方案文档：``docs/test-plan-claude-code-config.md``。

本模块是**纯本地后端验证**——不需要真的把 Claude Code 跑起来（国内网络下它本就
无法联网）。要验的是：
  1. 初始化写入后，Claude Code 的三类配置文件内容正确；
  2. 设置页开关调用的 API（``POST`` / ``DELETE /api/client-config/<platform>/<kind>``）
     能正确写入 / 移除 / 恢复配置；
  3. 三个开关互相独立，互不串扰。

设置页开关的「开 / 关」视觉态直接来自 ``store.clientStatus(platform, kind)``，
其值 = 后端 ``GET /api/client-config`` 的 ``detect_platform`` 结果。因此
「开关状态 ↔ 配置文件」一致性 == 「``detect_platform`` 是否如实反映
``write_kind`` / ``remove_kind`` 对配置文件的改动」——本模块正是逐条核验这一点，
既走 ``client_config`` 函数层，也走前端真正调用的 HTTP 路由层（``TestClient``）。

所有测试 monkeypatch ``Path.home()`` 到临时目录，绝不触碰真实
``~/.claude`` / ``~/.claude.json``。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.client_config import (
    _platform_paths,
    detect_platform,
    remove_kind,
    write_kind,
)

PLATFORM = "ClaudeCode"
KINDS = ("mcp", "hooks", "agent")

# Claude Code 三类配置的落盘位置（AiClientConfig/platforms.json，macOS）：
#   mcp   → ~/.claude.json           键 mcpServers.MyKnowledge
#   hooks → ~/.claude/settings.json  键 hooks.PreToolUse[] 里 command 为我们的 curl
#   agent → ~/.claude/agents/MyKnowledge-agent.md   （frontmatter + 正文的 md 文件）
HOOK_ENDPOINT_MARK = "/hooks/pre-tool-use"


# ──────────────────────────────────────────────────────────────────────────
#  fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────


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


def cc_paths() -> dict:
    return _platform_paths(PLATFORM)


def mcp_file() -> Path:
    return cc_paths()["mcp_file"]


def hooks_file() -> Path:
    return cc_paths()["hooks_file"]


def agent_file() -> Path:
    return cc_paths()["agents_dir"] / "MyKnowledge-agent.md"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def mcp_has_myknowledge() -> bool:
    return "MyKnowledge" in (read_json(mcp_file()).get("mcpServers") or {})


def hooks_has_myknowledge() -> bool:
    hooks = (read_json(hooks_file()).get("hooks") or {}).get("PreToolUse") or []
    for matcher in hooks:
        for h in matcher.get("hooks", []):
            if HOOK_ENDPOINT_MARK in h.get("command", ""):
                return True
    return False


def agent_present() -> bool:
    return agent_file().exists()


def file_state() -> dict:
    """当前磁盘上三类配置各自是否存在 MyKnowledge 条目。"""
    return {
        "mcp": mcp_has_myknowledge(),
        "hooks": hooks_has_myknowledge(),
        "agent": agent_present(),
    }


def detect_state() -> dict:
    d = detect_platform(PLATFORM)
    return {k: d[k] for k in KINDS}


def init_all_via_api(client: TestClient) -> None:
    for kind in KINDS:
        r = client.post(f"/api/client-config/{PLATFORM}/{kind}")
        assert r.status_code == 200, r.text


# ══════════════════════════════════════════════════════════════════════════
#  检验一：初始化后 —— 三种配置都已写入；设置页三个开关都应显示为「开」
# ══════════════════════════════════════════════════════════════════════════


class TestCheck1_InitializedState:
    def test_init_writes_all_three_config_files(self, fake_home: Path) -> None:
        for kind in KINDS:
            res = write_kind(PLATFORM, kind)
            assert res["status"] in ("written", "exists"), res
        assert file_state() == {"mcp": True, "hooks": True, "agent": True}

    def test_mcp_file_content_correct(self, fake_home: Path) -> None:
        write_kind(PLATFORM, "mcp")
        srv = read_json(mcp_file())["mcpServers"]["MyKnowledge"]
        assert srv["type"] == "stdio"
        assert srv["args"] == ["-m", "backend.cli", "mcp"]  # 非 frozen 开发路径
        assert srv["command"].endswith(("python", "python3")) or "python" in srv["command"]
        assert srv["env"]["MYKNOWLEDGE_CLIENT"] == "ClaudeCode"
        assert "MYKNOWLEDGE_ROOT" in srv["env"]

    def test_hooks_file_content_correct(self, fake_home: Path) -> None:
        write_kind(PLATFORM, "hooks")
        pre = read_json(hooks_file())["hooks"]["PreToolUse"]
        mine = [m for m in pre
                if any(HOOK_ENDPOINT_MARK in h.get("command", "")
                       for h in m.get("hooks", []))]
        assert len(mine) == 1, pre
        assert mine[0]["matcher"] == "Bash|Write|Edit"
        cmd = mine[0]["hooks"][0]["command"]
        assert cmd.startswith("curl -s -X POST") and cmd.endswith("-d @-")

    def test_agent_file_content_correct(self, fake_home: Path) -> None:
        write_kind(PLATFORM, "agent")
        text = agent_file().read_text(encoding="utf-8")
        assert text.startswith("---\n")  # YAML frontmatter
        assert "name: MyKnowledge" in text
        assert "# MyKnowledge Agent" in text

    def test_detect_reports_all_on_after_init(self, fake_home: Path) -> None:
        for kind in KINDS:
            write_kind(PLATFORM, kind)
        assert detect_state() == {"mcp": True, "hooks": True, "agent": True}

    def test_switch_state_matches_files_after_init(self, client: TestClient) -> None:
        """设置页开关状态（= GET /api/client-config）↔ 磁盘配置文件，两者一致且都为「开」。"""
        init_all_via_api(client)
        api_state = client.get("/api/client-config").json()[PLATFORM]
        assert {k: api_state[k] for k in KINDS} == {"mcp": True, "hooks": True, "agent": True}
        assert file_state() == {"mcp": True, "hooks": True, "agent": True}


# ══════════════════════════════════════════════════════════════════════════
#  检验二：关掉某开关 —— 配置文件对应项被「移除」（不是保留停用）；开关显示为「关」
# ══════════════════════════════════════════════════════════════════════════


class TestCheck2_ToggleOff:
    @pytest.mark.parametrize("kind", KINDS)
    def test_toggle_off_removes_from_config_and_switch(
        self, client: TestClient, kind: str
    ) -> None:
        init_all_via_api(client)
        r = client.delete(f"/api/client-config/{PLATFORM}/{kind}")
        assert r.status_code == 200
        assert r.json()["status"] == "removed"

        # 配置文件层：该 kind 的 MyKnowledge 条目确实消失
        assert file_state()[kind] is False
        # 开关层：GET /api/client-config 对应项为 False
        assert client.get("/api/client-config").json()[PLATFORM][kind] is False

    def test_off_is_removal_not_disabled_flag(self, fake_home: Path) -> None:
        """「关」= 物理删除条目，而非写一个 enabled:false 之类的停用标记。"""
        write_kind(PLATFORM, "mcp")
        remove_kind(PLATFORM, "mcp")
        servers = read_json(mcp_file()).get("mcpServers", {})
        assert "MyKnowledge" not in servers  # 键被删除
        assert servers == {}  # 没有残留的停用形态

        write_kind(PLATFORM, "hooks")
        remove_kind(PLATFORM, "hooks")
        pre = (read_json(hooks_file()).get("hooks") or {}).get("PreToolUse")
        assert pre == []  # matcher 被移除，不是标记停用

        write_kind(PLATFORM, "agent")
        remove_kind(PLATFORM, "agent")
        assert not agent_file().exists()  # 文件被删除

    def test_toggle_off_preserves_user_other_config(self, fake_home: Path) -> None:
        """关开关只动 MyKnowledge 条目——用户自己的 mcpServers / hooks / 设置项保留。"""
        write_kind(PLATFORM, "mcp")
        data = read_json(mcp_file())
        data["mcpServers"]["RAPID"] = {"type": "stdio", "command": "rapid"}
        data["someUserSetting"] = 42
        mcp_file().write_text(json.dumps(data), encoding="utf-8")

        write_kind(PLATFORM, "hooks")
        h = read_json(hooks_file())
        h["hooks"]["PreToolUse"].append(
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "user-own-hook"}]})
        h["hooks"]["PostToolUse"] = [
            {"matcher": "*", "hooks": [{"type": "command", "command": "user-post"}]}]
        hooks_file().write_text(json.dumps(h), encoding="utf-8")

        remove_kind(PLATFORM, "mcp")
        remove_kind(PLATFORM, "hooks")

        mcp_data = read_json(mcp_file())
        assert "RAPID" in mcp_data["mcpServers"] and "MyKnowledge" not in mcp_data["mcpServers"]
        assert mcp_data["someUserSetting"] == 42

        h2 = read_json(hooks_file())
        pre_cmds = [x["hooks"][0]["command"] for x in h2["hooks"]["PreToolUse"]]
        assert pre_cmds == ["user-own-hook"]
        assert "PostToolUse" in h2["hooks"]

    def test_toggle_off_idempotent(self, client: TestClient) -> None:
        init_all_via_api(client)
        for _ in range(3):
            r = client.delete(f"/api/client-config/{PLATFORM}/mcp")
            assert r.status_code == 200 and r.json()["status"] == "removed"
        assert client.get("/api/client-config").json()[PLATFORM]["mcp"] is False


# ══════════════════════════════════════════════════════════════════════════
#  检验三：再次打开 —— 配置文件对应项恢复写入；开关显示为「开」
# ══════════════════════════════════════════════════════════════════════════


class TestCheck3_ToggleBackOn:
    @pytest.mark.parametrize("kind", KINDS)
    def test_off_then_on_restores_config_and_switch(
        self, client: TestClient, kind: str
    ) -> None:
        init_all_via_api(client)
        client.delete(f"/api/client-config/{PLATFORM}/{kind}")
        assert file_state()[kind] is False

        r = client.post(f"/api/client-config/{PLATFORM}/{kind}")
        assert r.status_code == 200
        assert r.json()["status"] in ("written", "exists")

        assert file_state()[kind] is True
        assert client.get("/api/client-config").json()[PLATFORM][kind] is True

    def test_restored_content_equivalent_to_original(self, fake_home: Path) -> None:
        """恢复写入的内容与初次写入等价（不是残缺/损坏的条目）。"""
        write_kind(PLATFORM, "mcp")
        first = read_json(mcp_file())["mcpServers"]["MyKnowledge"]
        remove_kind(PLATFORM, "mcp")
        write_kind(PLATFORM, "mcp")
        again = read_json(mcp_file())["mcpServers"]["MyKnowledge"]
        assert again == first

        write_kind(PLATFORM, "hooks")
        h1 = read_json(hooks_file())["hooks"]["PreToolUse"]
        remove_kind(PLATFORM, "hooks")
        write_kind(PLATFORM, "hooks")
        h2 = read_json(hooks_file())["hooks"]["PreToolUse"]
        assert h2 == h1

        write_kind(PLATFORM, "agent")
        a1 = agent_file().read_text(encoding="utf-8")
        remove_kind(PLATFORM, "agent")
        write_kind(PLATFORM, "agent")
        assert agent_file().read_text(encoding="utf-8") == a1

    def test_multiple_off_on_cycles_stable(self, client: TestClient) -> None:
        init_all_via_api(client)
        for _ in range(3):
            for kind in KINDS:
                client.delete(f"/api/client-config/{PLATFORM}/{kind}")
            assert file_state() == {"mcp": False, "hooks": False, "agent": False}
            for kind in KINDS:
                client.post(f"/api/client-config/{PLATFORM}/{kind}")
            assert file_state() == {"mcp": True, "hooks": True, "agent": True}


# ══════════════════════════════════════════════════════════════════════════
#  补充：三个开关各自独立、互不影响
# ══════════════════════════════════════════════════════════════════════════


class TestCheck4_SwitchIndependence:
    @pytest.mark.parametrize("toggled", KINDS)
    def test_toggling_one_off_does_not_touch_others(
        self, client: TestClient, toggled: str
    ) -> None:
        init_all_via_api(client)
        others = [k for k in KINDS if k != toggled]

        client.delete(f"/api/client-config/{PLATFORM}/{toggled}")
        state = client.get("/api/client-config").json()[PLATFORM]
        assert state[toggled] is False
        for o in others:
            assert state[o] is True, f"关 {toggled} 影响了 {o}"
            assert file_state()[o] is True

    @pytest.mark.parametrize("toggled", KINDS)
    def test_toggling_one_back_on_does_not_touch_others(
        self, client: TestClient, toggled: str
    ) -> None:
        init_all_via_api(client)
        others = [k for k in KINDS if k != toggled]
        # 先把 others 关掉，只留 toggled 关→开，验证不会顺带把 others 打开
        for o in others:
            client.delete(f"/api/client-config/{PLATFORM}/{o}")
        client.delete(f"/api/client-config/{PLATFORM}/{toggled}")

        client.post(f"/api/client-config/{PLATFORM}/{toggled}")
        state = client.get("/api/client-config").json()[PLATFORM]
        assert state[toggled] is True
        for o in others:
            assert state[o] is False, f"开 {toggled} 顺带打开了 {o}"

    def test_mcp_hooks_agent_use_distinct_files(self, fake_home: Path) -> None:
        """三类配置落在三个不同文件——天然隔离，不存在「改一个动另一个」。"""
        p = cc_paths()
        assert len({str(p["mcp_file"]), str(p["hooks_file"]),
                    str(p["agents_dir"] / "MyKnowledge-agent.md")}) == 3

    def test_independent_state_matrix(self, client: TestClient) -> None:
        """8 种开/关组合逐一核验：设置页开关矩阵 ↔ 配置文件矩阵完全一致。"""
        init_all_via_api(client)
        for bits in range(8):
            want = {
                "mcp": bool(bits & 1),
                "hooks": bool(bits & 2),
                "agent": bool(bits & 4),
            }
            for kind, on in want.items():
                if on:
                    client.post(f"/api/client-config/{PLATFORM}/{kind}")
                else:
                    client.delete(f"/api/client-config/{PLATFORM}/{kind}")
            api_state = client.get("/api/client-config").json()[PLATFORM]
            assert {k: api_state[k] for k in KINDS} == want
            assert file_state() == want


# ══════════════════════════════════════════════════════════════════════════
#  初始化引导（rerunGuide → guideExecute）回归：不能把已配置项误删 / 一个都写不进
#  —— 见 docs/test-plan-claude-code-config.md「发现的问题」#1、#2
# ══════════════════════════════════════════════════════════════════════════


class TestGuideExecuteContract:
    """``store.guideExecute()`` 对后端的调用契约（前端 bug 的后端侧护栏）。

    前端 bug 详情见测试方案文档；这里从后端角度钉死两条：
      - kind 必须是 mcp/hooks/agent 字符串，``[object Object]`` 之类会被 400 拒绝
        （引导漏取 ``kindMeta.key`` 时的症状）；
      - 对已配置平台重复「初始化」应保持开启（``POST`` 幂等），不应变成关闭。
    """

    def test_object_like_kind_is_rejected(self, client: TestClient) -> None:
        r = client.post(f"/api/client-config/{PLATFORM}/%5Bobject%20Object%5D")
        assert r.status_code == 400

    def test_reinit_keeps_config_on(self, client: TestClient) -> None:
        """已配置平台再跑一次初始化（POST 幂等）——配置仍在，不被关闭。"""
        init_all_via_api(client)
        init_all_via_api(client)  # 第二次「初始化」
        assert file_state() == {"mcp": True, "hooks": True, "agent": True}
        api_state = client.get("/api/client-config").json()[PLATFORM]
        assert {k: api_state[k] for k in KINDS} == {"mcp": True, "hooks": True, "agent": True}
