"""Regression fixtures for modern desktop, legacy CLI, live files and WAL indexes."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ccsweb.models import CommandDetail
from ccsweb.sources.codex import CodexAdapter
from ccsweb.util.time import parse_iso


@pytest.mark.parametrize("ending", ["task_complete", "turn_completed", "turn_aborted"])
def test_live_status_changes_on_completion_and_abort(tmp_path: Path, ending: str):
    now = datetime.now(UTC).isoformat()
    path = write(
        tmp_path, "running", [meta("running"), record("event_msg", {"type": "task_started"}, now)]
    )
    adapter = CodexAdapter(tmp_path)
    assert adapter.list_sessions()[0].run_status == "running"
    assert adapter.get_session("running").run_status == "running"
    with path.open("a", encoding="utf8") as stream:
        stream.write(json.dumps(record("event_msg", {"type": ending}, now)) + "\n")
    assert adapter.list_sessions()[0].run_status == "idle"
    assert adapter.get_session("running").run_status == "idle"


def test_tail_progress_and_final_phase_establish_status_without_a_start(tmp_path: Path):
    from ccsweb.sources.codex import _run_status

    progress = item("AgentMessage", "p", "Working", phase="commentary")
    final = item("AgentMessage", "f", "Done", phase="final_answer")
    assert _run_status([progress]) == "running"
    assert _run_status([progress, final, record("token_usage_record", {"usage": {}})]) == "idle"
    for subtype in ("function_call_output", "custom_tool_call_output"):
        output = record("response_item", {"type": subtype, "output": "Result"})
        assert _run_status([output]) == "running"
        assert _run_status([final, output]) == "idle"
    assert _run_status([record("event_msg", {"type": "thread_settings_applied"})]) == "unknown"
    write(tmp_path, "stale", [meta("stale"), record("event_msg", {"type": "task_started"})])
    assert CodexAdapter(tmp_path).list_sessions()[0].run_status == "unknown"


def test_running_status_expires_even_when_rollout_cache_is_unchanged(tmp_path: Path, monkeypatch):
    from ccsweb.sources import codex

    now = datetime.now(UTC)
    write(
        tmp_path,
        "cached",
        [
            meta("cached"),
            record(
                "event_msg",
                {
                    "type": "item_started",
                    "started_at_ms": int(now.timestamp() * 1000),
                    "item": {"type": "CommandExecution", "id": "command"},
                },
            ),
        ],
    )
    adapter = CodexAdapter(tmp_path)
    assert adapter.list_sessions()[0].run_status == "running"

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return (now + timedelta(minutes=11)).astimezone(tz)

    monkeypatch.setattr(codex, "datetime", Later)
    assert adapter.list_sessions()[0].run_status == "unknown"
    assert adapter.get_session("cached").run_status == "unknown"
    monkeypatch.setattr(codex, "datetime", datetime)
    assert adapter.list_sessions()[0].run_status == "running"


def test_extensions_and_mcp_calls_keep_specific_operation_names_and_arguments():
    from ccsweb.sources.codex import _item_tool

    tool = _item_tool(
        {
            "type": "Extension",
            "id": "search",
            "kind": "web.search",
            "action": {"type": "findInPage", "url": "https://example.com", "pattern": "keyword"},
            "results": [{"text": "Found"}],
        }
    )
    assert tool.name == "Web · Find in page"
    assert tool.detail.input["action"]["pattern"] == "keyword"
    assert "Found" in tool.detail.output
    mcp = _item_tool(
        {
            "type": "McpToolCall",
            "server": "example",
            "tool": "lookup",
            "arguments": {"key": "value"},
        }
    )
    assert mcp.name == "example.lookup" and mcp.detail.input == {"key": "value"}


def test_approval_classification_uses_metadata_not_a_chat_title():
    from ccsweb.sources.codex_index import is_approval_review

    assert not is_approval_review({"title": "Guardian review"}, {})
    assert not is_approval_review({"source": {"subagent": {"other": "worker"}}}, {})
    assert is_approval_review({}, {"source": json.dumps({"subagent": {"other": "guardian"}})})


def record(kind: str, payload: dict, timestamp: str = "2026-10-01T09:00:00Z") -> dict:
    return {"type": kind, "timestamp": timestamp, "payload": payload}


def meta(native_id: str, **extra) -> dict:
    return record(
        "session_meta",
        {
            "id": native_id,
            "session_id": native_id,
            "timestamp": "2026-10-01T09:00:00Z",
            "cwd": r"C:\repos\sample",
            **extra,
        },
    )


def item(kind: str, native_id: str, text: str = "", **extra) -> dict:
    return record(
        "event_msg",
        {
            "type": "item_completed",
            "turn_id": "turn-1",
            "started_at_ms": 1790845200000,
            "completed_at_ms": 1790845201000,
            "item": {
                "type": kind,
                "id": native_id,
                "content": [{"type": "text", "text": text}],
                **extra,
            },
        },
    )


def write(root: Path, name: str, records: list[dict], archived: bool = False) -> Path:
    directory = root / ("archived_sessions" if archived else "sessions/2026/10/01")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"rollout-{name}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def state(root: Path, path: Path, native_id: str = "chat") -> sqlite3.Connection:
    db = sqlite3.connect(root / "state_5.sqlite")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute(
        "CREATE TABLE threads (id TEXT PRIMARY KEY, rollout_path TEXT, name TEXT, title TEXT, "
        "created_at_ms INTEGER, updated_at_ms INTEGER, recency_at_ms INTEGER, "
        "model TEXT, archived INTEGER)"
    )
    db.execute(
        "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?)",
        (
            native_id,
            str(path),
            "Saved name",
            "First prompt",
            1790845200000,
            1790845800000,
            1790845320000,
            "test-model",
            0,
        ),
    )
    db.commit()
    return db


def test_desktop_display_stream_preserves_prose_tools_and_real_user_times(tmp_path: Path):
    usage = {
        "input_tokens": 100,
        "cached_input_tokens": 60,
        "output_tokens": 30,
        "reasoning_output_tokens": 10,
    }
    records = [
        meta("chat"),
        record("turn_context", {"turn_id": "turn-1", "model": "test-model"}),
        record(
            "response_item",
            {
                "type": "message",
                "role": "user",
                "content": [{"text": "environment"}],
                "internal_chat_message_metadata_passthrough": {
                    "content_item_kinds": ["environments.environment_context"]
                },
            },
        ),
        record(
            "response_item", {"type": "message", "role": "user", "content": [{"text": "Question"}]}
        ),
        item("UserMessage", "human", "Question"),
        item(
            "CommandExecution",
            "cmd",
            command=["python", "-V"],
            aggregated_output="Python",
            exit_code=0,
            status="Completed",
        ),
        record(
            "response_item",
            {
                "type": "message",
                "id": "answer",
                "role": "assistant",
                "content": [{"text": "Answer"}],
            },
        ),
        item("AgentMessage", "answer", "Answer"),
        record(
            "token_usage_record",
            {
                "turn_id": "turn-1",
                "response_id": "request",
                "usage": usage,
                "thread_token_usage": usage,
            },
        ),
        record(
            "token_usage_record",
            {
                "turn_id": "turn-1",
                "response_id": "request",
                "usage": usage,
                "thread_token_usage": usage,
            },
        ),
        record("event_msg", {"type": "task_complete"}, "2026-10-01T09:02:00Z"),
    ]
    write(tmp_path, "chat", records)
    adapter = CodexAdapter(tmp_path)
    summary = adapter.list_sessions()[0]
    detail = adapter.get_session("chat")
    assert detail is not None
    assert [m.role for m in detail.messages] == ["user", "assistant"]
    assert [m.text for m in detail.messages] == ["Question", "Answer"]
    assert detail.messages[0].started_at == parse_iso("2026-10-01T09:00:00Z")
    assert isinstance(detail.messages[1].blocks[0].detail, CommandDetail)
    assert detail.messages[1].blocks[0].detail.command == "python -V"
    assert detail.models == ["test-model"]
    assert detail.usage.input_tokens == 40 and detail.usage.cached_tokens == 60
    assert detail.usage.output_tokens == 20 and detail.usage.thinking_tokens == 10
    assert detail.messages[1].usage.total_tokens == 130
    assert summary.updated_at == detail.updated_at == parse_iso("2026-10-01T09:02:00Z")
    assert detail.user_message_count == 1
    assert detail.project.name == "sample"


def test_ids_child_relationships_archives_and_true_forks_are_distinct(tmp_path: Path):
    write(tmp_path, "parent", [meta("parent"), item("UserMessage", "u-parent", "Same prompt")])
    write(
        tmp_path,
        "child",
        [
            meta(
                "child",
                session_id="parent",
                parent_thread_id="parent",
                thread_source="guardian_review",
            ),
            item("UserMessage", "u-child", "Review"),
        ],
    )
    write(
        tmp_path,
        "fork",
        [
            meta("fork", session_id="parent", forked_from_id="parent"),
            item("UserMessage", "u-fork", "Same prompt"),
        ],
        archived=True,
    )
    write(
        tmp_path,
        "agent",
        [
            meta("agent", source={"subagent": {"thread_spawn": {"parent_thread_id": "parent"}}}),
            item("UserMessage", "u-agent", "Delegated task"),
        ],
    )
    adapter = CodexAdapter(tmp_path)
    sessions = {s.id: s for s in adapter.list_sessions()}
    assert set(sessions) == {"parent", "child", "fork", "agent"}
    assert sessions["child"].is_approval_review and not sessions["child"].is_subagent
    assert sessions["child"].parent_session_id == "parent"
    assert sessions["agent"].is_subagent and not sessions["agent"].is_approval_review
    assert sessions["parent"].subagent_count == 1
    assert sessions["parent"].approval_review_count == 1
    assert sessions["fork"].is_archived and sessions["fork"].fork_of == "parent"
    assert not sessions["fork"].is_fork
    assert adapter.get_session("parent").subagents[0].id == "agent"
    assert adapter.get_session("parent").approval_reviews[0].id == "child"
    assert adapter.get_session("fork").id == "fork"


def test_native_index_uses_wal_saved_names_and_activity_without_full_scan(
    tmp_path: Path, monkeypatch
):
    path = write(tmp_path, "canonical", [meta("chat"), item("UserMessage", "u", "Question")])
    write(tmp_path, "duplicate", [meta("chat"), item("UserMessage", "dup", "Stale")])
    db = state(tmp_path, path)
    try:
        import ccsweb.sources.codex as codex

        monkeypatch.setattr(
            codex,
            "iter_jsonl",
            lambda p: pytest.fail("listing must not parse a full indexed rollout"),
        )
        adapter = CodexAdapter(tmp_path)
        sessions = adapter.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].title == "Saved name"
        assert sessions[0].source_path == str(path)
        assert not sessions[0].counts_exact
        # updated_at is bookkeeping; recency is actual conversation activity.
        assert sessions[0].updated_at == parse_iso("2026-10-01T09:02:00Z")
        db.execute("UPDATE threads SET name='Renamed',recency_at_ms=1790845500000")
        db.commit()
        assert adapter.list_sessions()[0].title == "Renamed"
        assert adapter.list_sessions()[0].updated_at == parse_iso("2026-10-01T09:05:00Z")
    finally:
        db.close()


def test_cli_event_prose_is_not_duplicated_and_tools_are_structured(tmp_path: Path):
    records = [
        meta("old", id=None, session_id="old"),
        record("event_msg", {"type": "user_message", "message": "Question"}),
        record(
            "response_item", {"type": "message", "role": "user", "content": [{"text": "Question"}]}
        ),
        record(
            "response_item",
            {
                "type": "function_call",
                "name": "functions.exec_command",
                "call_id": "call",
                "arguments": '{"cmd":"pwd"}',
            },
        ),
        record(
            "response_item",
            {"type": "function_call_output", "call_id": "call", "output": "workspace"},
        ),
        record("event_msg", {"type": "agent_message", "message": "Answer"}),
        record(
            "response_item",
            {"type": "message", "role": "assistant", "content": [{"text": "Answer"}]},
        ),
        record(
            "event_msg",
            {
                "type": "token_count",
                "info": {"total_token_usage": {"input_tokens": 20, "output_tokens": 5}},
            },
        ),
    ]
    write(tmp_path, "old", records)
    detail = CodexAdapter(tmp_path).get_session("old")
    assert [m.text for m in detail.messages] == ["Question", "Answer"]
    tool = detail.messages[1].blocks[0]
    assert tool.detail.command == "pwd" and tool.detail.output == "workspace"
    assert tool.status == "completed"
    assert detail.usage.output_tokens == 5


def test_wire_only_and_mixed_format_history_and_mid_write_append(tmp_path: Path):
    records = [
        meta("chat"),
        record("event_msg", {"type": "user_message", "message": "First"}),
        record(
            "response_item",
            {"type": "message", "role": "assistant", "content": [{"text": "First answer"}]},
        ),
        record("turn_context", {"turn_id": "turn-1"}),
        item("UserMessage", "new-user", "Second"),
        item("AgentMessage", "new-agent", "Second answer"),
    ]
    path = write(tmp_path, "chat", records)
    adapter = CodexAdapter(tmp_path)
    detail = adapter.get_session("chat")
    assert [m.text for m in detail.messages] == ["First", "First answer", "Second", "Second answer"]
    with path.open("a", encoding="utf8") as f:
        f.write(json.dumps(item("UserMessage", "third", "Third")) + '\n{"incomplete":')
    detail = adapter.get_session("chat")
    assert detail.user_message_count == 3
    assert detail.messages[-1].text == "Third"
    assert adapter.list_sessions()[0].user_message_count == 3


def test_archived_only_install_and_session_index_name(tmp_path: Path):
    write(tmp_path, "archive", [meta("chat"), item("UserMessage", "u", "Prompt")], archived=True)
    (tmp_path / "session_index.jsonl").write_text(
        json.dumps({"id": "chat", "thread_name": "My name"}) + "\n", encoding="utf8"
    )
    adapter = CodexAdapter(tmp_path)
    assert adapter.is_available()
    assert adapter.list_sessions()[0].title == adapter.get_session("chat").title == "My name"


def test_running_activity_beats_stale_index_and_usage_survives_context_reset(tmp_path: Path):
    path = write(
        tmp_path,
        "chat",
        [
            meta("chat"),
            item("UserMessage", "u", "Question"),
            record(
                "token_usage_record",
                {"thread_token_usage": {"output_tokens": 100}},
                "2026-10-01T09:06:00Z",
            ),
            record(
                "event_msg",
                {"type": "token_count", "info": {"total_token_usage": {"output_tokens": 5}}},
                "2026-10-01T09:06:01Z",
            ),
            record("event_msg", {"type": "thread_settings_applied"}, "2026-10-01T10:00:00Z"),
        ],
    )
    db = state(tmp_path, path)
    try:
        adapter = CodexAdapter(tmp_path)
        summary = adapter.list_sessions()[0]
        detail = adapter.get_session("chat")
        assert summary.updated_at == detail.updated_at == parse_iso("2026-10-01T09:06:01Z")
        assert summary.usage.output_tokens == detail.usage.output_tokens == 100
    finally:
        db.close()


def test_older_injected_context_and_attachment_context_are_not_human_prompts(tmp_path: Path):
    write(
        tmp_path,
        "chat",
        [
            meta("chat"),
            record(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "<recommended_plugins>Context</recommended_plugins>",
                        },
                        {
                            "type": "input_text",
                            "text": "<environment_context>Context</environment_context>",
                        },
                    ],
                },
            ),
            record(
                "response_item",
                {"type": "message", "role": "user", "content": [{"text": "Question"}]},
            ),
            record(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"text": "# Files mentioned by the user:\nimage.png"},
                        {"type": "input_image"},
                    ],
                },
            ),
            record(
                "response_item",
                {"type": "message", "role": "assistant", "content": [{"text": "Answer"}]},
            ),
        ],
    )
    detail = CodexAdapter(tmp_path).get_session("chat")
    assert detail.user_message_count == 1
    assert [m.role for m in detail.messages] == ["user", "info", "assistant"]
    assert "[Attached image]" in detail.messages[1].text
