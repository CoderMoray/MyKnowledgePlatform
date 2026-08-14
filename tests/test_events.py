"""Tests for backend.events — broadcast event typing + version polling."""

from __future__ import annotations

import json
from pathlib import Path

from backend.events import broadcast, poll_event, poll_version, _version_path


# SSE 端点的数据形如 json.dumps(poll_event(kb_root)) = {version, type}。
# /api/events 是永不结束的 SSE 流，直接在测试里迭代流会无限阻塞（无事件时等待），
# 故不在此做端到端流式断言——由 poll_event 返回 {version, type} 的用例（见下方
# TestPollEventReturnsType）保证端点下发的载荷契约。


class TestBroadcastTyping:
    def test_default_event_type_write(self, tmp_kb_root: Path) -> None:
        """broadcast() without a type defaults to 'write' (backward-compatible)."""
        broadcast(tmp_kb_root)
        data = json.loads(_version_path(tmp_kb_root).read_text(encoding="utf-8"))
        assert data["type"] == "write"
        assert isinstance(data["version"], int) and data["version"] > 0

    def test_custom_event_type(self, tmp_kb_root: Path) -> None:
        """broadcast(kb_root, event_type='diagnose') stores {version, type}."""
        broadcast(tmp_kb_root, event_type="diagnose")
        data = json.loads(_version_path(tmp_kb_root).read_text(encoding="utf-8"))
        assert data["type"] == "diagnose"
        assert isinstance(data["version"], int)

    def test_poll_event_returns_type(self, tmp_kb_root: Path) -> None:
        broadcast(tmp_kb_root, event_type="diagnose")
        assert poll_event(tmp_kb_root) == {
            "version": poll_version(tmp_kb_root),
            "type": "diagnose",
        }

    def test_poll_event_empty_when_none(self, tmp_kb_root: Path) -> None:
        assert poll_event(tmp_kb_root) == {}
        assert poll_version(tmp_kb_root) == 0

    def test_version_tracks_and_type_changes(self, tmp_kb_root: Path) -> None:
        """Version (ms timestamp) is monotonically non-decreasing; type reflects the last event."""
        broadcast(tmp_kb_root)
        v1 = poll_version(tmp_kb_root)
        broadcast(tmp_kb_root, event_type="diagnose")
        v2 = poll_version(tmp_kb_root)
        assert v2 >= v1  # ms timestamp may coincide across rapid broadcasts
        assert poll_event(tmp_kb_root).get("type") == "diagnose"


class TestPollVersionCompat:
    def test_poll_version_reads_write_type(self, tmp_kb_root: Path) -> None:
        """poll_version still returns the integer version regardless of type."""
        broadcast(tmp_kb_root)  # default write
        assert poll_version(tmp_kb_root) > 0
        broadcast(tmp_kb_root, event_type="diagnose")
        assert poll_version(tmp_kb_root) > 0
