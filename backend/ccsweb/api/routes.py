"""HTTP routes.

Endpoints:

``GET  /api/sources``                     configured sources and availability
``GET  /api/sessions``                    merged listing, subagents hidden
``GET  /api/sessions/{id}``               transcript with heavy payloads elided
``GET  /api/sessions/{id}/blocks/{ref}``  one block's full payload (accordions)
``GET  /api/sessions/{id}/markdown``      export
``GET  /api/search``                      full-text across transcripts
``GET  /api/stats``                       totals for the dashboard
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ccsweb.archive import Archive, ArchiveResult
from ccsweb.config import get_settings
from ccsweb.export.markdown import session_to_markdown
from ccsweb.lazy import elide_session, locate_block
from ccsweb.models import Block, SessionDetail, SessionSummary, Usage
from ccsweb.pricing.service import CostService
from ccsweb.registry import Registry, SourceStatus
from ccsweb.search import SearchHit, search_sessions

router = APIRouter(prefix="/api")

_registry = Registry.from_settings()
_costs = CostService(_registry)
_archive = Archive(get_settings().archive_root)


class SourceOut(BaseModel):
    id: str
    display_name: str
    available: bool
    root: str
    session_count: int
    error: str | None = None

    @classmethod
    def of(cls, status: SourceStatus) -> SourceOut:
        return cls(**status.__dict__)


class StatsOut(BaseModel):
    """Aggregate counters.

    Tokens are reported as a breakdown rather than one sum on purpose. Agent
    loops resend the whole conversation on every request, so summing per-request
    ``input`` (and cache reads) across a session counts the same context dozens
    of times — a 3-task kilocode dataset totalled 4.5M that way, against 70k
    actually generated. ``output_tokens`` is the only figure that reflects text
    the models really produced, so the UI leads with it.
    """

    session_count: int
    message_count: int
    message_count_is_complete: bool

    input_tokens: int
    output_tokens: int
    cached_tokens: int
    thinking_tokens: int
    #: Sum of every category. Kept for completeness; not a headline figure.
    cumulative_tokens: int

    total_cost_usd: float
    by_source: dict[str, int]
    by_model: dict[str, int]


@router.get("/sources", response_model=list[SourceOut])
def list_sources() -> list[SourceOut]:
    return [SourceOut.of(s) for s in _registry.statuses()]


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(
    source: list[str] | None = Query(default=None),
    include_subagents: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> list[SessionSummary]:
    sessions = _registry.list_sessions(
        sources=source, include_subagents=include_subagents
    )
    return sessions[offset : offset + limit]


@router.get("/sessions/{session_id:path}/blocks/{ref}", response_model=Block)
def get_block(session_id: str, ref: str) -> Block:
    """Full payload for one block — backs the lazy accordions."""
    session = _registry.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    block = locate_block(session, ref)
    if block is None:
        raise HTTPException(status_code=404, detail="block not found")
    return block


@router.get("/sessions/{session_id:path}/markdown", response_class=PlainTextResponse)
def get_markdown(session_id: str) -> str:
    session = _registry.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session_to_markdown(session)


@router.get("/sessions/{session_id:path}", response_model=SessionDetail)
def get_session(session_id: str, full: bool = Query(default=False)) -> SessionDetail:
    session = _registry.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    session.cost_estimate = _costs.session(session)
    if full:
        return session
    return elide_session(session, get_settings().elide_threshold_bytes)


@router.get("/search", response_model=list[SearchHit])
def search(
    q: str = Query(min_length=2),
    source: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SearchHit]:
    return search_sessions(_registry, q, sources=source, limit=limit)


@router.get("/stats", response_model=StatsOut)
def stats() -> StatsOut:
    # Session *count* is of real conversations, so subagents stay excluded.
    sessions = _registry.list_sessions()
    # Usage must include them: a subagent run costs real money, and omitting it
    # understated opencode by 1.36M output tokens and $1.92 on the reference
    # store (3.53M/$79.34 shown against 4.89M/$81.26 actually spent).
    billable = _registry.list_sessions(include_subagents=True)
    by_source: dict[str, int] = {}
    by_model: dict[str, int] = {}
    totals = Usage()
    cost = 0.0
    messages = 0

    for session in sessions:
        by_source[session.source] = by_source.get(session.source, 0) + 1
        for model in session.models:
            by_model[model] = by_model.get(model, 0) + 1
        messages += session.message_count

    for session in billable:
        totals = totals + session.usage
        cost += session.usage.cost_usd or 0.0

    return StatsOut(
        session_count=len(sessions),
        message_count=messages,
        message_count_is_complete=all(s.counts_exact for s in sessions),
        input_tokens=totals.input_tokens,
        output_tokens=totals.output_tokens,
        cached_tokens=totals.cached_tokens,
        thinking_tokens=totals.thinking_tokens,
        cumulative_tokens=totals.total_tokens,
        total_cost_usd=round(cost, 4),
        by_source=by_source,
        by_model=dict(sorted(by_model.items(), key=lambda kv: -kv[1])[:20]),
    )


# --------------------------------------------------------------------------- #
# Archive
# --------------------------------------------------------------------------- #


@router.get("/costs")
def costs() -> dict:
    """Source-recorded amounts and current API estimates, calculated off the hot path."""
    return _costs.snapshot()


@router.post("/costs/refresh")
def refresh_costs() -> dict:
    """Re-read local usage immediately; concurrent refresh requests share one worker."""
    return _costs.snapshot(force=True)


class ArchiveStatsOut(BaseModel):
    session_count: int
    by_source: dict[str, int]
    root: str
    size_bytes: int


class ArchiveResultOut(BaseModel):
    added: int
    updated: int
    unchanged: int
    failed: int
    errors: list[str]


@router.get("/archive", response_model=ArchiveStatsOut)
def archive_stats() -> ArchiveStatsOut:
    return ArchiveStatsOut(**_archive.stats())


@router.get("/archive/sessions", response_model=list[SessionSummary])
def archive_sessions() -> list[SessionSummary]:
    return _archive.list_sessions()


@router.post("/archive/run", response_model=ArchiveResultOut)
def archive_run(source: list[str] | None = Query(default=None)) -> ArchiveResultOut:
    """Snapshot every visible session into the local archive.

    Content-hashed, so re-running is cheap and unchanged sessions are skipped.
    """
    result: ArchiveResult = _archive.archive_all(_registry, sources=source)
    return ArchiveResultOut(
        added=result.added,
        updated=result.updated,
        unchanged=result.unchanged,
        failed=result.failed,
        errors=(result.errors or [])[:20],
    )
