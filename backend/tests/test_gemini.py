"""Gemini adapter tests.

These pin the two bugs that made Gemini "a mess": duplicate snapshot files
producing repeated sessions, and rich assistant metadata being dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ccsweb.models import ThinkingBlock, ToolUseBlock
from ccsweb.sources.gemini import GeminiAdapter


def _write(root: Path, project: str, name: str, payload: dict) -> Path:
    chats = root / "tmp" / project / "chats"
    chats.mkdir(parents=True, exist_ok=True)
    path = chats / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _session(session_id: str, messages: list[dict], last_updated: str) -> dict:
    return {
        "sessionId": session_id,
        "projectHash": "hash123",
        "startTime": "2026-02-07T17:09:18.325Z",
        "lastUpdated": last_updated,
        "messages": messages,
    }


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / ".gemini"


def test_duplicate_snapshots_collapse_to_newest(root: Path):
    """Two files, one sessionId — the newest snapshot wins, and only one
    session is listed. This is the exact shape that produced a session whose
    entry contained the whole conversation alongside stale copies."""
    stale = [{"id": "1", "type": "user", "content": "hi", "timestamp": None}]
    fresh = stale + [
        {"id": "2", "type": "gemini", "content": "hello", "model": "gemini-3-flash"}
    ]

    _write(root, "p1", "session-2026-02-07T17-08-b776145d.json",
           _session("b776145d", stale, "2026-02-07T17:10:00.000Z"))
    _write(root, "p1", "session-2026-02-07T17-09-b776145d.json",
           _session("b776145d", fresh, "2026-02-08T13:58:48.913Z"))

    sessions = GeminiAdapter(root).list_sessions()

    assert len(sessions) == 1, "duplicate snapshots must collapse to one session"
    assert sessions[0].message_count == 2, "the newest snapshot should win"


def test_assistant_metadata_is_parsed(root: Path):
    """thoughts, tokens, model and toolCalls must all survive."""
    message = {
        "id": "m1",
        "type": "gemini",
        "content": "Here is the analysis.",
        "model": "gemini-3-flash-preview",
        "thoughts": [
            {
                "subject": "Initiating Analysis",
                "description": "Starting the project analysis now.",
                "timestamp": "2026-02-07T17:09:49.488Z",
            }
        ],
        "tokens": {
            "input": 6911,
            "output": 85,
            "cached": 3101,
            "thoughts": 49,
            "tool": 0,
            "total": 7045,
        },
        "toolCalls": [
            {
                "id": "read_file-1",
                "name": "read_file",
                "args": {"file_path": "app/main.py"},
                "result": [
                    {"functionResponse": {"response": {"output": "print('hi')"}}}
                ],
            }
        ],
    }
    _write(root, "p1", "session-a.json",
           _session("sid-a", [{"id": "u", "type": "user", "content": "go"}, message],
                    "2026-02-07T17:10:00.000Z"))

    detail = GeminiAdapter(root).get_session("sid-a")
    assert detail is not None

    assistant = detail.messages[1]
    assert assistant.model == "gemini-3-flash-preview"
    assert assistant.usage is not None
    assert assistant.usage.input_tokens == 6911
    assert assistant.usage.thinking_tokens == 49
    assert assistant.usage.total_tokens == 7045, "matches Gemini's own total"

    thinking = [b for b in assistant.blocks if isinstance(b, ThinkingBlock)]
    assert thinking and thinking[0].subject == "Initiating Analysis"

    tools = [b for b in assistant.blocks if isinstance(b, ToolUseBlock)]
    assert tools and tools[0].detail.category == "file_read"
    assert tools[0].detail.path == "app/main.py"
    assert tools[0].detail.content == "print('hi')"


def test_subagent_tool_output_is_recognised(root: Path):
    """Gemini has no subagent record; it is inferred from the output banner."""
    message = {
        "id": "m1",
        "type": "gemini",
        "content": "done",
        "toolCalls": [
            {
                "id": "ci-1",
                "name": "codebase_investigator",
                "args": {"objective": "Map the modules"},
                "result": [
                    {
                        "functionResponse": {
                            "response": {
                                "output": "Subagent 'codebase_investigator' finished.\n"
                                "Termination Reason: GOAL\nResult:\nIt is an LMS."
                            }
                        }
                    }
                ],
            }
        ],
    }
    _write(root, "p1", "s.json", _session("sid-b", [message], "2026-02-07T18:00:00.000Z"))

    detail = GeminiAdapter(root).get_session("sid-b")
    assert detail is not None
    tool = next(b for b in detail.messages[0].blocks if isinstance(b, ToolUseBlock))
    assert tool.detail.category == "subagent"
    assert tool.detail.agent_type == "codebase_investigator"
    assert tool.detail.result == "It is an LMS."


def test_noise_only_sessions_are_hidden(root: Path):
    """Auth/install chatter is not a conversation."""
    noise = [
        {"id": "1", "type": "info", "content": "Code Assist login required."},
        {"id": "2", "type": "info", "content": "Authentication succeeded"},
    ]
    _write(root, "p1", "noise.json", _session("noise", noise, "2026-02-04T15:36:40.737Z"))

    assert GeminiAdapter(root).list_sessions() == []


def test_missing_root_is_not_an_error(tmp_path: Path):
    adapter = GeminiAdapter(tmp_path / "absent")
    assert adapter.is_available() is False
    assert adapter.list_sessions() == []
