"""Full-text search across transcripts.

Deliberately simple: a case-insensitive substring scan over session titles first,
then message text for the sources that can supply it cheaply.

The opencode store in the reference dataset is 457 MB, so scanning every
transcript on each keystroke is not viable. Search is therefore capped and
title-first; a persistent inverted index is the follow-up if this proves too
slow in practice.
"""

from __future__ import annotations

from pydantic import BaseModel

from ccsweb.models import SessionSummary


class SearchHit(BaseModel):
    session: SessionSummary
    #: Where the match came from: ``title`` or ``message``.
    field: str
    #: Surrounding text with the match in the middle.
    excerpt: str


def search_sessions(
    registry,
    query: str,
    sources: list[str] | None = None,
    limit: int = 50,
    scan_transcripts: int = 40,
) -> list[SearchHit]:
    needle = query.strip().lower()
    if len(needle) < 2:
        return []

    sessions = registry.list_sessions(
        sources=sources, include_subagents=True, include_approval_reviews=True
    )
    hits: list[SearchHit] = []
    unmatched: list[SessionSummary] = []

    for session in sessions:
        if needle in (session.title or "").lower():
            hits.append(
                SearchHit(
                    session=session,
                    field="title",
                    excerpt=_excerpt(session.title, needle),
                )
            )
        else:
            unmatched.append(session)
        if len(hits) >= limit:
            return hits

    # Only then pay for transcript reads, and only for a bounded number.
    for session in unmatched[:scan_transcripts]:
        if len(hits) >= limit:
            break
        detail = registry.get_session(session.id)
        if detail is None:
            continue
        for message in detail.messages:
            text = message.text
            if needle in text.lower():
                hits.append(
                    SearchHit(
                        session=session,
                        field="message",
                        excerpt=_excerpt(text, needle),
                    )
                )
                break

    return hits


def _excerpt(text: str, needle: str, window: int = 90) -> str:
    lowered = text.lower()
    index = lowered.find(needle)
    if index == -1:
        return text[: window * 2].strip()
    start = max(0, index - window)
    end = min(len(text), index + len(needle) + window)
    excerpt = text[start:end].replace("\n", " ").strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{excerpt}{suffix}"
