"""Base reader class for tool storage parsers."""

from abc import ABC, abstractmethod

from pathlib import Path

from ccs.models import Session


class BaseReader(ABC):
    """Abstract base class for tool-specific readers."""

    tool_name: str = "unknown"

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this tool's storage exists."""
        pass

    @abstractmethod
    def list_sessions(self) -> list[dict]:
        """List available sessions with metadata."""
        pass

    @abstractmethod
    def get_session(self, session_id: str):
        """Load a specific session. Returns Session or None."""
        pass

    def get_storage_path(self) -> Path:
        """Override to return tool's storage path."""
        return Path.home()
