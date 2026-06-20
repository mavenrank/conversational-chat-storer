"""Reader for Kilocode storage format."""

import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime

from ccs.models import (
    Session,
    Message,
    THINKING_MARKER,
    THINKING_END_MARKER,
    FILEREAD_MARKER,
    FILEREAD_MARKER_END,
    FILEREAD_END_MARKER,
    EDIT_MARKER,
    EDIT_OLD_START,
    EDIT_OLD_END,
    EDIT_NEW_START,
    EDIT_NEW_END,
    EDIT_END_MARKER,
)
from ccs.readers.base import BaseReader


def _clean_read_output(output: str) -> str:
    m = re.search(r"<content>\n?(.*?)</content>", output, re.DOTALL)
    if m:
        content = m.group(1)
        lines = []
        for line in content.split("\n"):
            lines.append(re.sub(r"^\d+:\s?", "", line))
        return "\n".join(lines)
    return output


def _wrap_thinking(text: str) -> str:
    return f"{THINKING_MARKER}\n{text}\n{THINKING_END_MARKER}"


class KilocodeReader(BaseReader):
    """Reads Kilocode chat history from ~/.local/share/kilo/"""

    tool_name = "kilocode"

    def __init__(self):
        self.storage_path = Path.home() / ".local" / "share" / "kilo"
        self.db_path = self.storage_path / "kilo.db"
        self.vscode_storage = (
            Path.home() / ".vscode" / "globalStorage" / "kilocode.kilo-code"
        )

    def is_available(self) -> bool:
        return self.db_path.exists() or self.vscode_storage.exists()

    def get_storage_path(self) -> Path:
        if self.db_path.exists():
            return self.storage_path
        return self.vscode_storage

    def list_sessions(self) -> list[dict]:
        sessions = []

        if self.db_path.exists():
            try:
                conn = sqlite3.connect(str(self.db_path), timeout=10.0)
                conn.execute("PRAGMA query_only = ON")
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, title, time_created, directory
                    FROM session
                    ORDER BY time_created DESC
                    LIMIT 100
                """)
                for row in cursor.fetchall():
                    timestamp_ms = row[2]
                    start_time = (
                        datetime.fromtimestamp(timestamp_ms / 1000)
                        if timestamp_ms
                        else None
                    )
                    sessions.append(
                        {
                            "session_id": f"kilocode_{row[0]}",
                            "tool_name": self.tool_name,
                            "start_time": start_time,
                            "source": str(self.db_path),
                            "title": row[1] or "",
                            "directory": row[3] or "",
                        }
                    )
                conn.close()
            except Exception as e:
                pass

        if self.vscode_storage.exists():
            tasks_path = self.vscode_storage / "tasks"
            if tasks_path.exists():
                for task_dir in tasks_path.iterdir():
                    if task_dir.is_dir():
                        messages_file = task_dir / "clineMessages.json"
                        if messages_file.exists():
                            try:
                                stat = messages_file.stat()
                                sessions.append(
                                    {
                                        "session_id": f"kilocode_vscode_{task_dir.name}",
                                        "tool_name": self.tool_name,
                                        "start_time": datetime.fromtimestamp(
                                            stat.st_mtime
                                        ),
                                        "source": str(messages_file),
                                    }
                                )
                            except Exception:
                                continue

        return sorted(
            sessions, key=lambda x: x.get("start_time") or datetime.min, reverse=True
        )

    def get_session(self, session_id: str) -> Session | None:
        if not session_id.startswith("kilocode_"):
            return None

        actual_id = session_id[9:]

        if self.db_path.exists():
            try:
                conn = sqlite3.connect(str(self.db_path), timeout=10.0)
                conn.execute("PRAGMA query_only = ON")
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT id, time_created, directory, title
                    FROM session
                    WHERE id = ?
                """,
                    (actual_id,),
                )
                session_row = cursor.fetchone()

                if not session_row:
                    conn.close()
                    return None

                cursor.execute(
                    """
                    SELECT id, time_created, data
                    FROM message
                    WHERE session_id = ?
                    ORDER BY time_created ASC
                """,
                    (actual_id,),
                )

                messages = []
                for msg_row in cursor.fetchall():
                    try:
                        msg_id = msg_row[0]
                        msg_data = json.loads(msg_row[2]) if msg_row[2] else {}
                        role = msg_data.get("role", "unknown")
                        model = msg_data.get("modelID", "")

                        content_parts = []
                        part_cursor = conn.cursor()
                        part_cursor.execute(
                            "SELECT data FROM part WHERE message_id = ? ORDER BY time_created ASC",
                            (msg_id,),
                        )
                        for part_row in part_cursor.fetchall():
                            try:
                                part_data = (
                                    json.loads(part_row[0]) if part_row[0] else {}
                                )
                                ptype = part_data.get("type", "")

                                if ptype == "text":
                                    text = part_data.get("text", "").strip()
                                    if text:
                                        content_parts.append(text)

                                elif ptype == "reasoning":
                                    text = part_data.get("text", "").strip()
                                    if text:
                                        content_parts.append(_wrap_thinking(text))

                                elif ptype == "tool":
                                    tool_name = part_data.get("tool", "unknown")
                                    state = part_data.get("state", {})
                                    status = state.get("status", "unknown")
                                    inp = state.get("input", {})
                                    output = state.get("output", "")

                                    if tool_name == "read":
                                        fpath = inp.get("filePath", "")
                                        clean = _clean_read_output(output)
                                        body = (
                                            f"{FILEREAD_MARKER}{fpath}{FILEREAD_MARKER_END}\n{clean}\n{FILEREAD_END_MARKER}"
                                            if clean
                                            else f"[Read: {fpath}]"
                                        )
                                    elif tool_name == "write":
                                        header = f"[Write: {inp.get('filePath', '')}]"
                                        content_written = inp.get("content", "")
                                        body = f"{header}\n```\n{content_written}\n```"
                                    elif tool_name == "edit":
                                        fpath = inp.get("filePath", "")
                                        old_str = inp.get("oldString", "")
                                        new_str = inp.get("newString", "")
                                        body = f"{EDIT_MARKER}{fpath}-->\n{EDIT_OLD_START}\n{old_str}\n{EDIT_OLD_END}\n{EDIT_NEW_START}\n{new_str}\n{EDIT_NEW_END}\n{EDIT_END_MARKER}"
                                    elif tool_name == "bash":
                                        cmd = inp.get("command", inp.get("cmd", ""))
                                        header = f"[Bash: {cmd[:120]}]"
                                        body = (
                                            f"{header}\n{output}" if output else header
                                        )
                                    elif tool_name == "task":
                                        desc = inp.get("description", "")
                                        agent = inp.get("subagent_type", "")
                                        header = f"[Subagent ({agent}): {desc}]"
                                        if "<task_result>" in str(output):
                                            result = (
                                                str(output)
                                                .split("<task_result>")[-1]
                                                .split("</task_result>")[0]
                                                .strip()
                                            )
                                            body = f"{header}\n{result}"
                                        else:
                                            body = (
                                                f"{header}\n{output}"
                                                if output
                                                else header
                                            )
                                    elif tool_name in ("webfetch", "websearch"):
                                        query = inp.get("url", inp.get("query", ""))
                                        header = f"[{tool_name}: {query}]"
                                        body = header
                                    elif tool_name == "glob":
                                        header = f"[Glob: {inp.get('pattern', '')}]"
                                        body = (
                                            f"{header}\n{output}" if output else header
                                        )
                                    else:
                                        header = f"[Tool ({tool_name})]"
                                        inp_str = (
                                            json.dumps(inp, indent=2) if inp else ""
                                        )
                                        body = (
                                            f"{header}\nInput: {inp_str}\nOutput: {str(output)[:300]}"
                                            if (inp_str or output)
                                            else header
                                        )

                                    if status == "error":
                                        body = f"{body}\n[ERROR: {state.get('error', 'unknown error')}]"

                                    content_parts.append(body)

                                elif ptype == "patch":
                                    files = part_data.get("files", [])
                                    if files:
                                        content_parts.append(
                                            f"[Patch applied to: {', '.join(files)}]"
                                        )

                                # skip: step-start, step-finish

                            except Exception:
                                continue

                        content = "\n\n".join(content_parts) if content_parts else ""

                        timestamp_ms = msg_row[1]
                        timestamp = (
                            datetime.fromtimestamp(timestamp_ms / 1000)
                            if timestamp_ms
                            else None
                        )
                        messages.append(
                            Message(
                                role=role,
                                content=content,
                                timestamp=timestamp,
                                model=model,
                            )
                        )
                    except:
                        continue

                conn.close()

                timestamp_ms = session_row[1]
                start_time = (
                    datetime.fromtimestamp(timestamp_ms / 1000)
                    if timestamp_ms
                    else None
                )

                return Session(
                    session_id=session_id,
                    tool_name=self.tool_name,
                    title=session_row[3] or "",
                    start_time=start_time,
                    messages=messages,
                    working_directory=session_row[2] or "",
                    source_path=str(self.db_path),
                )
            except Exception:
                pass

        if session_id.startswith("kilocode_vscode_"):
            actual_id = session_id[16:]
            tasks_path = self.vscode_storage / "tasks"
            if tasks_path.exists():
                task_dir = tasks_path / actual_id
                if task_dir.is_dir():
                    messages_file = task_dir / "clineMessages.json"
                    if messages_file.exists():
                        try:
                            with open(messages_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            messages = []
                            for msg in (
                                data
                                if isinstance(data, list)
                                else data.get("messages", [])
                            ):
                                messages.append(
                                    Message(
                                        role=msg.get("type", "unknown"),
                                        content=msg.get("text", msg.get("content", "")),
                                        timestamp=datetime.fromisoformat(
                                            msg["timestamp"]
                                        )
                                        if msg.get("timestamp")
                                        else None,
                                    )
                                )
                            return Session(
                                session_id=session_id,
                                tool_name=self.tool_name,
                                messages=messages,
                                source_path=str(messages_file),
                            )
                        except Exception:
                            pass

        return None
