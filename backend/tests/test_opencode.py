"""OpenCode adapter tests.

Cover the subagent-listing bug and the provider-dependent reasoning shapes.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ccsweb.models import TextBlock, ThinkingBlock, ToolUseBlock
from ccsweb.sources.opencode import OpenCodeAdapter
from ccsweb.sources.opencode_parts import parse_reasoning, parse_step_finish

SCHEMA = """
CREATE TABLE project (id TEXT PRIMARY KEY, worktree TEXT NOT NULL, vcs TEXT,
  name TEXT, time_created INTEGER, time_updated INTEGER, sandboxes TEXT);
CREATE TABLE session (id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
  parent_id TEXT, slug TEXT NOT NULL, directory TEXT NOT NULL, title TEXT NOT NULL,
  version TEXT NOT NULL, time_created INTEGER NOT NULL, time_updated INTEGER);
CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
  time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT NOT NULL,
  session_id TEXT NOT NULL, time_created INTEGER NOT NULL,
  time_updated INTEGER NOT NULL, data TEXT NOT NULL);
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "opencode"
    root.mkdir()
    conn = sqlite3.connect(root / "opencode.db")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO project VALUES ('p1','/home/me/app',NULL,'app',1,1,'[]')"
    )
    # One root session and one subagent child of it.
    conn.execute(
        "INSERT INTO session VALUES ('ses_root','p1',NULL,'s','/home/me/app',"
        "'Main chat','1',1770000000000,1770000100000)"
    )
    conn.execute(
        "INSERT INTO session VALUES ('ses_child','p1','ses_root','s2','/home/me/app',"
        "'Analyze thing (@explore subagent)','1',1770000050000,1770000060000)"
    )
    conn.commit()
    conn.close()
    return root


def _add_message(root: Path, msg_id: str, session: str, data: dict, parts: list[dict]):
    conn = sqlite3.connect(root / "opencode.db")
    conn.execute(
        "INSERT INTO message VALUES (?,?,?,?,?)",
        (msg_id, session, 1770000000000, 1770000004000, json.dumps(data)),
    )
    for index, part in enumerate(parts):
        conn.execute(
            "INSERT INTO part VALUES (?,?,?,?,?,?)",
            (f"{msg_id}-p{index}", msg_id, session, 1770000000000 + index,
             1770000000000 + index, json.dumps(part)),
        )
    conn.commit()
    conn.close()


def test_subagents_are_flagged_not_listed_as_chats(root: Path):
    """The core bug: children must be distinguishable from real conversations."""
    sessions = OpenCodeAdapter(root).list_sessions()
    by_id = {s.id: s for s in sessions}

    assert by_id["ses_root"].is_subagent is False
    assert by_id["ses_root"].subagent_count == 1
    assert by_id["ses_child"].is_subagent is True
    assert by_id["ses_child"].parent_session_id == "ses_root"


def test_registry_hides_subagents_by_default(root: Path, tmp_path: Path):
    from ccsweb.config import Settings
    from ccsweb.registry import Registry

    settings = Settings(
        claude_root=tmp_path / "none",
        gemini_root=tmp_path / "none",
        opencode_root=root,
        kilocode_root=tmp_path / "none",
        codex_root=tmp_path / "none",
        archive_root=tmp_path / "archive",
    )
    registry = Registry.from_settings(settings)

    default = registry.list_sessions()
    assert [s.id for s in default] == ["opencode:ses_root"]

    everything = registry.list_sessions(include_subagents=True)
    assert len(everything) == 2


def test_step_finish_supplies_usage(root: Path):
    """Tokens and cost live on step-finish, which the TUI discarded."""
    _add_message(
        root, "m1", "ses_root", {"role": "assistant", "modelID": "claude-sonnet"},
        [
            {"type": "text", "text": "Done."},
            {
                "type": "step-finish",
                "reason": "stop",
                "tokens": {"total": 10019, "input": 599, "output": 55,
                           "reasoning": 149, "cache": {"write": 0, "read": 9216}},
                "cost": 0.001893,
            },
        ],
    )
    detail = OpenCodeAdapter(root).get_session("ses_root")
    assert detail is not None
    usage = detail.messages[0].usage
    assert usage is not None
    assert usage.input_tokens == 599
    assert usage.cached_tokens == 9216
    assert usage.thinking_tokens == 149
    assert usage.cost_usd == pytest.approx(0.001893)
    assert usage.total_tokens == 10019, "matches opencode's own total"


def test_task_tool_links_child_session(root: Path):
    _add_message(
        root, "m2", "ses_root", {"role": "assistant"},
        [{
            "type": "tool",
            "tool": "task",
            "callID": "call_1",
            "state": {
                "status": "completed",
                "input": {"description": "Fetch docs", "subagent_type": "explore"},
                "output": "task_id: ses_child (for resuming)\n\n<task_result>\nFound it.\n</task_result>",
            },
        }],
    )
    detail = OpenCodeAdapter(root).get_session("ses_root")
    assert detail is not None
    tool = next(b for b in detail.messages[0].blocks if isinstance(b, ToolUseBlock))
    assert tool.detail.category == "subagent"
    assert tool.detail.child_session_id == "ses_child"
    assert tool.detail.result == "Found it."
    assert [s.id for s in detail.subagents] == ["ses_child"]


def test_synthetic_text_is_hidden(root: Path):
    _add_message(
        root, "m3", "ses_root", {"role": "assistant"},
        [
            {"type": "text", "text": "Continue if you have next steps.", "synthetic": True},
            {"type": "text", "text": "Real answer."},
        ],
    )
    detail = OpenCodeAdapter(root).get_session("ses_root")
    assert detail is not None
    texts = [b.text for b in detail.messages[0].blocks if isinstance(b, TextBlock)]
    assert texts == ["Real answer."]


# --------------------------------------------------------------------------- #
# Provider-specific reasoning
# --------------------------------------------------------------------------- #


def test_openai_caption_becomes_subject():
    block = parse_reasoning(
        {"type": "reasoning", "text": "**Analyzing file operations**\n\nI need to run a task.",
         "metadata": {"openai": {"itemId": "x"}}}
    )
    assert isinstance(block, ThinkingBlock)
    assert block.subject == "Analyzing file operations"
    assert block.text == "I need to run a task."


def test_plain_reasoning_has_no_subject():
    block = parse_reasoning({"type": "reasoning", "text": "The user is asking about X."})
    assert isinstance(block, ThinkingBlock)
    assert block.subject is None


def test_opaque_reasoning_is_dropped():
    """OpenAI/Copilot continuation chunks carry no text and must not render."""
    assert parse_reasoning(
        {"type": "reasoning", "text": "", "metadata": {"openai": {"itemId": "x"}}}
    ) is None


def test_step_finish_without_tokens():
    usage, cost = parse_step_finish({"type": "step-finish", "reason": "stop"})
    assert usage is None and cost is None
