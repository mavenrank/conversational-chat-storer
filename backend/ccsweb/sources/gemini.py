"""Gemini CLI adapter.

Layout::

    ~/.gemini/tmp/<projectHash>/
        chats/session-<iso-ts>-<tag>.json   transcript snapshots
        logs.json                            flat log of user prompts only

Two things about this layout caused the bugs this adapter exists to fix.

**Snapshots, not sessions.** Gemini re-serialises the *entire* conversation to a
new file each time it saves. Successive snapshots of one conversation share an
internal ``sessionId`` but get different filenames, because the filename encodes
the save time. De-duplicating by filename therefore keeps every snapshot, and
the most recent one looks like a single chat that has "dumped its whole history"
next to smaller stale copies of itself. We de-duplicate on the internal
``sessionId`` and keep the snapshot with the latest ``lastUpdated``.

**Rich assistant metadata.** A ``type: "gemini"`` message carries ``thoughts``,
``tokens``, ``model`` and ``toolCalls`` alongside ``content``. Reading only
``content`` silently discards the thinking, the usage numbers and every tool
call.

``logs.json`` is not a transcript and is ignored.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ccsweb.models import (
    Message,
    ProjectRef,
    SessionDetail,
    SessionSummary,
    TextBlock,
    ThinkingBlock,
    Usage,
)
from ccsweb.sources.base import SourceAdapter
from ccsweb.sources.gemini_tools import build_tool_block
from ccsweb.util.jsonio import read_json
from ccsweb.util.time import parse_iso

#: Gemini's ``type`` field mapped onto our roles.
_ROLE_BY_TYPE = {
    "user": "user",
    "gemini": "assistant",
    "info": "info",
    "error": "error",
}

#: Sessions containing only these roles are bookkeeping (auth prompts, install
#: notices) rather than conversation, and are excluded from the list.
_NON_CONVERSATIONAL = {"info", "error"}


class GeminiAdapter(SourceAdapter):
    source_id = "gemini"
    display_name = "Gemini CLI"

    @staticmethod
    def default_root() -> Path:
        return Path.home() / ".gemini"

    @property
    def _tmp(self) -> Path:
        return self.root / "tmp"

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def _snapshots(self) -> dict[str, tuple[Path, dict[str, Any]]]:
        """Map ``sessionId`` -> newest snapshot for it.

        This is the fix for the duplicate-session bug: keyed on the id *inside*
        the file, not on the filename.
        """
        best: dict[str, tuple[Path, dict[str, Any]]] = {}
        if not self._tmp.is_dir():
            return best

        for chat_file in sorted(self._tmp.glob("*/chats/*.json")):
            data = read_json(chat_file)
            if not isinstance(data, dict):
                continue
            session_id = data.get("sessionId")
            if not session_id:
                continue

            previous = best.get(session_id)
            if previous is None or _snapshot_rank(data) > _snapshot_rank(previous[1]):
                best[session_id] = (chat_file, data)

        return best

    def list_sessions(self) -> list[SessionSummary]:
        sessions: list[SessionSummary] = []
        for session_id, (path, data) in self._snapshots().items():
            messages = data.get("messages") or []
            roles = {_ROLE_BY_TYPE.get(m.get("type", ""), "info") for m in messages}
            if not roles - _NON_CONVERSATIONAL:
                # Auth/install noise only — not a conversation.
                continue

            sessions.append(
                SessionSummary(
                    id=session_id,
                    source=self.source_id,
                    title=_derive_title(messages),
                    project=_project_ref(path, data),
                    created_at=parse_iso(data.get("startTime")),
                    updated_at=parse_iso(data.get("lastUpdated")),
                    message_count=len(messages),
                    user_message_count=sum(
                        1 for m in messages if m.get("type") == "user"
                    ),
                    models=sorted({m["model"] for m in messages if m.get("model")}),
                    usage=_sum_usage(messages),
                    source_path=str(path),
                )
            )

        sessions.sort(key=lambda s: s.updated_at or datetime.min, reverse=True)
        return sessions

    # ------------------------------------------------------------------ #
    # Detail
    # ------------------------------------------------------------------ #

    def get_session(self, session_id: str) -> SessionDetail | None:
        found = self._snapshots().get(session_id)
        if found is None:
            return None
        path, data = found

        raw_messages = data.get("messages") or []
        messages = [_build_message(raw) for raw in raw_messages]

        return SessionDetail(
            id=session_id,
            source=self.source_id,
            title=_derive_title(raw_messages),
            project=_project_ref(path, data),
            created_at=parse_iso(data.get("startTime")),
            updated_at=parse_iso(data.get("lastUpdated")),
            message_count=len(messages),
            user_message_count=sum(1 for m in messages if m.role == "user"),
            models=sorted({m.model for m in messages if m.model}),
            usage=_sum_usage(raw_messages),
            source_path=str(path),
            messages=messages,
        )


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


def _snapshot_rank(data: dict[str, Any]) -> tuple[datetime, int]:
    """Order snapshots of the same session: newest, then most complete."""
    updated = parse_iso(data.get("lastUpdated")) or datetime.min
    return updated, len(data.get("messages") or [])


def _project_ref(path: Path, data: dict[str, Any]) -> ProjectRef:
    # chats/<file>.json -> chats -> <projectHash>
    project_hash = data.get("projectHash") or path.parent.parent.name
    return ProjectRef(id=project_hash, name=project_hash[:12])


def _derive_title(messages: list[dict[str, Any]]) -> str:
    """First real user prompt, trimmed to one line."""
    for message in messages:
        if message.get("type") == "user":
            text = str(message.get("content") or "").strip()
            if text:
                first_line = text.splitlines()[0]
                return first_line[:120]
    return "Untitled session"


def _parse_usage(raw: dict[str, Any]) -> Usage | None:
    tokens = raw.get("tokens")
    if not isinstance(tokens, dict):
        return None
    return Usage(
        input_tokens=int(tokens.get("input") or 0),
        output_tokens=int(tokens.get("output") or 0),
        cached_tokens=int(tokens.get("cached") or 0),
        thinking_tokens=int(tokens.get("thoughts") or 0),
        tool_tokens=int(tokens.get("tool") or 0),
    )


def _sum_usage(messages: list[dict[str, Any]]) -> Usage:
    total = Usage()
    for message in messages:
        usage = _parse_usage(message)
        if usage is not None:
            total = total + usage
    return total


def _build_message(raw: dict[str, Any]) -> Message:
    role = _ROLE_BY_TYPE.get(raw.get("type", ""), "info")
    blocks: list[Any] = []

    # Thoughts are stored as {subject, description, timestamp} records.
    for thought in raw.get("thoughts") or []:
        if isinstance(thought, dict):
            description = str(thought.get("description") or "").strip()
            if description:
                blocks.append(
                    ThinkingBlock(
                        text=description,
                        subject=str(thought.get("subject") or "") or None,
                    )
                )
        elif isinstance(thought, str) and thought.strip():
            blocks.append(ThinkingBlock(text=thought.strip()))

    content = str(raw.get("content") or "").strip()
    if content:
        blocks.append(TextBlock(text=content))

    for call in raw.get("toolCalls") or []:
        block = build_tool_block(call)
        if block is not None:
            blocks.append(block)

    return Message(
        id=str(raw.get("id") or ""),
        role=role,  # type: ignore[arg-type]
        blocks=blocks,
        started_at=parse_iso(raw.get("timestamp")),
        model=raw.get("model"),
        provider="google" if raw.get("model") else None,
        usage=_parse_usage(raw),
    )
