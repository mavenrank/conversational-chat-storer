"""Reader for Gemini CLI storage format."""

import json
import hashlib
from pathlib import Path

from datetime import datetime

from ccs.models import Session, Message
from ccs.readers.base import BaseReader


class GeminiReader(BaseReader):
    """Reads Gemini CLI chat history from ~/.gemini/"""

    tool_name = "gemini"

    def __init__(self):
        self.storage_path = Path.home() / ".gemini"
        self.tmp_path = self.storage_path / "tmp"

    def is_available(self) -> bool:
        return self.storage_path.exists()

    def get_storage_path(self) -> Path:
        return self.storage_path

    def _get_project_hash(self, cwd: str = None) -> str:
        if cwd:
            return hashlib.md5(cwd.encode()).hexdigest()[:12]
        return ""

    def list_sessions(self) -> list[dict]:
        sessions = []
        seen_ids = set()

        if not self.tmp_path.exists():
            return sessions

        for project_dir in self.tmp_path.iterdir():
            if project_dir.is_dir():
                chats_path = project_dir / "chats"
                if chats_path.exists():
                    for chat_file in chats_path.glob("*.json"):
                        # Deduplicate by session ID (filename)
                        session_id = f"gemini_{chat_file.stem}"
                        if session_id in seen_ids:
                            continue
                        seen_ids.add(session_id)

                        try:
                            with open(chat_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            sessions.append(
                                {
                                    "session_id": session_id,
                                    "tool_name": self.tool_name,
                                    "start_time": datetime.fromisoformat(
                                        data.get("startTime", "")
                                    )
                                    if data.get("startTime")
                                    else None,
                                    "source": str(chat_file),
                                    "project_hash": project_dir.name,
                                }
                            )
                        except Exception:
                            continue

        return sorted(
            sessions, key=lambda x: x.get("start_time") or datetime.min, reverse=True
        )

    def get_session(self, session_id: str) -> Session | None:
        if not session_id.startswith("gemini_"):
            return None

        actual_id = session_id[7:]

        if not self.tmp_path.exists():
            return None

        for project_dir in self.tmp_path.iterdir():
            if project_dir.is_dir():
                chats_path = project_dir / "chats"
                if chats_path.exists():
                    chat_file = chats_path / f"{actual_id}.json"
                    if chat_file.exists():
                        try:
                            with open(chat_file, "r", encoding="utf-8") as f:
                                data = json.load(f)

                            messages = []
                            for msg in data.get("messages", []):
                                # Gemini uses 'type' field: user, gemini, info, error
                                msg_type = msg.get("type", "unknown")
                                if msg_type == "user":
                                    role = "user"
                                elif msg_type == "gemini":
                                    role = "assistant"
                                else:
                                    role = msg_type  # info, error, etc.

                                messages.append(
                                    Message(
                                        role=role,
                                        content=msg.get("content", ""),
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
                                start_time=datetime.fromisoformat(
                                    data.get("startTime", "")
                                )
                                if data.get("startTime")
                                else None,
                                end_time=datetime.fromisoformat(data.get("endTime", ""))
                                if data.get("endTime")
                                else None,
                                messages=messages,
                                working_directory=data.get("cwd", ""),
                                source_path=str(chat_file),
                            )
                        except Exception:
                            pass

        return None
