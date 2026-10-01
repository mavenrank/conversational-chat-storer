"""Map opencode ``part`` rows onto typed blocks.

Part types observed in a real store (38,343 parts): ``tool``, ``step-start``,
``step-finish``, ``text``, ``reasoning``, ``compaction``, ``patch``, ``file``.

Reasoning is provider-dependent, which is why this lives in its own module:

===============  ===========================================================
provider          shape
===============  ===========================================================
anthropic         ``text`` populated, ``metadata.anthropic.signature``
deepseek & co.    ``text`` populated, no metadata
openai            ``text`` is ``**Caption**\\n\\nbody`` — or empty for the
                  opaque continuation chunks, which carry only
                  ``metadata.openai.itemId``
copilot           no usable text, only ``metadata.copilot.reasoningOpaque``
===============  ===========================================================

OpenAI's leading ``**Caption**`` is lifted into ``ThinkingBlock.subject``, which
gives it the same shape as Gemini's ``{subject, description}`` thoughts. Parts
with no readable text are dropped rather than rendered as empty accordions.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ccsweb.sources.trim import trim_tool_output
from ccsweb.models import (
    Block,
    CommandDetail,
    FileEditDetail,
    FileReadDetail,
    FileWriteDetail,
    GenericDetail,
    SearchDetail,
    SubagentDetail,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    Usage,
)

#: opencode prefixes a task tool's output with the child session id.
TASK_ID_RE = re.compile(r"^task_id:\s*(?P<sid>\S+)")

#: OpenAI reasoning captions: a bold first line acting as a heading.
_CAPTION_RE = re.compile(r"\A\s*\*\*(?P<caption>[^*\n]{1,120})\*\*\s*\n+(?P<body>.*)", re.DOTALL)

#: ``read`` tool output wraps file bodies and prefixes every line with "N: ".
_CONTENT_RE = re.compile(r"<content>\n?(?P<body>.*?)</content>", re.DOTALL)
_LINENO_RE = re.compile(r"^\s*\d+:\s?", re.MULTILINE)


def parse_reasoning(part: dict[str, Any]) -> ThinkingBlock | None:
    """Build a thinking block, or ``None`` when the part has no readable text."""
    text = str(part.get("text") or "").strip()
    if not text:
        # OpenAI/Copilot opaque continuation chunk — nothing to show.
        return None

    match = _CAPTION_RE.match(text)
    if match:
        return ThinkingBlock(
            subject=match.group("caption").strip(),
            text=match.group("body").strip(),
        )
    return ThinkingBlock(text=text)


def parse_text(part: dict[str, Any]) -> TextBlock | None:
    """Assistant prose. Synthetic parts are harness nudges, not model output."""
    if part.get("synthetic"):
        return None
    text = str(part.get("text") or "").strip()
    return TextBlock(text=text) if text else None


def parse_step_finish(part: dict[str, Any]) -> tuple[Usage | None, float | None]:
    """Extract usage from a ``step-finish`` part.

    This is the only place opencode records tokens and cost. The TUI skipped
    these parts as "metadata only", which is why opencode sessions had no usage
    numbers at all.
    """
    tokens = part.get("tokens")
    if not isinstance(tokens, dict):
        return None, None

    cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
    cost = part.get("cost")
    usage = Usage(
        input_tokens=int(tokens.get("input") or 0),
        output_tokens=int(tokens.get("output") or 0),
        thinking_tokens=int(tokens.get("reasoning") or 0),
        cached_tokens=int((cache or {}).get("read") or 0),
        cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
    )
    return usage, usage.cost_usd


def parse_tool(part: dict[str, Any]) -> ToolUseBlock:
    """Build a tool block with a typed detail payload."""
    name = str(part.get("tool") or "unknown")
    state = part.get("state") if isinstance(part.get("state"), dict) else {}
    raw_status = str(state.get("status") or "completed")
    status = raw_status if raw_status in {"pending", "running", "completed", "error"} else "completed"
    args = state.get("input") if isinstance(state.get("input"), dict) else {}
    output = state.get("output")
    output_text = output if isinstance(output, str) else json.dumps(output) if output else ""
    # Search tools return an entire prompt wrapping their results; keep only
    # the results. Done here so storage, API, UI and export all benefit.
    output_text = trim_tool_output(output_text)

    detail = _build_detail(name, args, output_text)
    error = state.get("error") if status == "error" else None

    return ToolUseBlock(
        tool_id=str(part.get("callID") or "") or None,
        name=name,
        status=status,  # type: ignore[arg-type]
        error=str(error) if error else None,
        detail=detail,
    )


def _build_detail(name: str, args: dict, output: str):
    if name == "read":
        return FileReadDetail(
            path=str(args.get("filePath") or ""),
            content=_clean_read_output(output),
        )

    if name == "write":
        return FileWriteDetail(
            path=str(args.get("filePath") or ""),
            content=str(args.get("content") or ""),
        )

    if name == "edit":
        return FileEditDetail(
            path=str(args.get("filePath") or ""),
            old_text=str(args.get("oldString") or ""),
            new_text=str(args.get("newString") or ""),
        )

    if name == "bash":
        return CommandDetail(
            command=str(args.get("command") or args.get("cmd") or ""),
            output=output,
        )

    if name == "task":
        return SubagentDetail(
            agent_type=str(args.get("subagent_type") or ""),
            description=str(args.get("description") or ""),
            prompt=str(args.get("prompt") or ""),
            result=_strip_task_result(output),
            child_session_id=extract_child_session_id(output),
        )

    if name in {"glob", "grep", "list", "webfetch", "websearch"}:
        return SearchDetail(
            query=str(
                args.get("pattern")
                or args.get("query")
                or args.get("url")
                or args.get("path")
                or ""
            ),
            output=output,
        )

    return GenericDetail(input=args, output=output)


def extract_child_session_id(output: str) -> str | None:
    """Read the ``task_id: ses_...`` prefix opencode writes on task output."""
    match = TASK_ID_RE.match(output.lstrip())
    return match.group("sid") if match else None


def _strip_task_result(output: str) -> str:
    """Unwrap ``<task_result>`` and drop the task_id preamble."""
    if "<task_result>" in output:
        body = output.split("<task_result>", 1)[1]
        return body.split("</task_result>", 1)[0].strip()
    return TASK_ID_RE.sub("", output.lstrip(), count=1).strip()


def _clean_read_output(output: str) -> str:
    """Unwrap ``<content>`` and strip the ``N: `` line-number gutter."""
    match = _CONTENT_RE.search(output)
    body = match.group("body") if match else output
    return _LINENO_RE.sub("", body)


def parse_part(part: dict[str, Any]) -> Block | None:
    """Dispatch one part to a block, or ``None`` if it carries no content."""
    kind = part.get("type")
    if kind == "text":
        return parse_text(part)
    if kind == "reasoning":
        return parse_reasoning(part)
    if kind == "tool":
        return parse_tool(part)
    # step-start/step-finish are handled by the caller; compaction/patch/file
    # carry no renderable conversation content.
    return None
