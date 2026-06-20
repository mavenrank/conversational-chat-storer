"""Textual TUI for CCS - Interactive chat viewer."""

import re
import sys
from datetime import datetime


from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal
from textual.widgets import Header, Footer, Static, Label
from textual.message import Message
from textual.reactive import reactive
from rich.markdown import Markdown

from ccs.readers import ClaudeReader, GeminiReader, OpenCodeReader, KilocodeReader
from ccs.models import (
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
    code_fence,
    close_fences,
    format_timestamp,
)
from rich.table import Table
from rich.text import Text


def get_all_readers():
    """Get all available readers."""
    return [
        ClaudeReader(),
        GeminiReader(),
        OpenCodeReader(),
        KilocodeReader(),
    ]


def list_all_sessions() -> list[dict]:
    """List sessions from all available tools."""
    all_sessions = []
    for reader in get_all_readers():
        if reader.is_available():
            try:
                sessions = reader.list_sessions()
                all_sessions.extend(sessions)
            except Exception:
                pass

    def get_sort_key(x):
        ts = x.get("start_time")
        if ts is None:
            return datetime.min
        if ts.tzinfo is not None:
            return ts.replace(tzinfo=None)
        return ts

    return sorted(all_sessions, key=get_sort_key, reverse=True)


def get_session(session_id: str):
    """Get a session by ID."""
    for reader in get_all_readers():
        if session_id.startswith(f"{reader.tool_name}_"):
            if reader.is_available():
                return reader.get_session(session_id)
    return None


class SessionSelected(Message):
    """Message sent when a session is selected."""

    def __init__(self, session_id: str, session_data: dict):
        super().__init__()
        self.session_id = session_id
        self.session_data = session_data


class SessionItem(Static):
    """A clickable session item in the sidebar."""

    DEFAULT_CSS = """
    SessionItem {
        padding: 0 1;
        padding-left: 2;
        margin-bottom: 1;
        width: 100%;
    }
    SessionItem:hover {
        background: $surface;
    }
    SessionItem.selected {
        background: $boost;
    }
    """

    selected = reactive(False)

    def __init__(self, session_data: dict, **kwargs):
        super().__init__(**kwargs)
        self.session_data = session_data
        self.session_id = session_data["session_id"]

    def render(self) -> str:
        title = self.session_data.get("title") or ""
        return title if title else f"[dim]{self.session_id[:20]}[/]"

    def on_click(self) -> None:
        self.post_message(SessionSelected(self.session_id, self.session_data))


class SessionHeader(Static):
    """Fixed session info header above chat area."""

    DEFAULT_CSS = """
    SessionHeader {
        width: 1fr;
        padding: 1 2;
        background: $surface;
        border-bottom: solid $primary;
    }
    """

    def show_session(self, session) -> None:
        if not session:
            self.update("")
            return
        title = session.title or session.session_id
        lines = [
            f"[bold]{title}[/]",
            f"[dim]Session:[/] {session.session_id}",
            f"[dim]Tool:[/] {session.tool_name}",
        ]
        if session.start_time:
            lines.append(
                f"[bold]Started:[/] {session.start_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        if session.working_directory:
            lines.append(f"[dim]Directory:[/] {session.working_directory}")
        self.update("\n".join(lines))


INITIAL_CHUNK = 30
SCROLL_CHUNK = 10


class LoadingIndicator(Static):
    """Loading indicator widget shown during lazy load."""

    DEFAULT_CSS = """
    LoadingIndicator {
        padding: 1 0;
        text-align: center;
        width: 100%;
    }
    """


class ChatArea(VerticalScroll):
    """Scrollable chat message area with lazy loading."""

    DEFAULT_CSS = """
    ChatArea {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._all_messages = []
        self._loaded_count = 0
        self._all_loaded = True
        self._loading_more = False
        self._mount_target = 0
        self._scroll_timer = None
        self._last_ts = None

    def on_mount(self) -> None:
        self._scroll_timer = self.set_interval(0.3, self._check_scroll)

    def _check_scroll(self) -> None:
        if self._all_loaded or self._loading_more or not self._all_messages:
            return
        max_y = self.max_scroll_y
        if max_y > 5 and self.scroll_y >= max_y - 5:
            self._load_more()

    def show_loading(self) -> None:
        self.remove_children()
        self._all_messages = []
        self._loaded_count = 0
        self._mount_target = 0
        self._all_loaded = True
        self._loading_more = False
        self.mount(LoadingIndicator("[dim]Loading session data...[/]"))

    def show_session(self, session) -> None:
        self.remove_children()
        self._all_messages = list(session.messages) if session else []
        self._loaded_count = 0
        self._mount_target = 0
        self._all_loaded = False
        self._loading_more = False
        self._last_ts = None

        if not session or not self._all_messages:
            if not session:
                self.mount(Static("[red]Session not found[/]"))
            self._all_loaded = True
            return

        self.scroll_y = 0
        self.mount(LoadingIndicator("[dim]Structuring messages...[/]"))
        self._mount_target = min(INITIAL_CHUNK, len(self._all_messages))
        self._mount_next()

    def _mount_next(self) -> None:
        if self._loaded_count >= self._mount_target:
            self._finish_batch()
            return
        self._mount_message(self._all_messages[self._loaded_count])
        self._loaded_count += 1
        self.call_later(self._mount_next)

    def _finish_batch(self) -> None:
        self._remove_loading_indicator()
        if self._loaded_count >= len(self._all_messages):
            self._all_loaded = True
        else:
            self.mount(LoadingIndicator("[dim]Scroll down to load more messages...[/]"))
        self._loading_more = False

    def _load_more(self) -> None:
        self._loading_more = True
        remaining = len(self._all_messages) - self._loaded_count
        if remaining <= 0:
            self._all_loaded = True
            self._loading_more = False
            return

        self._remove_loading_indicator()
        self.mount(LoadingIndicator("[dim]Loading more messages...[/]"))
        self._mount_target = min(
            self._loaded_count + SCROLL_CHUNK, len(self._all_messages)
        )
        self.call_later(self._mount_next)

    def _remove_loading_indicator(self) -> None:
        for w in self.query(LoadingIndicator):
            w.remove()

    def _mount_message(self, msg) -> None:
        """Render a single message as one markdown string, mount as one Static."""
        role = msg.role.upper()
        ts_str = format_timestamp(msg.timestamp, self._last_ts)
        self._last_ts = msg.timestamp
        model = msg.model

        if role == "USER":
            self.mount(Static(f"[bold blue]USER[/] [dim]{ts_str}[/]"))
        else:
            model_str = f" [dim]model: {model}[/]" if model else ""
            self.mount(
                Static(f"[bold green]ASSISTANT[/] [dim]{ts_str}[/]{model_str}")
            )

        content = close_fences(msg.content)
        parts = []
        pos = 0
        while pos < len(content):
            next_thinking = content.find(THINKING_MARKER, pos)
            next_fileread = content.find(FILEREAD_MARKER, pos)
            next_edit = content.find(EDIT_MARKER, pos)

            if next_thinking == -1 and next_fileread == -1 and next_edit == -1:
                remaining = content[pos:].strip()
                if remaining:
                    parts.append(remaining)
                    parts.append("")
                break

            candidates = [(t, "think") for t in [next_thinking] if t != -1]
            candidates += [(t, "read") for t in [next_fileread] if t != -1]
            candidates += [(t, "edit") for t in [next_edit] if t != -1]
            next_pos, marker_type = min(candidates, key=lambda x: x[0])

            before = content[pos:next_pos].strip()
            if before:
                parts.append(before)
                parts.append("")

            if marker_type == "think":
                end = content.find(THINKING_END_MARKER, next_pos)
                if end == -1:
                    end = len(content)
                inner = content[next_pos + len(THINKING_MARKER) : end].strip("\n ")
                parts.append("> **Thinking:**")
                for line in inner.split("\n"):
                    parts.append(f"> {line}")
                parts.append("")
                pos = end if end >= len(content) else end + len(THINKING_END_MARKER)
            elif marker_type == "read":
                end = content.find(FILEREAD_END_MARKER, next_pos)
                header_end = content.find(FILEREAD_MARKER_END, next_pos)
                if header_end == -1 or end == -1:
                    parts.append(content[next_pos:].strip())
                    break
                fpath = content[next_pos + len(FILEREAD_MARKER) : header_end]
                inner_start = header_end + len(FILEREAD_MARKER_END)
                inner = content[inner_start:end].strip("\n ")
                fence = code_fence(inner)
                parts.append(f"### Read: {fpath}")
                parts.append("")
                parts.append(fence)
                parts.append(inner)
                parts.append(fence)
                parts.append("")
                pos = end + len(FILEREAD_END_MARKER)
            else:
                end_marker = content.find(EDIT_END_MARKER, next_pos)
                if end_marker == -1:
                    parts.append(content[next_pos:].strip())
                    break
                header_end = content.find("-->", next_pos)
                if header_end == -1:
                    parts.append(content[next_pos:].strip())
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

                if parts:
                    self.mount(Static(Markdown("\n".join(parts))))
                    parts = []

                table = Table(
                    show_header=True, header_style="bold", title=f"Edit: {fpath}"
                )
                table.add_column("Removed", style="red", no_wrap=False)
                table.add_column("Added", style="green", no_wrap=False)
                table.add_row(old_str, new_str)
                self.mount(Static(table))
                pos = end_marker + len(EDIT_END_MARKER)

        if parts:
            self.mount(Static(Markdown("\n".join(parts))))
        self.mount(Static("[dim]" + "─" * 60 + "[/]"))


class SessionSidebar(Container):
    """Sidebar with list of sessions."""

    DEFAULT_CSS = """
    SessionSidebar {
        width: 40;
        dock: left;
        background: $surface;
        border-right: solid $primary;
        overflow-y: auto;
    }
    .sidebar-header {
        text-align: center;
        padding: 1;
        background: $primary;
        color: white;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sessions = []

    def compose(self) -> ComposeResult:
        yield Label("Sessions", classes="sidebar-header")

    def load_sessions(self, sessions: list[dict]) -> None:
        """Load sessions into sidebar."""
        self.sessions = sessions

        if not self.sessions:
            self.mount(Static("[dim]No sessions found[/]"))
            return

        for session_data in self.sessions:
            item = SessionItem(session_data)
            self.mount(item)


class CCSApp(App):
    """CCS TUI Application."""

    CSS = """
    Screen {
        layout: horizontal;
    }
    #chat-container {
        layout: vertical;
        width: 1fr;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("j", "scroll_down", "Scroll Down"),
        ("k", "scroll_up", "Scroll Up"),
        ("e", "export", "Export"),
    ]

    selected_session_id = reactive(None)

    def compose(self) -> ComposeResult:
        yield Header()
        yield SessionSidebar()
        with Container(id="chat-container"):
            yield SessionHeader()
            yield ChatArea()
        yield Footer()

    def on_mount(self) -> None:
        self.title = "CCS - Chat Viewer"
        # Load sessions on mount
        self._load_sessions()

    def _load_sessions(self) -> None:
        """Load sessions and display."""
        sidebar = self.query_one(SessionSidebar)
        sessions = list_all_sessions()
        sidebar.load_sessions(sessions)

        # Select first session if available
        if sessions:
            self.select_session(sessions[0]["session_id"])

    def on_session_selected(self, event: SessionSelected) -> None:
        self.select_session(event.session_id)

    def select_session(self, session_id: str) -> None:
        """Select and display a session."""
        self.selected_session_id = session_id

        # Update sidebar selection
        sidebar = self.query_one(SessionSidebar)
        for item in sidebar.query(SessionItem):
            item.selected = item.session_id == session_id

        # Update header
        header = self.query_one(SessionHeader)
        header.show_session(None)

        # Load session
        chat = self.query_one(ChatArea)
        chat.show_loading()

        # Use call_later to avoid blocking
        self.call_later(self._load_session, session_id)

    def _load_session(self, session_id: str) -> None:
        """Load and display a session."""
        session = get_session(session_id)
        header = self.query_one(SessionHeader)
        header.show_session(session)
        chat = self.query_one(ChatArea)
        chat.show_session(session)

    def action_refresh(self) -> None:
        """Refresh the session list."""
        sidebar = self.query_one(SessionSidebar)

        # Clear existing items
        for item in sidebar.query(SessionItem):
            item.remove()

        self._load_sessions()

    def action_scroll_down(self) -> None:
        self.query_one(ChatArea).scroll_relative(y=5)

    def action_scroll_up(self) -> None:
        self.query_one(ChatArea).scroll_relative(y=-5)

    def action_export(self) -> None:
        """Export current session to markdown file."""
        if not self.selected_session_id:
            return

        session = get_session(self.selected_session_id)
        if not session:
            return

        filename = f"{self.selected_session_id}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(session.to_markdown())

        self.notify(f"Exported to {filename}")


def run_tui():
    """Run the TUI application."""
    app = CCSApp()
    app.run()


if __name__ == "__main__":
    run_tui()
