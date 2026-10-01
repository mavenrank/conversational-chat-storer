"""Read local Codex CLI/Desktop chats, archived history, and delegated runs."""

from __future__ import annotations

import json
import shlex
from collections import OrderedDict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

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
from ccsweb.sources.codex_index import read_meta, read_names, read_state, read_tail, subagent_parent
from ccsweb.sources.opencode_parts import _CAPTION_RE
from ccsweb.sources.trim import trim_tool_output
from ccsweb.util.jsonio import iter_jsonl
from ccsweb.util.time import parse_epoch_ms, parse_iso

_TOOL_CALL_TYPES = {"custom_tool_call", "function_call"}
_TOOL_OUTPUT_TYPES = {"custom_tool_call_output", "function_call_output"}


class CodexAdapter(SourceAdapter):
    source_id = "codex"
    display_name = "Codex"

    def __init__(self, root: Path | None = None) -> None:
        super().__init__(root)
        self._lock = RLock()
        self._heads: dict[Path, tuple[tuple[int, int], dict]] = {}
        self._tails: dict[Path, tuple[tuple[int, int], SessionSummary]] = {}
        self._fallback: dict[Path, tuple[tuple[int, int], SessionSummary]] = {}
        self._details: OrderedDict[Path, tuple[tuple[int, int], SessionDetail]] = OrderedDict()

    @staticmethod
    def default_root() -> Path:
        return Path.home() / ".codex"

    def is_available(self) -> bool:
        return any((self.root / d).is_dir() for d in ("sessions", "archived_sessions"))

    def _rollouts(self) -> list[Path]:
        return [
            p
            for d in ("sessions", "archived_sessions")
            for p in (self.root / d).rglob("rollout-*.jsonl")
        ]

    def _index(self) -> dict[str, SessionSummary]:
        rows, parents = read_state(self.root)
        names = read_names(self.root)
        paths = self._rollouts()
        chosen: dict[str, tuple[Path, dict, tuple[int, int]]] = {}
        for path in paths:
            try:
                stamp = _stamp(path)
            except OSError:
                continue
            cached = self._heads.get(path)
            meta = cached[1] if cached and cached[0] == stamp else read_meta(path)
            self._heads[path] = stamp, meta
            if not meta:
                continue
            # session_id can identify the parent; id identifies this thread.
            native_id = str(meta.get("id") or meta.get("session_id") or path.stem)
            previous = chosen.get(native_id)
            indexed_path = rows.get(native_id, {}).get("rollout_path")
            if previous and _same_path(previous[0], indexed_path):
                continue
            if previous and not _same_path(path, indexed_path) and stamp <= previous[2]:
                continue
            chosen[native_id] = path, meta, stamp
        live = set(paths)
        self._heads = {p: v for p, v in self._heads.items() if p in live}
        self._tails = {p: v for p, v in self._tails.items() if p in live}
        self._fallback = {p: v for p, v in self._fallback.items() if p in live}
        self._details = OrderedDict((p, v) for p, v in self._details.items() if p in live)
        summaries = {}
        for native_id, (path, meta, stamp) in chosen.items():
            row = rows.get(native_id, {})
            cached = self._details.get(path)
            if cached and cached[0] == stamp:
                summary = SessionSummary.model_validate(cached[1].model_dump())
            elif not row:
                # CLI-only installs have no native index; reuse unchanged scans.
                cached_summary = self._fallback.get(path)
                if cached_summary and cached_summary[0] == stamp:
                    summary = cached_summary[1].model_copy(deep=True)
                else:
                    summary = SessionSummary.model_validate(
                        self._read_detail(path, native_id, stamp).model_dump()
                    )
                    self._fallback[path] = stamp, summary.model_copy(deep=True)
            else:
                cached_tail = self._tails.get(path)
                if cached_tail and cached_tail[0] == stamp:
                    summary = cached_tail[1].model_copy(deep=True)
                else:
                    summary = _summary(native_id, path, meta, read_tail(path))
                    self._tails[path] = stamp, summary.model_copy(deep=True)
                summary.counts_exact = False
            child, parent = subagent_parent(meta, row)
            cwd = str(row.get("cwd") or meta.get("cwd") or "")
            summary.cwd, summary.project = cwd, _project(cwd, native_id)
            summary.title = str(
                row.get("name") or names.get(native_id) or row.get("title") or summary.title
            ).strip()
            summary.created_at = _row_time(row, "created_at") or summary.created_at
            recency = _row_time(row, "recency_at")
            summary.updated_at = (
                max(filter(None, (recency, summary.updated_at)), default=None)
                if recency
                else (_row_time(row, "updated_at") or summary.updated_at)
            )
            summary.is_subagent = child
            summary.parent_session_id = parents.get(native_id) or parent
            summary.is_archived = bool(row.get("archived")) or "archived_sessions" in path.parts
            # Real forks remain independent visible conversations.
            summary.fork_of = meta.get("forked_from_id")
            if row.get("model") and row["model"] not in summary.models:
                summary.models.append(row["model"])
            summaries[native_id] = summary
        for summary in summaries.values():
            summary.subagent_count = sum(
                s.is_subagent and s.parent_session_id == summary.id for s in summaries.values()
            )
        return summaries

    def list_sessions(self) -> list[SessionSummary]:
        with self._lock:
            return list(self._index().values())

    def _read_detail(self, path: Path, native_id: str, stamp: tuple[int, int]) -> SessionDetail:
        cached = self._details.get(path)
        if cached and cached[0] == stamp:
            self._details.move_to_end(path)
            return cached[1]
        records = list(iter_jsonl(path))
        meta = next(
            (r.get("payload") or {} for r in records if r.get("type") == "session_meta"), {}
        )
        messages = list(_build_messages(records))
        summary = _summary(native_id, path, meta, records)
        summary.title = _first_prompt(messages) or summary.title
        summary.message_count = len(messages)
        summary.user_message_count = sum(m.role == "user" for m in messages)
        summary.models = sorted(set(summary.models) | {m.model for m in messages if m.model})
        if not summary.usage.total_tokens:
            for message in messages:
                if message.usage:
                    summary.usage = summary.usage + message.usage
        detail = SessionDetail(**summary.model_dump(), messages=messages)
        if stamp[1] <= 16 * 1024 * 1024:
            self._details[path] = stamp, detail
            self._details.move_to_end(path)
            while len(self._details) > 8:
                self._details.popitem(last=False)
        return detail

    def get_session(self, session_id: str) -> SessionDetail | None:
        with self._lock:
            summaries = self._index()
            summary = summaries.get(session_id)
            if summary is None:
                return None
            path = Path(summary.source_path)
            try:
                detail = self._read_detail(path, session_id, _stamp(path)).model_copy(deep=True)
            except OSError:
                return None
            for field in (
                "title",
                "created_at",
                "updated_at",
                "project",
                "cwd",
                "is_archived",
                "is_subagent",
                "parent_session_id",
                "subagent_count",
                "fork_of",
            ):
                setattr(detail, field, getattr(summary, field))
            detail.subagents = [
                s for s in summaries.values() if s.is_subagent and s.parent_session_id == session_id
            ]
            return detail


def _stamp(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _same_path(path: Path, value: Any) -> bool:
    return (
        bool(value)
        and str(path).replace("\\", "/").casefold() == str(value).replace("\\", "/").casefold()
    )


def _row_time(row: dict, field: str) -> datetime | None:
    return parse_epoch_ms(row.get(field + "_ms")) or parse_epoch_ms((row.get(field) or 0) * 1000)


def _project(cwd: str, native_id: str) -> ProjectRef | None:
    return (
        ProjectRef(
            id=cwd or native_id, name=cwd.replace("\\", "/").rstrip("/").split("/")[-1], path=cwd
        )
        if cwd
        else None
    )


def _summary(native_id: str, path: Path, meta: dict, records: list[dict]) -> SessionSummary:
    models = {str(meta["model"])} if meta.get("model") else set()
    latest = parse_iso(meta.get("timestamp"))
    usage = Usage()
    has_thread_usage = False
    for record in records:
        timestamp = _activity_time(record)
        if timestamp and (latest is None or timestamp > latest):
            latest = timestamp
        payload = record.get("payload") or {}
        if record.get("type") == "turn_context" and payload.get("model"):
            models.add(str(payload["model"]))
        total = (
            payload.get("thread_token_usage")
            if record.get("type") == "token_usage_record"
            else None
        )
        if payload.get("type") == "token_count" and not has_thread_usage:
            total = (payload.get("info") or {}).get("total_token_usage") or total
        if isinstance(total, dict):
            usage = _usage(total)
            if record.get("type") == "token_usage_record":
                has_thread_usage = True
    cwd = str(meta.get("cwd") or "")
    return SessionSummary(
        id=native_id,
        source="codex",
        title="Untitled session",
        cwd=cwd,
        project=_project(cwd, native_id),
        source_path=str(path),
        created_at=parse_iso(meta.get("timestamp")),
        updated_at=latest,
        models=sorted(models),
        providers=[str(meta.get("model_provider") or "openai")],
        usage=usage,
    )


def _activity_time(record: dict) -> datetime | None:
    """Ignore settings/index bookkeeping; include progress in running turns."""
    kind, payload = record.get("type"), record.get("payload") or {}
    subtype = payload.get("type")
    if kind == "token_usage_record":
        return parse_iso(record.get("timestamp"))
    if kind == "event_msg":
        if subtype == "item_completed":
            return parse_epoch_ms(payload.get("completed_at_ms")) or parse_iso(
                record.get("timestamp")
            )
        if subtype not in {
            "user_message",
            "agent_message",
            "agent_reasoning",
            "task_complete",
            "turn_aborted",
            "token_count",
        }:
            return None
    elif kind == "response_item":
        if subtype == "message":
            role = payload.get("role")
            if role == "user" and _wire_context(payload) == "injected":
                return None
            kinds = (payload.get("internal_chat_message_metadata_passthrough") or {}).get(
                "content_item_kinds"
            ) or []
            if role not in {"user", "assistant"} or (
                role == "user" and kinds and not any(str(k).startswith("user.") for k in kinds)
            ):
                return None
    else:
        return None
    return parse_iso(record.get("timestamp"))


def _wire_context(payload: dict) -> str:
    kinds = (payload.get("internal_chat_message_metadata_passthrough") or {}).get(
        "content_item_kinds"
    ) or []
    if kinds:
        return "user" if any(str(k).startswith("user.") for k in kinds) else "injected"
    text = _flatten_content(payload.get("content")).lstrip()
    if text.startswith(
        (
            "<environment_context>",
            "<recommended_plugins>",
            "<user_instructions>",
            "<permissions instructions>",
        )
    ):
        return "injected"
    if text.startswith("# Files mentioned by the user:"):
        return "attachments"
    return "user"


def _turns(records: list[dict]) -> list[str]:
    current = "legacy"
    turns = []
    for record in records:
        payload = record.get("payload") or {}
        metadata = payload.get("internal_chat_message_metadata_passthrough") or {}
        if payload.get("turn_id"):
            current = str(payload["turn_id"])
        turns.append(str(metadata.get("turn_id") or current))
    return turns


def _build_messages(records: list[dict[str, Any]]) -> Iterable[Message]:
    """Prefer the desktop display stream per turn; fall back to CLI/wire prose."""
    turns = _turns(records)
    item_turns = {
        t
        for t, r in zip(turns, records, strict=True)
        if (r.get("payload") or {}).get("type") == "item_completed"
        and ((r.get("payload") or {}).get("item") or {}).get("type") != "ContextCompaction"
    }
    item_roles = {
        (t, ("user" if item.get("type") == "UserMessage" else "assistant"))
        for t, r in zip(turns, records, strict=True)
        for p in [r.get("payload") or {}]
        for item in [p.get("item") or {}]
        if p.get("type") == "item_completed" and item.get("type") in {"UserMessage", "AgentMessage"}
    }
    event_roles = {
        (t, ("user" if p.get("type") == "user_message" else "assistant"))
        for t, r in zip(turns, records, strict=True)
        for p in [r.get("payload") or {}]
        if p.get("type") in {"user_message", "agent_message"}
    }
    modern_usage_turns = {
        t for t, r in zip(turns, records, strict=True) if r.get("type") == "token_usage_record"
    }
    outputs = _collect_tool_outputs(records)
    messages: list[Message] = []
    pending: list[Block] = []
    started = completed = model = None
    provider = "openai"
    pending_usage = Usage()
    seen_items: set[str] = set()
    seen_requests: set[str] = set()
    seen_wire: set[str] = set()
    previous_total: dict[str, int] = {}

    def flush():
        nonlocal pending, started, completed, pending_usage
        if pending:
            messages.append(
                Message(
                    id=f"assistant-{len(messages)}",
                    role="assistant",
                    blocks=pending,
                    started_at=started,
                    completed_at=completed,
                    model=model,
                    provider=provider,
                    usage=pending_usage if pending_usage.total_tokens else None,
                )
            )
        pending, started, completed, pending_usage = [], None, None, Usage()

    def add(block: Block, begin: datetime | None, end: datetime | None = None):
        nonlocal started, completed
        started = started or begin
        completed = end or begin or completed
        pending.append(block)

    for turn, record in zip(turns, records, strict=True):
        kind = record.get("type")
        payload = record.get("payload") or {}
        subtype = payload.get("type")
        timestamp = parse_iso(record.get("timestamp"))
        if kind == "session_meta":
            model = payload.get("model") or model
            provider = str(payload.get("model_provider") or provider)
        elif kind == "turn_context":
            model = payload.get("model") or model
        elif kind == "token_usage_record" or subtype == "token_count":
            raw = None
            if kind == "token_usage_record":
                request = str(payload.get("response_id") or "")
                if request and request in seen_requests:
                    continue
                if request:
                    seen_requests.add(request)
                raw = payload.get("usage")
            else:
                total = (payload.get("info") or {}).get("total_token_usage")
                if isinstance(total, dict):
                    delta = {
                        k: max(0, v - previous_total.get(k, 0))
                        for k, v in total.items()
                        if isinstance(v, int)
                    }
                    previous_total = total
                    if turn not in modern_usage_turns:
                        raw = delta
            if isinstance(raw, dict):
                usage = _usage(raw)
                if pending:
                    pending_usage = pending_usage + usage
                elif messages and messages[-1].role == "assistant":
                    messages[-1].usage = (messages[-1].usage or Usage()) + usage
                else:
                    pending_usage = pending_usage + usage
        elif subtype in {"task_complete", "turn_aborted"}:
            flush()
        elif subtype == "item_completed" and turn in item_turns:
            item = payload.get("item") or {}
            item_id = str(item.get("id") or "")
            if item_id and item_id in seen_items:
                continue
            if item_id:
                seen_items.add(item_id)
            item_type = item.get("type")
            begin = (
                parse_epoch_ms(payload.get("started_at_ms"))
                or parse_epoch_ms(payload.get("completed_at_ms"))
                or timestamp
            )
            end = parse_epoch_ms(payload.get("completed_at_ms")) or begin
            text = _flatten_content(item.get("content"))
            if item_type == "UserMessage":
                flush()
                if text:
                    messages.append(
                        Message(
                            id=item_id or f"user-{len(messages)}",
                            role="user",
                            blocks=[TextBlock(text=text)],
                            started_at=begin,
                            completed_at=end,
                        )
                    )
            elif item_type == "AgentMessage":
                if text:
                    add(TextBlock(text=text), begin, end)
                    flush()
            elif item_type == "Reasoning":
                block = _thinking(
                    _flatten_content(item.get("summary_text"))
                    or _flatten_content(item.get("raw_content"))
                )
                if block:
                    add(block, begin, end)
            elif item_type != "ContextCompaction":
                add(_item_tool(item), begin, end)
        elif kind == "event_msg" and turn not in item_turns:
            if subtype == "user_message":
                flush()
                text = str(payload.get("message") or "").strip()
                if text:
                    messages.append(
                        Message(
                            id=f"user-{len(messages)}",
                            role="user",
                            blocks=[TextBlock(text=text)],
                            started_at=timestamp,
                        )
                    )
            elif subtype == "agent_message":
                text = str(payload.get("message") or "").strip()
                if text:
                    add(TextBlock(text=text), timestamp)
                    flush()
            elif subtype == "agent_reasoning":
                block = _thinking(str(payload.get("text") or ""))
                if block:
                    add(block, timestamp)
        elif kind == "response_item":
            if subtype in _TOOL_CALL_TYPES and turn not in item_turns:
                add(_tool_block(payload, outputs), timestamp)
            elif subtype == "message":
                role = payload.get("role")
                context = _wire_context(payload) if role == "user" else "user"
                if context == "injected":
                    continue
                if context == "attachments":
                    flush()
                    messages.append(
                        Message(
                            id=str(payload.get("id") or f"attachments-{len(messages)}"),
                            role="info",
                            blocks=[TextBlock(text=_flatten_content(payload.get("content")))],
                            started_at=timestamp,
                        )
                    )
                    continue
                if (turn, role) in item_roles or (turn, role) in event_roles:
                    continue
                wire_id = str(payload.get("id") or "")
                if wire_id and wire_id in seen_wire:
                    continue
                if wire_id:
                    seen_wire.add(wire_id)
                metadata = payload.get("internal_chat_message_metadata_passthrough") or {}
                content_kinds = metadata.get("content_item_kinds") or []
                if (
                    role == "user"
                    and content_kinds
                    and not any(str(k).startswith("user.") for k in content_kinds)
                ):
                    continue
                text = _flatten_content(payload.get("content"))
                begin = parse_epoch_ms((metadata.get("create_time") or 0) * 1000) or timestamp
                if text and role == "user":
                    flush()
                    messages.append(
                        Message(
                            id=str(payload.get("id") or f"user-{len(messages)}"),
                            role="user",
                            blocks=[TextBlock(text=text)],
                            started_at=begin,
                        )
                    )
                elif text and role == "assistant":
                    add(TextBlock(text=text), begin)
                    flush()
            elif subtype == "reasoning" and turn not in item_turns:
                block = _thinking(_flatten_content(payload.get("summary")))
                if block:
                    add(block, timestamp)
    flush()
    yield from messages


def _usage(raw: dict) -> Usage:
    def number(key: str) -> int:
        try:
            return max(0, int(raw.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    cached, thinking = number("cached_input_tokens"), number("reasoning_output_tokens")
    return Usage(
        input_tokens=max(0, number("input_tokens") - cached),
        cached_tokens=cached,
        output_tokens=max(0, number("output_tokens") - thinking),
        thinking_tokens=thinking,
    )


def _collect_tool_outputs(records: list[dict]) -> dict[str, str]:
    return {
        str(p["call_id"]): trim_tool_output(_flatten_content(p.get("output")))
        for r in records
        if r.get("type") == "response_item"
        for p in [r.get("payload") or {}]
        if p.get("type") in _TOOL_OUTPUT_TYPES and p.get("call_id")
    }


def _status(value: Any, has_output: bool = True) -> str:
    status = str(value or ("completed" if has_output else "pending")).lower()
    if status in {"failed", "error"}:
        return "error"
    if status in {"pending", "running", "in_progress"}:
        return "running" if status == "in_progress" else status
    return "completed"


def _tool_block(payload: dict, outputs: dict[str, str]) -> ToolUseBlock:
    name, call_id = str(payload.get("name") or "tool"), str(payload.get("call_id") or "")
    output = outputs.get(call_id, "")
    raw = payload.get("arguments") or payload.get("input") or ""
    try:
        arguments = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        arguments = {"raw": raw}
    if not isinstance(arguments, dict):
        arguments = {"raw": arguments}
    short_name = name.rsplit(".", 1)[-1]
    if short_name in {"exec", "exec_command", "shell", "shell_command", "local_shell"}:
        command = arguments.get("cmd") or arguments.get("command") or arguments.get("raw") or raw
        detail = CommandDetail(command=str(command), output=output)
    elif short_name in {"apply_patch", "edit"}:
        detail = FileEditDetail(path="", unified_diff=str(raw))
    else:
        detail = GenericDetail(input=arguments, output=output)
    return ToolUseBlock(
        tool_id=call_id or None,
        name=name,
        status=_status(payload.get("status"), call_id in outputs),
        detail=detail,
    )  # type: ignore[arg-type]


def _item_tool(item: dict) -> ToolUseBlock:
    kind = item.get("type") or "Tool"
    status = _status(item.get("status"))
    if kind == "CommandExecution":
        command = item.get("command") or ""
        if isinstance(command, list):
            command = shlex.join(str(p) for p in command)
        detail = CommandDetail(
            command=str(command),
            output=trim_tool_output(
                str(
                    item.get("aggregated_output")
                    or item.get("formatted_output")
                    or "\n".join(str(item.get(k)) for k in ("stdout", "stderr") if item.get(k))
                )
            ),
            exit_code=item.get("exit_code"),
        )
        if item.get("exit_code") not in (None, 0):
            status = "error"
    elif kind == "FileChange":
        changes = item.get("changes") or {}
        detail = FileEditDetail(
            path=", ".join(changes),
            unified_diff="\n".join(
                str(v.get("unified_diff") or v.get("diff") or v.get("content") or "")
                for v in changes.values()
                if isinstance(v, dict)
            ),
        )
    elif kind == "McpToolCall":
        result = item.get("result") or {}
        detail = GenericDetail(
            input=item.get("arguments") or {},
            output=trim_tool_output(_flatten_content(result.get("content"))),
        )
        if result.get("isError"):
            status = "error"
    else:
        detail = GenericDetail(input={k: v for k, v in item.items() if k not in {"type", "id"}})
    duration = item.get("duration") or {}
    duration_ms = (
        int((duration.get("secs", 0) + duration.get("nanos", 0) / 1e9) * 1000)
        if isinstance(duration, dict) and duration
        else None
    )
    return ToolUseBlock(
        tool_id=item.get("id"),
        name=str(item.get("tool") or kind),
        status=status,
        duration_ms=duration_ms,
        detail=detail,
    )  # type: ignore[arg-type]


def _thinking(text: str) -> ThinkingBlock | None:
    text = text.strip()
    if not text:
        return None
    match = _CAPTION_RE.match(text)
    if match:
        return ThinkingBlock(
            subject=match.group("caption").strip(), text=match.group("body").strip()
        )
    if text.startswith("**") and text.endswith("**"):
        return ThinkingBlock(subject=text.strip("*").strip(), text="")
    return ThinkingBlock(text=text)


def _flatten_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(text for item in content if (text := _flatten_content(item)))
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if content.get("type") in {"image", "input_image", "localImage"}:
            return "[Attached image]"
    return ""


def _first_prompt(messages: list[Message]) -> str:
    return next(
        (
            m.text.strip().splitlines()[0][:120]
            for m in messages
            if m.role == "user" and m.text.strip()
        ),
        "",
    )
