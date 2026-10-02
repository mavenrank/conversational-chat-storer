"""Adapter registry.

Owns the set of configured adapters, merges their listings into one timeline,
and applies the rules that are the whole point of this app:

* Subagent runs are hidden from the default listing and attached to their
  parent instead.
* A session is addressed globally as ``<source>:<native-id>``, because native
  ids only need to be unique within their own tool.
* One broken source never takes down the listing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from time import monotonic

from ccsweb.config import Settings, get_settings
from ccsweb.models import SessionDetail, SessionSummary
from ccsweb.sources.base import SourceAdapter
from ccsweb.sources.claude import ClaudeAdapter
from ccsweb.sources.codex import CodexAdapter
from ccsweb.sources.gemini import GeminiAdapter
from ccsweb.sources.kilocode import KilocodeAdapter
from ccsweb.sources.opencode import OpenCodeAdapter

SEPARATOR = ":"


@dataclass
class SourceStatus:
    """What the UI shows in the sources sidebar."""

    id: str
    display_name: str
    available: bool
    root: str
    session_count: int = 0
    error: str | None = None


@dataclass
class Registry:
    adapters: dict[str, SourceAdapter] = field(default_factory=dict)
    index_ttl_seconds: float = 5
    _index: dict[str, tuple[float, list[SessionSummary]]] = field(default_factory=dict, init=False)
    _index_lock: RLock = field(default_factory=RLock, init=False, repr=False)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> Registry:
        settings = settings or get_settings()
        adapters: list[SourceAdapter] = [
            ClaudeAdapter(settings.claude_root),
            OpenCodeAdapter(settings.opencode_root),
            GeminiAdapter(settings.gemini_root),
            KilocodeAdapter(settings.kilocode_root),
            CodexAdapter(settings.codex_root),
        ]
        return cls(
            adapters={a.source_id: a for a in adapters},
            index_ttl_seconds=settings.index_ttl_seconds,
        )

    def _sessions(self, adapter: SourceAdapter) -> list[SessionSummary]:
        # Sources, timeline and statistics arrive concurrently on first load.
        # Coalesce their scans and cache native IDs, never mutated API objects.
        with self._index_lock:
            cached = self._index.get(adapter.source_id)
            if cached and monotonic() - cached[0] < self.index_ttl_seconds:
                return cached[1]
            sessions = adapter.list_sessions()
            self._index[adapter.source_id] = monotonic(), sessions
            return sessions

    # ------------------------------------------------------------------ #

    def statuses(self) -> list[SourceStatus]:
        result = []
        for adapter in self.adapters.values():
            status = SourceStatus(
                id=adapter.source_id,
                display_name=adapter.display_name,
                available=adapter.is_available(),
                root=str(adapter.root),
            )
            if status.available:
                try:
                    status.session_count = sum(
                        1
                        for s in self._sessions(adapter)
                        if not s.is_subagent and not s.is_approval_review and not s.is_fork
                    )
                except Exception as exc:  # noqa: BLE001 - surfaced in the UI
                    status.available = False
                    status.error = str(exc)
            result.append(status)
        return result

    def list_sessions(
        self,
        sources: list[str] | None = None,
        include_subagents: bool = False,
        include_approval_reviews: bool = False,
        include_forks: bool = False,
    ) -> list[SessionSummary]:
        """Merged, newest-first listing across sources."""
        merged: list[SessionSummary] = []
        for source_id, adapter in self.adapters.items():
            if sources and source_id not in sources:
                continue
            if not adapter.is_available():
                continue
            try:
                sessions = self._sessions(adapter)
            except Exception:  # noqa: BLE001 - a broken source must not break the list
                continue
            for session in sessions:
                if session.is_subagent and not include_subagents:
                    continue
                if session.is_approval_review and not include_approval_reviews:
                    continue
                # Resume/fork transcripts duplicate a conversation's whole
                # history; only the longest is listed.
                if session.is_fork and not include_forks:
                    continue
                session = session.model_copy(deep=True)
                session.id = make_global_id(source_id, session.id)
                if session.parent_session_id:
                    session.parent_session_id = make_global_id(source_id, session.parent_session_id)
                if session.fork_of:
                    session.fork_of = make_global_id(source_id, session.fork_of)
                merged.append(session)

        merged.sort(key=_sort_key, reverse=True)
        return merged

    def get_session(self, global_id: str) -> SessionDetail | None:
        parsed = split_global_id(global_id)
        if parsed is None:
            return None
        source_id, native_id = parsed
        adapter = self.adapters.get(source_id)
        if adapter is None or not adapter.is_available():
            return None

        session = adapter.get_session(native_id)
        if session is None:
            return None

        session = session.model_copy(deep=True)

        session.id = make_global_id(source_id, session.id)
        if session.parent_session_id:
            session.parent_session_id = make_global_id(source_id, session.parent_session_id)
        if session.fork_of:
            session.fork_of = make_global_id(source_id, session.fork_of)
        for child in list(session.subagents) + list(session.approval_reviews) + list(session.forks):
            child.id = make_global_id(source_id, child.id)
            if child.parent_session_id:
                child.parent_session_id = make_global_id(source_id, child.parent_session_id)
            if child.fork_of:
                child.fork_of = make_global_id(source_id, child.fork_of)
        return session


def make_global_id(source_id: str, native_id: str) -> str:
    if native_id.startswith(f"{source_id}{SEPARATOR}"):
        return native_id
    return f"{source_id}{SEPARATOR}{native_id}"


def split_global_id(global_id: str) -> tuple[str, str] | None:
    source_id, separator, native_id = global_id.partition(SEPARATOR)
    if not separator or not native_id:
        return None
    return source_id, native_id


def _sort_key(session: SessionSummary):
    from datetime import datetime

    return session.updated_at or session.created_at or datetime.min
