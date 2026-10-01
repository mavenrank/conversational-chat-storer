"""Markdown export.

Output format is carried over from the TUI's exporter — headed sections per
turn, thinking as a blockquote, reads in a fence chosen to not collide with the
content, edits as a ``diff`` fence. The difference is the input: the TUI parsed
marker strings back out of prose, this walks the structured blocks directly, so
there is nothing to mis-parse.
"""

from __future__ import annotations

from datetime import datetime

from ccsweb.models import Message, SessionDetail


def session_to_markdown(session: SessionDetail) -> str:
    lines: list[str] = [
        f"# {session.title or session.id}",
        "",
        f"**Source:** {session.source}",
        f"**Session ID:** {session.id}",
    ]
    if session.created_at:
        lines.append(f"**Started:** {session.created_at:%Y-%m-%d %H:%M:%S}")
    if session.cwd:
        lines.append(f"**Working Directory:** {session.cwd}")
    if session.models:
        lines.append(f"**Models:** {', '.join(session.models)}")
    if session.usage.total_tokens:
        lines.append(f"**Tokens:** {session.usage.total_tokens:,}")
    if session.usage.cost_usd:
        lines.append(f"**Estimated cost:** ${session.usage.cost_usd:.4f}")

    lines += ["", "---", "", "## Conversation", ""]

    previous: datetime | None = None
    for message in session.messages:
        lines.extend(_render_message(message, previous))
        previous = message.started_at or previous

    return "\n".join(lines)


def _render_message(message: Message, previous: datetime | None) -> list[str]:
    stamp = _format_timestamp(message.started_at, previous)
    heading = f"### {message.role.capitalize()}"
    if stamp:
        heading += f" ({stamp})"
    if message.model:
        heading += f" (model: {message.model})"

    lines = [heading, ""]

    meta: list[str] = []
    if (duration := message.duration_ms) is not None:
        meta.append(f"took {duration / 1000:.1f}s")
    if message.usage and message.usage.total_tokens:
        meta.append(f"{message.usage.total_tokens:,} tokens")
    if message.usage and message.usage.cost_usd:
        meta.append(f"${message.usage.cost_usd:.4f}")
    if meta:
        lines += [f"*{' · '.join(meta)}*", ""]

    for block in message.blocks:
        lines.extend(_render_block(block))

    lines += ["---", ""]
    return lines


def _render_block(block) -> list[str]:
    if block.kind == "text":
        return [_close_fences(block.text), ""]

    if block.kind == "thinking":
        lines = []
        if block.subject:
            lines.append(f"> **Thinking — {block.subject}**")
        else:
            lines.append("> **Thinking:**")
        for line in block.text.strip().splitlines():
            lines.append(f"> {line}")
        lines.append("")
        return lines

    return _render_tool(block)


def _render_tool(block) -> list[str]:
    detail = block.detail
    category = detail.category

    if category == "file_read":
        # A read's content is the file, which the reader already has. Exporting
        # it in full is what makes transcripts unreadable — a single session can
        # carry hundreds of these. Record what was read and how much.
        size = len(detail.content.encode("utf-8")) if detail.content else detail.size_bytes
        lines = [f"#### Read: {detail.path}", ""]
        if size:
            lines.append(f"*{size:,} bytes*")
            lines.append("")
        return lines

    if category == "file_write":
        fence = _fence_for(detail.content)
        return [
            f"#### Write: {detail.path}",
            "",
            fence,
            detail.content,
            fence,
            "",
        ]

    if category == "file_edit":
        body = detail.unified_diff or _diff_from_strings(detail)
        return [f"#### Edit: {detail.path}", "", "```diff", body, "```", ""]

    if category == "command":
        lines = [f"#### Command", "", "```bash", detail.command, "```", ""]
        if detail.output:
            fence = _fence_for(detail.output)
            lines += [fence, detail.output, fence, ""]
        return lines

    if category == "search":
        lines = [f"#### {block.name}: {detail.query}", ""]
        if detail.output:
            fence = _fence_for(detail.output)
            lines += [fence, detail.output, fence, ""]
        return lines

    if category == "subagent":
        header = f"#### Subagent ({detail.agent_type})"
        if detail.description:
            header += f": {detail.description}"
        lines = [header, ""]
        if detail.result:
            lines += [detail.result, ""]
        return lines

    lines = [f"#### Tool: {block.name}", ""]
    if detail.output:
        fence = _fence_for(detail.output)
        lines += [fence, detail.output, fence, ""]
    return lines


def _diff_from_strings(detail) -> str:
    lines = [f"-{line}" for line in detail.old_text.splitlines()]
    lines += [f"+{line}" for line in detail.new_text.splitlines()]
    return "\n".join(lines)


def _fence_for(content: str, char: str = "~") -> str:
    """Pick a fence that cannot appear inside ``content``."""
    fence = char * 3
    while fence in content:
        fence += char
    return fence


def _close_fences(text: str) -> str:
    """Balance stray backtick fences so they cannot swallow the rest of the doc."""
    if text.count("```") % 2 != 0:
        return text + "\n```"
    return text


def _format_timestamp(value: datetime | None, previous: datetime | None) -> str:
    if value is None:
        return ""
    time_part = value.strftime("%H:%M:%S")
    if previous is None or value.date() != previous.date():
        return f"{value:%Y-%m-%d} {time_part}"
    return time_part
