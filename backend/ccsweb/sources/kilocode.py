"""Kilocode adapter.

Kilocode is a VS Code extension, so history lives in the extension's
``globalStorage``::

    <globalStorage>/kilocode.kilo-code/tasks/<task-id>/
        ui_messages.json               the rendered conversation
        api_conversation_history.json  the raw provider messages
        task_metadata.json
        checkpoints/

``ui_messages.json`` is the source of truth here because it is what the user
actually saw, and it carries reasoning, per-request usage and tool results that
the raw provider history does not.

Each entry is ``{ts, type: "say"|"ask", say|ask: <subtype>, text}`` where ``text``
is frequently a JSON string that must be decoded again.

Role assignment is subtle: the *first* ``say:text`` is the task prompt the user
typed, later ``say:text`` entries are assistant prose, and follow-up user turns
arrive as ``say:user_feedback``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from ccsweb.models import (
    Block,
    FileEditDetail,
    FileReadDetail,
    FileWriteDetail,
    GenericDetail,
    Message,
    ProjectRef,
    SearchDetail,
    SessionDetail,
    SessionSummary,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    Usage,
)
from ccsweb.sources.base import SourceAdapter
from ccsweb.util.jsonio import read_json
from ccsweb.util.time import parse_epoch_ms

#: Entries that carry no conversational content.
_SKIP = {"checkpoint_saved", "resume_task", "resume_completed_task", "api_req_finished"}


class KilocodeAdapter(SourceAdapter):
    source_id = "kilocode"
    display_name = "Kilocode"

    @staticmethod
    def default_root() -> Path:
        import os

        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Code" / "User" / "globalStorage" / "kilocode.kilo-code"

    @property
    def _tasks(self) -> Path:
        return self.root / "tasks"

    def is_available(self) -> bool:
        return self._tasks.is_dir()

    def _task_dir(self, session_id: str) -> Path | None:
        candidate = self._tasks / session_id
        return candidate if candidate.is_dir() else None

    # ------------------------------------------------------------------ #

    def list_sessions(self) -> list[SessionSummary]:
        if not self._tasks.is_dir():
            return []

        sessions: list[SessionSummary] = []
        for task_dir in self._tasks.iterdir():
            if not task_dir.is_dir():
                continue
            ui_path = task_dir / "ui_messages.json"
            entries = read_json(ui_path)
            if not isinstance(entries, list) or not entries:
                continue

            usage, providers, models = _scan_usage(entries)
            sessions.append(
                SessionSummary(
                    id=task_dir.name,
                    source=self.source_id,
                    title=_derive_title(entries),
                    project=_project_ref(task_dir),
                    cwd=_derive_cwd(entries),
                    created_at=parse_epoch_ms(entries[0].get("ts")),
                    updated_at=parse_epoch_ms(entries[-1].get("ts")),
                    message_count=sum(
                        1 for e in entries if _role_of(e, entries) is not None
                    ),
                    user_message_count=sum(
                        1 for e in entries if _role_of(e, entries) == "user"
                    ),
                    models=sorted(models),
                    providers=sorted(providers),
                    usage=usage,
                    source_path=str(ui_path),
                )
            )

        # Sort on a datetime throughout; mixing datetime with a numeric fallback
        # raises a TypeError as soon as one session lacks timestamps.
        sessions.sort(
            key=lambda s: s.updated_at or s.created_at or datetime.min, reverse=True
        )
        return sessions

    def get_session(self, session_id: str) -> SessionDetail | None:
        task_dir = self._task_dir(session_id)
        if task_dir is None:
            return None
        ui_path = task_dir / "ui_messages.json"
        entries = read_json(ui_path)
        if not isinstance(entries, list):
            return None

        messages = list(_build_messages(entries))
        usage, providers, models = _scan_usage(entries)

        return SessionDetail(
            id=session_id,
            source=self.source_id,
            title=_derive_title(entries),
            project=_project_ref(task_dir),
            cwd=_derive_cwd(entries),
            created_at=parse_epoch_ms(entries[0].get("ts")) if entries else None,
            updated_at=parse_epoch_ms(entries[-1].get("ts")) if entries else None,
            message_count=len(messages),
            user_message_count=sum(1 for m in messages if m.role == "user"),
            models=sorted(models),
            providers=sorted(providers),
            usage=usage,
            source_path=str(ui_path),
            messages=messages,
        )


# ---------------------------------------------------------------------- #


def _decode(text: Any) -> dict[str, Any]:
    """Kilocode double-encodes structured payloads as JSON inside ``text``."""
    if not isinstance(text, str) or not text.strip():
        return {}
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _subtype(entry: dict[str, Any]) -> str:
    return str(entry.get("say") or entry.get("ask") or "")


def _role_of(entry: dict[str, Any], entries: list[dict[str, Any]]) -> str | None:
    """Map an entry to a message role, or ``None`` if it is not a turn."""
    subtype = _subtype(entry)
    if subtype in _SKIP:
        return None
    if subtype == "user_feedback":
        return "user"
    if subtype == "text":
        # The first say:text precedes any request and is the user's task.
        return "user" if entry is _first_text(entries) else "assistant"
    if subtype in {"completion_result", "followup"}:
        return "assistant"
    return None


def _first_text(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    for entry in entries:
        if _subtype(entry) == "api_req_started":
            return None
        if _subtype(entry) == "text":
            return entry
    return None


def _build_messages(entries: list[dict[str, Any]]) -> Iterable[Message]:
    first_text = _first_text(entries)
    pending: list[Block] = []
    pending_ts: Any = None
    pending_usage: Usage | None = None
    model: str | None = None
    index = 0

    def flush() -> Message | None:
        nonlocal pending, pending_ts, pending_usage, index
        if not pending:
            return None
        message = Message(
            id=f"assistant-{index}",
            role="assistant",
            blocks=pending,
            started_at=parse_epoch_ms(pending_ts),
            model=model,
            usage=pending_usage,
        )
        pending, pending_ts, pending_usage = [], None, None
        index += 1
        return message

    for entry in entries:
        subtype = _subtype(entry)
        timestamp = entry.get("ts")

        if subtype in _SKIP:
            continue

        if subtype == "api_req_started":
            payload = _decode(entry.get("text"))
            usage = _usage_from_request(payload)
            if usage is not None:
                pending_usage = usage if pending_usage is None else pending_usage + usage
            provider = payload.get("inferenceProvider")
            if isinstance(provider, str) and provider:
                model = provider
            continue

        if subtype == "reasoning":
            text = str(entry.get("text") or "").strip()
            if text:
                pending_ts = pending_ts or timestamp
                pending.append(ThinkingBlock(text=text))
            continue

        if subtype in {"tool", "command"}:
            block = _tool_block(_decode(entry.get("text")))
            if block is not None:
                pending_ts = pending_ts or timestamp
                pending.append(block)
            continue

        if subtype == "user_feedback" or (subtype == "text" and entry is first_text):
            flushed = flush()
            if flushed is not None:
                yield flushed
            text = str(entry.get("text") or "").strip()
            if text:
                index += 1
                yield Message(
                    id=f"user-{index}",
                    role="user",
                    blocks=[TextBlock(text=text)],
                    started_at=parse_epoch_ms(timestamp),
                )
            continue

        if subtype in {"text", "completion_result"}:
            text = str(entry.get("text") or "").strip()
            if text:
                pending_ts = pending_ts or timestamp
                pending.append(TextBlock(text=text))
            continue

        if subtype == "followup":
            payload = _decode(entry.get("text"))
            question = str(payload.get("question") or "").strip()
            if question:
                pending_ts = pending_ts or timestamp
                pending.append(TextBlock(text=question))
            continue

    trailing = flush()
    if trailing is not None:
        yield trailing


def _usage_from_request(payload: dict[str, Any]) -> Usage | None:
    if not payload:
        return None
    if payload.get("usageMissing"):
        return None
    cost = payload.get("cost")
    return Usage(
        input_tokens=int(payload.get("tokensIn") or 0),
        output_tokens=int(payload.get("tokensOut") or 0),
        cached_tokens=int(payload.get("cacheReads") or 0),
        cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
    )


def _tool_block(payload: dict[str, Any]) -> ToolUseBlock | None:
    if not payload:
        return None
    name = str(payload.get("tool") or "tool")
    path = str(payload.get("path") or "")
    content = str(payload.get("content") or "")
    stats = payload.get("diffStats") if isinstance(payload.get("diffStats"), dict) else {}
    additions = int((stats or {}).get("added") or 0)
    deletions = int((stats or {}).get("removed") or 0)

    if name == "readFile":
        detail = FileReadDetail(path=path, content=content)
    elif name == "newFileCreated":
        # content is a unified diff against /dev/null.
        detail = FileEditDetail(
            path=path, unified_diff=content, additions=additions, deletions=deletions
        )
    elif name in {"editedExistingFile", "appliedDiff"}:
        detail = FileEditDetail(
            path=path,
            unified_diff=str(payload.get("diff") or content),
            additions=additions,
            deletions=deletions,
        )
    elif name == "deleteFile":
        detail = FileWriteDetail(path=path, content="")
    elif name in {"listFilesRecursive", "listFilesTopLevel", "searchFiles"}:
        detail = SearchDetail(query=path, output=content)
    else:
        detail = GenericDetail(input=payload, output=content)

    return ToolUseBlock(name=name, detail=detail)


#: Kilocode writes this in place of a real provider for locally-generated
#: messages (condense summaries and the like). It is not a vendor.
_PLACEHOLDER_PROVIDERS = {"<synthetic>", "synthetic", "none", "unknown"}


def _scan_usage(
    entries: list[dict[str, Any]],
) -> tuple[Usage, set[str], set[str]]:
    """Usage, providers and models from the ``api_req_started`` records.

    ``inferenceProvider`` is a *vendor* ("Minimax", "xAI"), not a model. It was
    previously stored in the summary's ``models`` field, so the pricing sync
    asked the catalog to price "Minimax" and reported it missing. The two are
    now kept apart, and Kilocode's ``<synthetic>`` placeholder is dropped.
    """
    total = Usage()
    providers: set[str] = set()
    models: set[str] = set()

    for entry in entries:
        if _subtype(entry) != "api_req_started":
            continue
        payload = _decode(entry.get("text"))
        usage = _usage_from_request(payload)
        if usage is not None:
            total = total + usage

        provider = payload.get("inferenceProvider")
        if isinstance(provider, str) and provider.lower() not in _PLACEHOLDER_PROVIDERS:
            providers.add(provider)

        # Kilocode has used several keys for this over time.
        for key in ("modelId", "model", "apiModelId", "modelID"):
            model = payload.get(key)
            if isinstance(model, str) and model.strip():
                models.add(model.strip())
                break

    return total, providers, models


def _derive_title(entries: list[dict[str, Any]]) -> str:
    first = _first_text(entries)
    if first is not None:
        text = str(first.get("text") or "").strip()
        if text:
            return text.splitlines()[0][:120]
    for entry in entries:
        if _subtype(entry) == "user_feedback":
            text = str(entry.get("text") or "").strip()
            if text:
                return text.splitlines()[0][:120]
    return "Untitled task"


def _derive_cwd(entries: list[dict[str, Any]]) -> str:
    """Recover the workspace from the absolute path on the first file tool."""
    for entry in entries:
        if _subtype(entry) not in {"tool", "command"}:
            continue
        payload = _decode(entry.get("text"))
        content = payload.get("content")
        path = payload.get("path")
        if isinstance(content, str) and isinstance(path, str) and content.endswith(path):
            return content[: -len(path)].rstrip("\\/")
    return ""


def _project_ref(task_dir: Path) -> ProjectRef:
    return ProjectRef(id=task_dir.name, name=task_dir.name[:8])
