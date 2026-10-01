"""OpenCode adapter.

Storage is a single SQLite database at ``~/.local/share/opencode/opencode.db``
with tables ``project``, ``session``, ``message`` and ``part``.

The database belongs to a live agent, so it is opened with ``immutable=1``. That
takes no locks and ignores the WAL, guaranteeing we can never block or corrupt a
running opencode process. The tradeoff is that writes still sitting in the WAL
are invisible until opencode checkpoints; for a history browser that is the
right trade.

**Subagents.** ``session.parent_id`` marks a session as a delegated run. On the
reference store 161 of 251 sessions were children. Listing them as ordinary
chats is what made subagents "show up as normal chats". They are returned here
flagged, and the registry hides them from the default list while attaching them
to the ``task`` call that spawned them.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from ccsweb.models import (
    Message,
    ProjectRef,
    SessionDetail,
    SessionSummary,
    Usage,
)
from ccsweb.sources.base import AdapterError, SourceAdapter
from ccsweb.sources.opencode_parts import parse_part, parse_step_finish
from ccsweb.util.time import parse_epoch_ms


class OpenCodeAdapter(SourceAdapter):
    source_id = "opencode"
    display_name = "OpenCode"

    def __init__(self, root: Path | None = None) -> None:
        super().__init__(root)
        #: (db mtime_ns, per-session usage) — see ``_usage_index``.
        self._usage_cache: tuple[int, dict[str, Usage]] | None = None

    @staticmethod
    def default_root() -> Path:
        return Path.home() / ".local" / "share" / "opencode"

    @property
    def _db_path(self) -> Path:
        return self.root / "opencode.db"

    def is_available(self) -> bool:
        return self._db_path.exists()

    def _connect(self) -> sqlite3.Connection:
        try:
            return sqlite3.connect(f"file:{self._db_path}?immutable=1", uri=True)
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            raise AdapterError(self.source_id, f"cannot open database: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Listing
    # ------------------------------------------------------------------ #

    def list_sessions(self) -> list[SessionSummary]:
        conn = self._connect()
        try:
            columns = _columns(conn, "session")
            projects = _load_projects(conn)
            child_counts = _child_counts(conn)
            usage_by_session = self._usage_index(conn)
            user_counts = _user_message_counts(conn)
            models_by_session, providers_by_session = _model_index(conn)

            select = ["id", "parent_id", "project_id", "directory", "title", "time_created"]
            optional = [c for c in ("time_updated", "time_archived") if c in columns]
            select += optional

            rows = conn.execute(
                f"SELECT {', '.join(select)} FROM session ORDER BY time_created DESC"
            ).fetchall()

            sessions: list[SessionSummary] = []
            for row in rows:
                record = dict(zip(select, row))
                if record.get("time_archived"):
                    continue
                session_id = record["id"]
                parent_id = record.get("parent_id")
                sessions.append(
                    SessionSummary(
                        id=session_id,
                        source=self.source_id,
                        title=record.get("title") or "Untitled session",
                        project=projects.get(record.get("project_id") or ""),
                        cwd=record.get("directory") or "",
                        created_at=parse_epoch_ms(record.get("time_created")),
                        updated_at=parse_epoch_ms(record.get("time_updated"))
                        or parse_epoch_ms(record.get("time_created")),
                        user_message_count=user_counts.get(session_id, 0),
                        usage=usage_by_session.get(session_id, Usage()),
                        models=sorted(models_by_session.get(session_id, set())),
                        providers=sorted(providers_by_session.get(session_id, set())),
                        is_subagent=parent_id is not None,
                        parent_session_id=parent_id,
                        subagent_count=child_counts.get(session_id, 0),
                        source_path=str(self._db_path),
                    )
                )
            return sessions
        finally:
            conn.close()

    def _usage_index(self, conn: sqlite3.Connection) -> dict[str, Usage]:
        """Token totals per session, aggregated from ``step-finish`` parts.

        Usage lives only on those parts, so a per-session figure needs a scan of
        them. On a 457 MB store that is ~8.4k rows and about 2.5s, so the result
        is cached against the database's mtime — sessions are immutable once
        written, and a new write bumps the file.
        """
        try:
            stamp = self._db_path.stat().st_mtime_ns
        except OSError:
            stamp = 0
        if self._usage_cache is not None and self._usage_cache[0] == stamp:
            return self._usage_cache[1]

        totals: dict[str, Usage] = {}
        try:
            rows = conn.execute(
                "SELECT session_id, data FROM part WHERE data LIKE '%step-finish%'"
            )
        except sqlite3.Error:
            return {}

        for session_id, raw in rows:
            part = _loads(raw)
            if part.get("type") != "step-finish":
                continue
            usage, _ = parse_step_finish(part)
            if usage is None:
                continue
            totals[session_id] = totals.get(session_id, Usage()) + usage

        self._usage_cache = (stamp, totals)
        return totals

    # ------------------------------------------------------------------ #
    # Detail
    # ------------------------------------------------------------------ #

    def get_session(self, session_id: str) -> SessionDetail | None:
        conn = self._connect()
        try:
            columns = _columns(conn, "session")
            select = ["id", "parent_id", "project_id", "directory", "title", "time_created"]
            select += [c for c in ("time_updated",) if c in columns]

            row = conn.execute(
                f"SELECT {', '.join(select)} FROM session WHERE id = ?", (session_id,)
            ).fetchone()
            if row is None:
                return None
            record = dict(zip(select, row))

            messages = list(self._iter_messages(conn, session_id))
            total_usage = Usage()
            for message in messages:
                if message.usage is not None:
                    total_usage = total_usage + message.usage

            projects = _load_projects(conn)
            subagents = self._child_summaries(conn, session_id, projects)

            return SessionDetail(
                id=session_id,
                source=self.source_id,
                title=record.get("title") or "Untitled session",
                project=projects.get(record.get("project_id") or ""),
                cwd=record.get("directory") or "",
                created_at=parse_epoch_ms(record.get("time_created")),
                updated_at=parse_epoch_ms(record.get("time_updated"))
                or parse_epoch_ms(record.get("time_created")),
                message_count=len(messages),
                user_message_count=sum(1 for m in messages if m.role == "user"),
                models=sorted({m.model for m in messages if m.model}),
                providers=sorted({m.provider for m in messages if m.provider}),
                usage=total_usage,
                is_subagent=record.get("parent_id") is not None,
                parent_session_id=record.get("parent_id"),
                subagent_count=len(subagents),
                source_path=str(self._db_path),
                messages=messages,
                subagents=subagents,
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------ #

    def _iter_messages(
        self, conn: sqlite3.Connection, session_id: str
    ) -> Iterator[Message]:
        rows = conn.execute(
            "SELECT id, time_created, time_updated, data FROM message "
            "WHERE session_id = ? ORDER BY time_created ASC",
            (session_id,),
        ).fetchall()

        for message_id, created, updated, raw in rows:
            data = _loads(raw)
            role = data.get("role") or "assistant"
            if role not in {"user", "assistant", "system"}:
                role = "assistant"

            blocks = []
            usage: Usage | None = None
            for (part_raw,) in conn.execute(
                "SELECT data FROM part WHERE message_id = ? ORDER BY time_created ASC",
                (message_id,),
            ):
                part = _loads(part_raw)
                if part.get("type") == "step-finish":
                    step_usage, _ = parse_step_finish(part)
                    if step_usage is not None:
                        usage = step_usage if usage is None else usage + step_usage
                    continue
                block = parse_part(part)
                if block is not None:
                    blocks.append(block)

            if not blocks:
                # Pure orchestration turn with nothing to render.
                continue

            yield Message(
                id=message_id,
                role=role,  # type: ignore[arg-type]
                blocks=blocks,
                started_at=parse_epoch_ms(created),
                completed_at=parse_epoch_ms(updated),
                model=_model_of(data),
                provider=data.get("providerID"),
                usage=usage,
            )

    def _child_summaries(
        self,
        conn: sqlite3.Connection,
        parent_id: str,
        projects: dict[str, ProjectRef],
    ) -> list[SessionSummary]:
        rows = conn.execute(
            "SELECT id, project_id, directory, title, time_created "
            "FROM session WHERE parent_id = ? ORDER BY time_created ASC",
            (parent_id,),
        ).fetchall()
        return [
            SessionSummary(
                id=row[0],
                source=self.source_id,
                title=row[3] or "Subagent run",
                project=projects.get(row[1] or ""),
                cwd=row[2] or "",
                created_at=parse_epoch_ms(row[4]),
                is_subagent=True,
                parent_session_id=parent_id,
                source_path=str(self._db_path),
            )
            for row in rows
        ]


# ---------------------------------------------------------------------- #
# SQLite helpers
# ---------------------------------------------------------------------- #


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Introspect columns so schema drift degrades instead of raising."""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _load_projects(conn: sqlite3.Connection) -> dict[str, ProjectRef]:
    projects: dict[str, ProjectRef] = {}
    try:
        rows = conn.execute("SELECT id, worktree, name FROM project").fetchall()
    except sqlite3.Error:
        return projects
    for project_id, worktree, name in rows:
        path = worktree or ""
        projects[project_id] = ProjectRef(
            id=project_id,
            name=name or (Path(path).name if path else project_id),
            path=path,
        )
    return projects


def _child_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT parent_id, COUNT(*) FROM session "
            "WHERE parent_id IS NOT NULL GROUP BY parent_id"
        )
    }


def _loads(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _model_of(data: dict[str, Any]) -> str | None:
    model = data.get("modelID")
    if isinstance(model, str) and model:
        return model
    nested = data.get("model")
    if isinstance(nested, dict):
        inner = nested.get("modelID")
        if isinstance(inner, str) and inner:
            return inner
    return None


def _user_message_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """How many turns the human actually typed, per session."""
    counts: dict[str, int] = {}
    try:
        rows = conn.execute(
            "SELECT session_id, COUNT(*) FROM message "
            "WHERE data LIKE '%\"role\":\"user\"%' GROUP BY session_id"
        )
    except sqlite3.Error:
        return counts
    for session_id, count in rows:
        counts[session_id] = count
    return counts


def _model_index(
    conn: sqlite3.Connection,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Distinct models and providers per session.

    The list view previously reported no models at all, which meant the pricing
    sync saw none of opencode's 22 models — roughly 90% of real usage. Both are
    needed: the model says what to price, and the provider says *which seller's*
    price applies. OpenCode Go and Zen charge differently for identical model
    ids, so the provider is not optional detail.
    """
    models: dict[str, set[str]] = {}
    providers: dict[str, set[str]] = {}
    try:
        rows = conn.execute("SELECT session_id, data FROM message")
    except sqlite3.Error:
        return models, providers

    for session_id, raw in rows:
        data = _loads(raw)
        model = _model_of(data)
        if model:
            models.setdefault(session_id, set()).add(model)
        provider = data.get("providerID")
        if isinstance(provider, str) and provider:
            providers.setdefault(session_id, set()).add(provider)
    return models, providers
