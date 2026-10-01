"""Source adapter protocol.

Each supported tool implements one adapter. Adapters are read-only: they never
write to a tool's storage, so running ccsweb can never corrupt or lock a live
session.

Two-phase contract:

``list_sessions`` must be cheap. It is called on every list refresh and should
avoid parsing full transcripts.

``get_session`` is called for one session at a time and may do the expensive
work.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ccsweb.models import SessionDetail, SessionSummary, SourceId


class SourceAdapter(ABC):
    """Read chat history out of one tool's native storage."""

    #: Stable identifier used in composite session ids and API routes.
    source_id: SourceId

    #: Human-readable name for the UI.
    display_name: str

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or self.default_root()

    @staticmethod
    @abstractmethod
    def default_root() -> Path:
        """Where this tool stores data when not overridden by config."""

    def is_available(self) -> bool:
        """True when this tool's storage exists on this machine."""
        return self.root.exists()

    @abstractmethod
    def list_sessions(self) -> list[SessionSummary]:
        """Return every session, including subagent runs.

        Subagent runs must be flagged with ``is_subagent`` and
        ``parent_session_id`` rather than omitted, so the registry can attach
        them to their parent and the UI can still search them.
        """

    @abstractmethod
    def get_session(self, session_id: str) -> SessionDetail | None:
        """Load one full transcript, or ``None`` if it is unknown."""


class AdapterError(Exception):
    """Raised when a source's storage exists but cannot be read."""

    def __init__(self, source_id: str, message: str) -> None:
        super().__init__(f"[{source_id}] {message}")
        self.source_id = source_id
