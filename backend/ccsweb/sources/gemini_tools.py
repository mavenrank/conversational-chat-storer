"""Map Gemini CLI ``toolCalls`` entries onto typed tool blocks.

A Gemini tool call looks like::

    {
      "id": "read_file-1770484238025-f35d8178f982d",
      "name": "read_file",
      "args": {"file_path": "backend/app/api/v1/chat.py"},
      "result": [{"functionResponse": {"response": {"output": "..."}}}]
    }

Gemini has no dedicated subagent record: a delegated run surfaces as an ordinary
tool call whose output begins ``Subagent '<name>' finished.``. We detect that
shape so those calls render as subagent cards rather than walls of text.
"""

from __future__ import annotations

import re
from typing import Any

from ccsweb.models import (
    CommandDetail,
    FileEditDetail,
    FileReadDetail,
    FileWriteDetail,
    GenericDetail,
    SearchDetail,
    SubagentDetail,
    ToolUseBlock,
)

_SUBAGENT_RE = re.compile(r"^Subagent '(?P<name>[^']+)' finished\.", re.MULTILINE)

_READ_TOOLS = {"read_file", "read_many_files"}
_WRITE_TOOLS = {"write_file"}
_EDIT_TOOLS = {"replace", "edit_file"}
_COMMAND_TOOLS = {"run_shell_command"}
_SEARCH_TOOLS = {"glob", "search_file_content", "google_web_search", "web_fetch"}


def build_tool_block(call: Any) -> ToolUseBlock | None:
    """Convert one raw tool call into a block, or ``None`` if unusable."""
    if not isinstance(call, dict):
        return None

    name = str(call.get("name") or "unknown")
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    output = _extract_output(call.get("result"))
    status = "error" if _looks_like_error(output) else "completed"

    detail = _build_detail(name, args, output)
    return ToolUseBlock(
        tool_id=str(call.get("id") or "") or None,
        name=name,
        status=status,  # type: ignore[arg-type]
        detail=detail,
    )


def _build_detail(name: str, args: dict, output: str):
    subagent = _SUBAGENT_RE.search(output)
    if subagent:
        return SubagentDetail(
            agent_type=subagent.group("name"),
            description=str(args.get("objective") or args.get("description") or ""),
            prompt=str(args.get("prompt") or args.get("objective") or ""),
            result=_strip_subagent_preamble(output),
        )

    if name in _READ_TOOLS:
        return FileReadDetail(
            path=str(args.get("file_path") or args.get("path") or ""),
            content=output,
        )

    if name in _WRITE_TOOLS:
        return FileWriteDetail(
            path=str(args.get("file_path") or args.get("path") or ""),
            content=str(args.get("content") or ""),
        )

    if name in _EDIT_TOOLS:
        return FileEditDetail(
            path=str(args.get("file_path") or args.get("path") or ""),
            old_text=str(args.get("old_string") or args.get("oldString") or ""),
            new_text=str(args.get("new_string") or args.get("newString") or ""),
        )

    if name in _COMMAND_TOOLS:
        return CommandDetail(
            command=str(args.get("command") or ""),
            output=output,
        )

    if name in _SEARCH_TOOLS:
        return SearchDetail(
            query=str(
                args.get("pattern")
                or args.get("query")
                or args.get("url")
                or ""
            ),
            output=output,
        )

    return GenericDetail(input=args, output=output)


def _extract_output(result: Any) -> str:
    """Pull the text payload out of Gemini's nested functionResponse wrapper."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result

    if isinstance(result, list):
        parts: list[str] = []
        for item in result:
            text = _extract_output(item)
            if text:
                parts.append(text)
        return "\n".join(parts)

    if isinstance(result, dict):
        response = result.get("functionResponse")
        if isinstance(response, dict):
            return _extract_output(response.get("response"))
        for key in ("output", "text", "content"):
            value = result.get(key)
            if isinstance(value, str):
                return value
        return ""

    return str(result)


def _strip_subagent_preamble(output: str) -> str:
    """Drop the ``Subagent ... / Termination Reason: ... / Result:`` header."""
    marker = "Result:"
    index = output.find(marker)
    if index != -1:
        return output[index + len(marker) :].strip()
    return output.strip()


def _looks_like_error(output: str) -> bool:
    head = output.lstrip()[:80].lower()
    return head.startswith("error") or head.startswith("failed")
