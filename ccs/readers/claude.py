"""Reader for Claude Code storage format."""

import json
from pathlib import Path

from datetime import datetime

from ccs.models import Session, Message
from ccs.readers.base import BaseReader


class ClaudeReader(BaseReader):
    """Reads Claude Code chat history from ~/.claude/"""

    tool_name = "claude"

    def __init__(self):
        self.storage_path = Path.home() / ".claude"
        self.history_file = self.storage_path / "history.jsonl"
        self.projects_path = self.storage_path / "projects"

    def is_available(self) -> bool:
        return self.storage_path.exists()

    def get_storage_path(self) -> Path:
        return self.storage_path

    def list_sessions(self) -> list[dict]:
        sessions = []

        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            session_id = entry.get("sessionId", f"history_{line_num}")
                            timestamp = entry.get("timestamp")

                            sessions.append(
                                {
                                    "session_id": f"claude_{session_id}",
                                    "tool_name": self.tool_name,
                                    "start_time": datetime.fromisoformat(timestamp)
                                    if timestamp
                                    else None,
                                    "source": str(self.history_file),
                                    "line_number": line_num,
                                }
                            )
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass

        if self.projects_path.exists():
            for project_dir in self.projects_path.iterdir():
                if project_dir.is_dir():
                    for session_dir in project_dir.iterdir():
                        if session_dir.is_dir():
                            session_file = session_dir / "session.json"
                            if session_file.exists():
                                try:
                                    with open(session_file, "r", encoding="utf-8") as f:
                                        data = json.load(f)
                                    sessions.append(
                                        {
                                            "session_id": f"claude_{session_dir.name}",
                                            "tool_name": self.tool_name,
                                            "start_time": datetime.fromisoformat(
                                                data.get("startTime", "")
                                            )
                                            if data.get("startTime")
                                            else None,
                                            "source": str(session_file),
                                            "project": project_dir.name,
                                        }
                                    )
                                except Exception:
                                    continue

        return sorted(
            sessions, key=lambda x: x.get("start_time") or datetime.min, reverse=True
        )

    def get_session(self, session_id: str) -> Session | None:
        if not session_id.startswith("claude_"):
            return None

        actual_id = session_id[7:]

        if self.projects_path.exists():
            for project_dir in self.projects_path.iterdir():
                if project_dir.is_dir():
                    session_dir = project_dir / actual_id
                    if session_dir.is_dir():
                        session_file = session_dir / "session.json"
                        messages_file = session_dir / "messages.jsonl"

                        if session_file.exists():
                            try:
                                with open(session_file, "r", encoding="utf-8") as f:
                                    data = json.load(f)

                                messages = []
                                if messages_file.exists():
                                    with open(
                                        messages_file, "r", encoding="utf-8"
                                    ) as f:
                                        for line in f:
                                            line = line.strip()
                                            if not line:
                                                continue
                                            try:
                                                msg_data = json.loads(line)
                                                role = (
                                                    "user"
                                                    if msg_data.get("role") == "human"
                                                    else "assistant"
                                                )
                                                messages.append(
                                                    Message(
                                                        role=role,
                                                        content=msg_data.get(
                                                            "content", ""
                                                        ),
                                                        timestamp=datetime.fromisoformat(
                                                            msg_data["timestamp"]
                                                        )
                                                        if msg_data.get("timestamp")
                                                        else None,
                                                    )
                                                )
                                            except:
                                                continue

                                return Session(
                                    session_id=session_id,
                                    tool_name=self.tool_name,
                                    start_time=datetime.fromisoformat(
                                        data.get("startTime", "")
                                    )
                                    if data.get("startTime")
                                    else None,
                                    end_time=datetime.fromisoformat(
                                        data.get("endTime", "")
                                    )
                                    if data.get("endTime")
                                    else None,
                                    messages=messages,
                                    working_directory=data.get("cwd", ""),
                                    source_path=str(session_file),
                                )
                            except Exception:
                                pass

        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get("sessionId") == actual_id:
                                messages = []
                                content = entry.get("content", "")
                                role = (
                                    "user"
                                    if entry.get("role") == "human"
                                    else "assistant"
                                )
                                messages.append(
                                    Message(
                                        role=role,
                                        content=content,
                                        timestamp=datetime.fromisoformat(
                                            entry["timestamp"]
                                        )
                                        if entry.get("timestamp")
                                        else None,
                                    )
                                )
                                return Session(
                                    session_id=session_id,
                                    tool_name=self.tool_name,
                                    start_time=datetime.fromisoformat(
                                        entry["timestamp"]
                                    )
                                    if entry.get("timestamp")
                                    else None,
                                    messages=messages,
                                    source_path=str(self.history_file),
                                )
                        except:
                            continue
            except:
                pass

        return None
