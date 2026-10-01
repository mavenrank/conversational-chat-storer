"""Claude Code adapter.

Storage is one JSONL file per session::

    ~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl

The directory name is the working directory with path separators replaced by
dashes, e.g. ``C--Users-me-Repos-app``.

Record types observed in a real store (9,193 records across 7 transcripts):

``user`` / ``assistant``
    Turns. ``message`` holds an Anthropic-format message; ``message.content`` is
    either a plain string (user prompts) or a list of ``text`` / ``thinking`` /
    ``tool_use`` blocks.
``ai-title`` / ``custom-title``
    Session titles. Written repeatedly as the title is refined, so the *last*
    one wins. Using these beats deriving a title from the first prompt.
``attachment``
    Pasted or referenced files.
``last-prompt`` / ``queue-operation`` / ``mode`` / ``system``
    Bookkeeping, ignored.

**Tool results** do not live on the assistant turn. Claude Code emits the
``tool_use`` on the assistant record and the result on the *following user*
record as ``toolUseResult``, with a matching ``tool_result`` content block
carrying the ``tool_use_id``. Results are therefore collected in a first pass
and joined by id.

**Subagents** are flagged with ``isSidechain`` on records belonging to a
delegated run, spawned by the ``Task`` tool. The reference dataset contained
neither, so that path is implemented to the documented behaviour but is not
verified against real data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ccsweb.models import (
    Block,
    CommandDetail,
    FileEditDetail,
    FileReadDetail,
    FileWriteDetail,
    GenericDetail,
    Message,
    ProjectRef,
    SearchDetail,
    SessionDetail,
    SessionSummary,
    SubagentDetail,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    Usage,
)
from ccsweb.sources.base import SourceAdapter
from ccsweb.sources.trim import trim_tool_output
from ccsweb.util.jsonio import iter_jsonl
from ccsweb.util.time import parse_iso

_TURN_TYPES = {"user", "assistant"}
_TITLE_TYPES = ("custom-title", "ai-title")

_READ_TOOLS = {"Read", "NotebookRead"}
_WRITE_TOOLS = {"Write"}
_EDIT_TOOLS = {"Edit", "MultiEdit", "NotebookEdit"}
_COMMAND_TOOLS = {"Bash", "PowerShell", "BashOutput"}
_SEARCH_TOOLS = {"Glob", "Grep", "WebSearch", "WebFetch", "ToolSearch"}
_TASK_TOOLS = {"Task", "Agent"}


class ClaudeAdapter(SourceAdapter):
    source_id = "claude"
    display_name = "Claude Code"

    @staticmethod
    def default_root() -> Path:
        return Path.home() / ".claude"

    @property
    def _projects(self) -> Path:
        return self.root / "projects"

    def is_available(self) -> bool:
        return self._projects.is_dir()

    def _transcripts(self) -> list[Path]:
        if not self._projects.is_dir():
            return []
        return sorted(self._projects.glob("*/*.jsonl"), reverse=True)

    def _find(self, session_id: str) -> Path | None:
        for path in self._transcripts():
            if path.stem == session_id:
                return path
        return None

    # ------------------------------------------------------------------ #

    def list_sessions(self) -> list[SessionSummary]:
        """List one entry per *conversation*, not per transcript file.

        Claude Code writes a brand-new file every time a session is resumed or
        forked, and each file contains the entire prior history. On the
        reference store that turned a single conversation into seven sessions of
        963-1294 turns, all sharing the same first-message uuid and each a
        near-prefix of the next. Transcripts are grouped by that root uuid and
        only the longest is listed; the rest are attached as forks.
        """
        scans: list[tuple[str, _Scan]] = []
        for path in self._transcripts():
            scan = _scan(path)
            if scan is not None:
                scans.append((str(path), scan))

        lineages: dict[str, list[tuple[str, _Scan]]] = {}
        for path_str, scan in scans:
            key = scan.root_uuid or path_str
            lineages.setdefault(key, []).append((path_str, scan))

        sessions: list[SessionSummary] = []
        for members in lineages.values():
            # Longest transcript wins: it contains the others' history.
            members.sort(key=lambda m: m[1].turns, reverse=True)
            primary_path, primary = members[0]
            primary_id = Path(primary_path).stem

            sessions.append(
                self._summary(Path(primary_path), primary, fork_count=len(members) - 1)
            )
            for fork_path, fork_scan in members[1:]:
                summary = self._summary(Path(fork_path), fork_scan)
                summary.is_fork = True
                summary.fork_of = primary_id
                sessions.append(summary)

        return sessions

    def _summary(
        self, path: Path, scan: "_Scan", fork_count: int = 0
    ) -> SessionSummary:
        return SessionSummary(
            id=path.stem,
            source=self.source_id,
            title=scan.title,
            project=_project_ref(path.parent, scan.cwd),
            cwd=scan.cwd,
            created_at=scan.first_at,
            updated_at=scan.last_at,
            message_count=scan.turns,
            user_message_count=scan.user_turns,
            models=sorted(scan.models),
            usage=scan.usage,
            is_subagent=False,
            fork_count=fork_count,
            source_path=str(path),
        )

    def get_session(self, session_id: str) -> SessionDetail | None:
        path = self._find(session_id)
        if path is None:
            return None

        records = list(iter_jsonl(path))
        results = _collect_tool_results(records)
        messages = list(_build_messages(records, results))

        scan = _scan(path, records)
        forks = [
            s
            for s in self.list_sessions()
            if s.is_fork and s.fork_of == session_id
        ]
        # Same requestId dedupe as the scan — see _scan.
        usage = Usage()
        counted: set[str] = set()
        for message in messages:
            if message.usage is None:
                continue
            key = message.request_id or message.id
            if key and key in counted:
                continue
            if key:
                counted.add(key)
            usage = usage + message.usage

        return SessionDetail(
            id=session_id,
            source=self.source_id,
            title=scan.title if scan else session_id,
            project=_project_ref(path.parent, scan.cwd if scan else ""),
            cwd=scan.cwd if scan else "",
            created_at=scan.first_at if scan else None,
            updated_at=scan.last_at if scan else None,
            message_count=scan.turns if scan else len(messages),
            user_message_count=scan.user_turns if scan else 0,
            models=sorted({m.model for m in messages if m.model}),
            usage=usage,
            fork_count=len(forks),
            source_path=str(path),
            messages=messages,
            forks=forks,
        )


# ---------------------------------------------------------------------- #
# Cheap scan for the list view
# ---------------------------------------------------------------------- #


class _Scan:
    __slots__ = (
        "title", "cwd", "turns", "user_turns", "models", "usage",
        "first_at", "last_at", "root_uuid",
    )

    def __init__(self) -> None:
        self.title = ""
        self.cwd = ""
        self.turns = 0
        self.user_turns = 0
        #: uuid of the first turn. Shared by every transcript descended from the
        #: same original conversation, which is what makes fork grouping possible.
        self.root_uuid = ""
        self.models: set[str] = set()
        self.usage = Usage()
        self.first_at = None
        self.last_at = None


def _scan(path: Path, records: list[dict[str, Any]] | None = None) -> _Scan | None:
    scan = _Scan()
    first_prompt = ""
    source = records if records is not None else iter_jsonl(path)
    seen = False
    #: Claude Code splits one API response across several assistant records and
    #: repeats the identical usage object on each. Counting per record inflated
    #: the reference transcript 3.3x (776,718 vs 235,336 real output tokens), so
    #: usage is counted once per requestId.
    counted_requests: set[str] = set()

    for record in source:
        seen = True
        kind = record.get("type")

        if kind in _TITLE_TYPES:
            # Titles are rewritten as they are refined; keep the newest.
            scan.title = str(record.get("customTitle") or record.get("aiTitle") or "")
            continue

        if kind not in _TURN_TYPES:
            continue

        scan.turns += 1
        if kind == "user" and _is_human_prompt(record):
            scan.user_turns += 1
        if not scan.root_uuid and record.get("uuid"):
            scan.root_uuid = str(record["uuid"])
        if not scan.cwd and record.get("cwd"):
            scan.cwd = str(record["cwd"])

        stamp = parse_iso(record.get("timestamp"))
        if stamp:
            if scan.first_at is None:
                scan.first_at = stamp
            scan.last_at = stamp

        message = record.get("message")
        if not isinstance(message, dict):
            continue
        if model := message.get("model"):
            scan.models.add(str(model))
        request_id = str(record.get("requestId") or message.get("id") or "")
        if request_id and request_id in counted_requests:
            pass  # already counted this API response
        else:
            if request_id:
                counted_requests.add(request_id)
            usage = _parse_usage(message.get("usage"))
            if usage is not None:
                scan.usage = scan.usage + usage

        if not first_prompt and kind == "user" and not record.get("isMeta"):
            text = _plain_text(message.get("content"))
            if text:
                first_prompt = text.splitlines()[0][:120]

    if not seen:
        return None
    if not scan.title:
        scan.title = first_prompt or "Untitled session"
    return scan


def _is_human_prompt(record: dict[str, Any]) -> bool:
    """True only for turns the person actually typed.

    Claude Code files tool *results* as ``user`` records, so counting by role
    wildly overstates human input: on the reference transcript, 497 of 515
    "user" records were tool results and only 18 were real prompts. A result is
    identified by a ``tool_result`` block in its content.
    """
    if record.get("isMeta"):
        return False
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return not any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )
    return False


def _project_ref(directory: Path, cwd: str) -> ProjectRef:
    name = Path(cwd).name if cwd else directory.name
    return ProjectRef(id=directory.name, name=name, path=cwd)


# ---------------------------------------------------------------------- #
# Transcript construction
# ---------------------------------------------------------------------- #


def _collect_tool_results(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Map ``tool_use_id`` -> result payload.

    Claude Code puts the result on the user record that follows the assistant's
    tool call, so a first pass is needed before turns can be rendered.
    """
    results: dict[str, Any] = {}
    for record in records:
        if record.get("type") != "user":
            continue

        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_id = block.get("tool_use_id")
                    if tool_id:
                        # Prefer the structured payload when present.
                        results[tool_id] = record.get("toolUseResult") or block.get(
                            "content"
                        )
    return results


def _build_messages(
    records: list[dict[str, Any]], results: dict[str, Any]
) -> Iterable[Message]:
    for index, record in enumerate(records):
        kind = record.get("type")
        if kind not in _TURN_TYPES:
            continue
        if record.get("isMeta"):
            continue

        message = record.get("message")
        if not isinstance(message, dict):
            continue

        blocks = list(_build_blocks(message.get("content"), results))
        if not blocks:
            # Pure tool-result carrier — already folded into the calling turn.
            continue

        yield Message(
            id=str(record.get("uuid") or f"{kind}-{index}"),
            request_id=str(record.get("requestId") or message.get("id") or "") or None,
            role="assistant" if kind == "assistant" else "user",
            blocks=blocks,
            started_at=parse_iso(record.get("timestamp")),
            model=message.get("model"),
            provider="anthropic",
            usage=_parse_usage(message.get("usage")),
            is_sidechain=bool(record.get("isSidechain")),
        )


def _build_blocks(content: Any, results: dict[str, Any]) -> Iterable[Block]:
    if isinstance(content, str):
        text = content.strip()
        if text:
            yield TextBlock(text=text)
        return

    if not isinstance(content, list):
        return

    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")

        if kind == "text":
            text = str(block.get("text") or "").strip()
            if text:
                yield TextBlock(text=text)

        elif kind == "thinking":
            text = str(block.get("thinking") or "").strip()
            if text:
                yield ThinkingBlock(text=text)

        elif kind == "tool_use":
            yield _tool_block(block, results)

        # tool_result blocks are joined onto their tool_use and skipped here.


def _tool_block(block: dict[str, Any], results: dict[str, Any]) -> ToolUseBlock:
    name = str(block.get("name") or "tool")
    args = block.get("input") if isinstance(block.get("input"), dict) else {}
    tool_id = str(block.get("id") or "")
    raw_result = results.get(tool_id)
    output = trim_tool_output(_stringify_result(raw_result))
    is_error = isinstance(raw_result, dict) and bool(raw_result.get("is_error"))

    return ToolUseBlock(
        tool_id=tool_id or None,
        name=name,
        status="error" if is_error else "completed",
        detail=_build_detail(name, args, output, raw_result),
    )


def _build_detail(name: str, args: dict, output: str, raw: Any):
    if name in _READ_TOOLS:
        return FileReadDetail(path=str(args.get("file_path") or ""), content=output)

    if name in _WRITE_TOOLS:
        return FileWriteDetail(
            path=str(args.get("file_path") or ""),
            content=str(args.get("content") or ""),
        )

    if name in _EDIT_TOOLS:
        # MultiEdit carries a list; show the first edit and note the rest.
        edits = args.get("edits")
        if isinstance(edits, list) and edits:
            first = edits[0] if isinstance(edits[0], dict) else {}
            return FileEditDetail(
                path=str(args.get("file_path") or ""),
                old_text=str(first.get("old_string") or ""),
                new_text=str(first.get("new_string") or ""),
            )
        return FileEditDetail(
            path=str(args.get("file_path") or ""),
            old_text=str(args.get("old_string") or ""),
            new_text=str(args.get("new_string") or ""),
        )

    if name in _COMMAND_TOOLS:
        return CommandDetail(
            command=str(args.get("command") or ""),
            output=output,
        )

    if name in _TASK_TOOLS:
        return SubagentDetail(
            agent_type=str(args.get("subagent_type") or ""),
            description=str(args.get("description") or ""),
            prompt=str(args.get("prompt") or ""),
            result=output,
        )

    if name in _SEARCH_TOOLS:
        return SearchDetail(
            query=str(
                args.get("pattern") or args.get("query") or args.get("url") or ""
            ),
            output=output,
        )

    return GenericDetail(input=args, output=output)


def _stringify_result(result: Any) -> str:
    """Flatten Claude Code's several tool-result shapes into text."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result

    if isinstance(result, dict):
        # Bash and friends.
        if "stdout" in result or "stderr" in result:
            parts = [str(result.get("stdout") or "")]
            stderr = str(result.get("stderr") or "")
            if stderr:
                parts.append(stderr)
            return "\n".join(p for p in parts if p)
        for key in ("content", "text", "output", "result"):
            if key in result:
                return _stringify_result(result[key])
        if isinstance(result.get("file"), dict):
            return str(result["file"].get("content") or "")
        return ""

    if isinstance(result, list):
        parts = []
        for item in result:
            text = _stringify_result(item)
            if text:
                parts.append(text)
        return "\n".join(parts)

    return str(result)


def _parse_usage(usage: Any) -> Usage | None:
    """Anthropic usage, including the two separate cache counters."""
    if not isinstance(usage, dict):
        return None
    return Usage(
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cached_tokens=int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0),
    )


def _plain_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block.get("text") or "").strip()
    return ""
