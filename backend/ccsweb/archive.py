"""Local archive of normalised sessions.

Chat stores are volatile in ways that are easy to miss: opencode has an open
issue about unbounded session growth and prunes, Codex rollouts can be cleaned
up, Gemini's `tmp/` directory is by definition temporary, and reinstalling a
tool or moving machines loses everything. This module snapshots sessions into a
directory we own, in *our* normalised schema, so history survives the source.

Layout::

    <archive_root>/
        index.json                     manifest: id -> {hash, archived_at, ...}
        sessions/<source>/<id>.json    one normalised SessionDetail per file

Design points:

* Snapshots are stored post-normalisation, so restoring does not depend on the
  original tool's format still being parseable.
* Content-hashed. Re-archiving an unchanged session is a no-op, which makes the
  operation cheap to run on a schedule.
* Never deletes from a source. This is strictly additive.
* The full payload is written, not the elided form the API returns, otherwise
  the archive would lose exactly the file contents worth keeping.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ccsweb.models import SessionDetail, SessionSummary

INDEX_NAME = "index.json"
SESSIONS_DIR = "sessions"


@dataclass
class ArchiveEntry:
    """One row of the manifest."""

    id: str
    source: str
    title: str
    #: Hash of the serialised session, used to skip unchanged re-archives.
    content_hash: str
    archived_at: str
    message_count: int
    path: str


@dataclass
class ArchiveResult:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


class Archive:
    """Read/write access to the local session archive."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.index_path = root / INDEX_NAME

    # ------------------------------------------------------------------ #
    # Manifest
    # ------------------------------------------------------------------ #

    def load_index(self) -> dict[str, ArchiveEntry]:
        if not self.index_path.exists():
            return {}
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A corrupt manifest must not block archiving; it gets rebuilt.
            return {}
        entries: dict[str, ArchiveEntry] = {}
        for key, value in (raw.get("entries") or {}).items():
            try:
                entries[key] = ArchiveEntry(**value)
            except TypeError:
                continue
        return entries

    def save_index(self, entries: dict[str, ArchiveEntry]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": _now(),
            "entries": {k: asdict(v) for k, v in entries.items()},
        }
        # Write via a temp file so an interrupted run cannot truncate the index.
        temp = self.index_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(self.index_path)

    # ------------------------------------------------------------------ #
    # Writing
    # ------------------------------------------------------------------ #

    def store(self, session: SessionDetail) -> str:
        """Write one session and return its status: added/updated/unchanged."""
        body = session.model_dump_json(indent=2)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()

        entries = self.load_index()
        existing = entries.get(session.id)
        if existing and existing.content_hash == digest:
            return "unchanged"

        relative = Path(SESSIONS_DIR) / session.source / f"{_safe(session.id)}.json"
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

        entries[session.id] = ArchiveEntry(
            id=session.id,
            source=session.source,
            title=session.title,
            content_hash=digest,
            archived_at=_now(),
            message_count=len(session.messages),
            path=str(relative).replace("\\", "/"),
        )
        self.save_index(entries)
        return "updated" if existing else "added"

    def archive_all(self, registry, sources: list[str] | None = None) -> ArchiveResult:
        """Snapshot every session the registry can see, subagents included."""
        result = ArchiveResult()
        summaries = registry.list_sessions(
            sources=sources, include_subagents=True, include_approval_reviews=True
        )

        for summary in summaries:
            try:
                detail = registry.get_session(summary.id)
                if detail is None:
                    result.failed += 1
                    result.errors.append(f"{summary.id}: could not be loaded")
                    continue
                status = self.store(detail)
                setattr(result, status, getattr(result, status) + 1)
            except Exception as exc:  # noqa: BLE001 - one bad session must not stop the run
                result.failed += 1
                result.errors.append(f"{summary.id}: {exc}")

        return result

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #

    def list_sessions(self) -> list[SessionSummary]:
        """Summaries of everything archived, newest first."""
        summaries: list[SessionSummary] = []
        for entry in self.load_index().values():
            detail = self.load(entry.id)
            if detail is not None:
                summaries.append(
                    SessionSummary(**detail.model_dump(exclude={"messages", "subagents"}))
                )
        summaries.sort(key=lambda s: s.updated_at or s.created_at or datetime.min, reverse=True)
        return summaries

    def load(self, session_id: str) -> SessionDetail | None:
        entry = self.load_index().get(session_id)
        if entry is None:
            return None
        path = self.root / entry.path
        try:
            return SessionDetail.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def stats(self) -> dict:
        entries = self.load_index()
        by_source: dict[str, int] = {}
        for entry in entries.values():
            by_source[entry.source] = by_source.get(entry.source, 0) + 1
        return {
            "session_count": len(entries),
            "by_source": by_source,
            "root": str(self.root),
            "size_bytes": _dir_size(self.root),
        }


def _safe(value: str) -> str:
    """Make a global id safe as a filename (ids contain ':' and may contain '/')."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in value)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
