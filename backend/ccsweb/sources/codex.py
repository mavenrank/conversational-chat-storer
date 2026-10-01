"""Codex CLI / Desktop adapter.

Storage is one JSONL "rollout" per session::

    ~/.codex/sessions/YYYY/MM/DD/rollout-<iso-ts>-<session-id>.jsonl

Every line is ``{timestamp, type, payload}``. Four record types matter:

``session_meta``
    First line. Carries ``session_id``, ``cwd``, ``model_provider``,
    ``cli_version`` and ``originator``.
``event_msg``
    The display stream — what the user actually saw. ``user_message``,
    ``agent_message``, ``agent_reasoning``, ``token_count``.
``response_item``
    The wire stream — ``message``, ``reasoning``, ``custom_tool_call``,
    ``function_call`` and their ``*_output`` counterparts.
``turn_context`` / ``world_state``
    Environment bookkeeping, ignored.

Prose and reasoning are taken from ``event_msg`` because that is the rendered
view: ``response_item.reasoning`` usually has an empty ``summary`` and only an
opaque ``encrypted_content``. Tool calls come from ``response_item``, paired to
their output by ``call_id``.

Like opencode's OpenAI reasoning, ``agent_reasoning`` text leads with a bold
caption, which is lifted into the thinking block's subject.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ccsweb.models import (
    Block,
    CommandDetail,
    FileEditDetail,
    GenericDetail,
    Message,
    ProjectRef,
    SessionDetail,
    SessionSummary,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    Usage,
)
from ccsweb.sources.base import SourceAdapter
from ccsweb.sources.trim import trim_tool_output
from ccsweb.sources.opencode_parts import _CAPTION_RE  # shared caption grammar
from ccsweb.util.jsonio import iter_jsonl
from ccsweb.util.time import parse_iso

_TOOL_CALL_TYPES = {"custom_tool_call", "function_call"}
_TOOL_OUTPUT_TYPES = {"custom_tool_call_output", "function_call_output"}


class CodexAdapter(SourceAdapter):
    source_id = "codex"
    display_name = "Codex"

    @staticmethod
    def default_root() -> Path:
        return Path.home() / ".codex"

    @property
    def _sessions_dir(self) -> Path:
        return self.root / "sessions"

    def is_available(self) -> bool:
        return self._sessions_dir.is_dir()

    def _rollouts(self) -> list[Path]:
        if not self._sessions_dir.is_dir():
            return []
        return sorted(self._sessions_dir.glob("*/*/*/rollout-*.jsonl"), reverse=True)

    def _find(self, session_id: str) -> Path | None:
        for path in self._rollouts():
            if path.stem.endswith(session_id):
                return path
        return None

    # ------------------------------------------------------------------ #

    def list_sessions(self) -> list[SessionSummary]:
        sessions: list[SessionSummary] = []
        for path in self._rollouts():
            meta, first_prompt, count, last_ts, user_count = _scan(path)
            if not meta:
                continue
            session_id = str(meta.get("session_id") or path.stem)
            cwd = str(meta.get("cwd") or "")
            sessions.append(
                SessionSummary(
                    id=session_id,
                    source=self.source_id,
                    title=first_prompt or "Untitled session",
                    project=ProjectRef(id=cwd or session_id, name=Path(cwd).name, path=cwd)
                    if cwd
                    else None,
                    cwd=cwd,
                    created_at=parse_iso(meta.get("timestamp")),
                    updated_at=last_ts,
                    message_count=count,
                    user_message_count=user_count,
                    models=[m] if (m := meta.get("model")) else [],
                    source_path=str(path),
                )
            )
        return sessions

    def get_session(self, session_id: str) -> SessionDetail | None:
        path = self._find(session_id)
        if path is None:
            return None

        records = list(iter_jsonl(path))
        meta = next(
            (r.get("payload") or {} for r in records if r.get("type") == "session_meta"),
            {},
        )
        messages = list(_build_messages(records))
        cwd = str(meta.get("cwd") or "")

        usage = Usage()
        for message in messages:
            if message.usage is not None:
                usage = usage + message.usage

        return SessionDetail(
            id=session_id,
            source=self.source_id,
            title=_first_prompt(messages) or "Untitled session",
            project=ProjectRef(id=cwd or session_id, name=Path(cwd).name, path=cwd)
            if cwd
            else None,
            cwd=cwd,
            created_at=parse_iso(meta.get("timestamp")),
            updated_at=messages[-1].started_at if messages else None,
            message_count=len(messages),
            user_message_count=sum(1 for m in messages if m.role == "user"),
            models=sorted({m.model for m in messages if m.model}),
            usage=usage,
            source_path=str(path),
            messages=messages,
        )


# ---------------------------------------------------------------------- #


def _scan(path: Path) -> tuple[dict[str, Any], str, int, Any, int]:
    """Cheap pass for the list view: metadata, first prompt, turn counts."""
    meta: dict[str, Any] = {}
    first_prompt = ""
    count = 0
    user_count = 0
    last_ts = None
    for record in iter_jsonl(path):
        payload = record.get("payload") or {}
        kind = record.get("type")
        if kind == "session_meta" and not meta:
            meta = payload
        elif kind == "event_msg":
            subtype = payload.get("type")
            if subtype == "user_message":
                count += 1
                user_count += 1
                if not first_prompt:
                    text = str(payload.get("message") or "").strip()
                    if text:
                        first_prompt = text.splitlines()[0][:120]
            elif subtype == "agent_message":
                count += 1
        if record.get("timestamp"):
            last_ts = parse_iso(record["timestamp"]) or last_ts
    return meta, first_prompt, count, last_ts, user_count


def _build_messages(records: list[dict[str, Any]]) -> Iterable[Message]:
    """Fold the record stream into user/assistant turns."""
    outputs = _collect_tool_outputs(records)

    pending: list[Block] = []
    pending_started = None
    index = 0

    def flush(model: str | None, usage: Usage | None):
        nonlocal pending, pending_started, index
        if not pending:
            return None
        message = Message(
            id=f"assistant-{index}",
            role="assistant",
            blocks=pending,
            started_at=pending_started,
            model=model,
            provider="openai",
            usage=usage,
        )
        pending = []
        pending_started = None
        index += 1
        return message

    for record in records:
        kind = record.get("type")
        payload = record.get("payload") or {}
        timestamp = parse_iso(record.get("timestamp"))

        if kind == "event_msg":
            subtype = payload.get("type")

            if subtype == "user_message":
                flushed = flush(None, None)
                if flushed is not None:
                    yield flushed
                text = str(payload.get("message") or "").strip()
                if text:
                    index += 1
                    yield Message(
                        id=f"user-{index}",
                        role="user",
                        blocks=[TextBlock(text=text)],
                        started_at=timestamp,
                    )

            elif subtype == "agent_reasoning":
                block = _thinking(str(payload.get("text") or ""))
                if block is not None:
                    pending_started = pending_started or timestamp
                    pending.append(block)

            elif subtype == "agent_message":
                text = str(payload.get("message") or "").strip()
                if text:
                    pending_started = pending_started or timestamp
                    pending.append(TextBlock(text=text))

        elif kind == "response_item" and payload.get("type") in _TOOL_CALL_TYPES:
            pending_started = pending_started or timestamp
            pending.append(_tool_block(payload, outputs))

    trailing = flush(None, None)
    if trailing is not None:
        yield trailing


def _collect_tool_outputs(records: list[dict[str, Any]]) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for record in records:
        payload = record.get("payload") or {}
        if record.get("type") != "response_item":
            continue
        if payload.get("type") not in _TOOL_OUTPUT_TYPES:
            continue
        call_id = payload.get("call_id")
        if call_id:
            outputs[call_id] = trim_tool_output(_flatten_content(payload.get("output")))
    return outputs


def _tool_block(payload: dict[str, Any], outputs: dict[str, str]) -> ToolUseBlock:
    name = str(payload.get("name") or "tool")
    call_id = str(payload.get("call_id") or "")
    output = outputs.get(call_id, "")
    raw_input = payload.get("input")
    arguments = payload.get("arguments")
    command = raw_input if isinstance(raw_input, str) else arguments or ""

    if name in {"exec", "shell", "shell_command", "local_shell"}:
        detail = CommandDetail(command=str(command), output=output)
    elif name in {"apply_patch", "edit"}:
        detail = FileEditDetail(path="", new_text=str(command))
    else:
        detail = GenericDetail(
            input={"raw": str(command)} if command else {}, output=output
        )

    status = str(payload.get("status") or "completed")
    return ToolUseBlock(
        tool_id=call_id or None,
        name=name,
        status=status if status in {"pending", "running", "completed", "error"} else "completed",  # type: ignore[arg-type]
        detail=detail,
    )


def _thinking(text: str) -> ThinkingBlock | None:
    text = text.strip()
    if not text:
        return None
    match = _CAPTION_RE.match(text)
    if match:
        return ThinkingBlock(
            subject=match.group("caption").strip(), text=match.group("body").strip()
        )
    # A bare "**Caption**" with no body is still a useful heading.
    stripped = text.strip("*").strip()
    if text.startswith("**") and text.endswith("**") and stripped:
        return ThinkingBlock(subject=stripped, text="")
    return ThinkingBlock(text=text)


def _flatten_content(content: Any) -> str:
    """Codex content is a list of ``{type, text}`` fragments."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if isinstance(content, dict):
        text = content.get("text")
        return text if isinstance(text, str) else ""
    return str(content)


def _first_prompt(messages: list[Message]) -> str:
    for message in messages:
        if message.role == "user" and message.text.strip():
            return message.text.strip().splitlines()[0][:120]
    return ""
