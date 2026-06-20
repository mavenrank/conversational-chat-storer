"""Data models for chat sessions."""

import re
from dataclasses import dataclass, field
from datetime import datetime

THINKING_MARKER = "<!--THINKING-->"
THINKING_END_MARKER = "<!--/THINKING-->"
FILEREAD_MARKER = "<!--FILEREAD:"
FILEREAD_MARKER_END = "FILEREAD-->"
FILEREAD_END_MARKER = "<!--/FILEREAD-->"
EDIT_MARKER = "<!--EDIT:"
EDIT_OLD_START = "<!--/OLD-->"
EDIT_OLD_END = "<!--/OLDEND-->"
EDIT_NEW_START = "<!--/NEW-->"
EDIT_NEW_END = "<!--/NEWEND-->"
EDIT_END_MARKER = "<!--/EDITEND-->"


def close_fences(text: str) -> str:
    """Ensure all backtick code fences in text are properly closed."""
    opens = text.count("```")
    if opens % 2 != 0:
        text += "\n```"
    return text


def format_timestamp(dt: datetime | None, prev_dt: datetime | None = None) -> str:
    if dt is None:
        return ""
    time_str = dt.strftime("%H:%M:%S")
    if prev_dt is None or dt.date() != prev_dt.date():
        return f"{dt.strftime('%Y-%m-%d')} {time_str}"
    return time_str


def code_fence(content: str, fence_chars: str = "~") -> str:
    """Return a fence string that does not appear in content."""
    fence = fence_chars * 3
    while fence in content:
        fence += fence_chars
    return fence


@dataclass
class Message:
    """Represents a single chat message."""

    role: str
    content: str
    timestamp: datetime | None = None
    model: str | None = None

    def __init__(
        self,
        role: str,
        content,
        timestamp: datetime | None = None,
        model: str | None = None,
    ):
        self.role = role
        if isinstance(content, list):
            self.content = "\n".join(str(item) for item in content)
        elif isinstance(content, dict):
            self.content = content.get("text", str(content))
        else:
            self.content = str(content) if content else ""
        self.timestamp = timestamp
        self.model = model

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "model": self.model,
        }


@dataclass
class Session:
    """Represents a chat session."""

    session_id: str
    tool_name: str
    title: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    messages: list[Message] = field(default_factory=list)
    working_directory: str = ""
    source_path: str = ""

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "title": self.title,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "messages": [m.to_dict() for m in self.messages],
            "working_directory": self.working_directory,
            "source_path": self.source_path,
        }

    def to_markdown(self) -> str:
        title = self.title or self.session_id
        lines = [
            f"# {title}",
            "",
            f"**Tool:** {self.tool_name}",
            f"**Session ID:** {self.session_id}",
        ]
        if self.start_time:
            lines.append(
                f"**Started:** {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        if self.working_directory:
            lines.append(f"**Working Directory:** {self.working_directory}")
        lines.extend(["", "---", "", "## Conversation", ""])

        last_ts = None
        for msg in self.messages:
            ts_str = format_timestamp(msg.timestamp, last_ts)
            last_ts = msg.timestamp
            role = msg.role.capitalize()
            model = msg.model
            model_str = f" (model: {model})" if model else ""
            lines.append(
                f"### {role} ({ts_str}){model_str}"
                if ts_str
                else f"### {role}{model_str}"
            )
            lines.append("")

            content = close_fences(msg.content)
            pos = 0
            while pos < len(content):
                next_thinking = content.find(THINKING_MARKER, pos)
                next_fileread = content.find(FILEREAD_MARKER, pos)
                next_edit = content.find(EDIT_MARKER, pos)

                if next_thinking == -1 and next_fileread == -1 and next_edit == -1:
                    remaining = content[pos:].strip()
                    if remaining:
                        lines.append(remaining)
                        lines.append("")
                    break

                # Find earliest marker
                candidates = [(t, "think") for t in [next_thinking] if t != -1]
                candidates += [(t, "read") for t in [next_fileread] if t != -1]
                candidates += [(t, "edit") for t in [next_edit] if t != -1]
                next_pos, marker_type = min(candidates, key=lambda x: x[0])

                before = content[pos:next_pos].strip()
                if before:
                    lines.append(before)
                    lines.append("")

                if marker_type == "think":
                    end = content.find(THINKING_END_MARKER, next_pos)
                    if end == -1:
                        end = len(content)
                    inner = content[next_pos + len(THINKING_MARKER) : end].strip("\n ")
                    lines.append("> **Thinking:**")
                    for line in inner.strip().split("\n"):
                        lines.append(f"> {line}")
                    lines.append("")
                    pos = end if end >= len(content) else end + len(THINKING_END_MARKER)
                elif marker_type == "read":
                    end = content.find(FILEREAD_END_MARKER, next_pos)
                    header_end = content.find(FILEREAD_MARKER_END, next_pos)
                    if header_end == -1 or end == -1:
                        lines.append(content[next_pos:].strip())
                        break
                    header = content[next_pos + len(FILEREAD_MARKER) : header_end]
                    inner_start = header_end + len(FILEREAD_MARKER_END)
                    inner = content[inner_start:end].strip("\n ")
                    fence = code_fence(inner)
                    lines.append(f"### Read: {header}")
                    lines.append("")
                    lines.append(fence)
                    lines.append(inner)
                    lines.append(fence)
                    lines.append("")
                    pos = end + len(FILEREAD_END_MARKER)
                else:
                    end_marker = content.find(EDIT_END_MARKER, next_pos)
                    if end_marker == -1:
                        lines.append(content[next_pos:].strip())
                        break
                    header_end = content.find("-->", next_pos)
                    if header_end == -1:
                        lines.append(content[next_pos:].strip())
                        break
                    fpath = content[next_pos + len(EDIT_MARKER) : header_end]
                    old_start = content.find(EDIT_OLD_START, next_pos)
                    old_end = content.find(EDIT_OLD_END, next_pos)
                    new_start = content.find(EDIT_NEW_START, next_pos)
                    new_end = content.find(EDIT_NEW_END, next_pos)
                    old_str = content[old_start + len(EDIT_OLD_START) : old_end].strip(
                        "\n "
                    )
                    new_str = content[new_start + len(EDIT_NEW_START) : new_end].strip(
                        "\n "
                    )
                    lines.append(f"### Edit: {fpath}")
                    lines.append("")
                    lines.append("```diff")
                    for line in old_str.split("\n"):
                        lines.append(f"-{line}")
                    for line in new_str.split("\n"):
                        lines.append(f"+{line}")
                    lines.append("```")
                    lines.append("")
                    pos = end_marker + len(EDIT_END_MARKER)

            lines.append("---")
            lines.append("")

        return "\n".join(lines)
