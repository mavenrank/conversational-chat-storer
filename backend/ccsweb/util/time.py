"""Timestamp parsing.

Sources disagree on format: Gemini and Claude Code write ISO-8601 strings with a
trailing ``Z``, opencode and kilocode write epoch milliseconds. Everything is
normalised to naive UTC ``datetime`` so sorting and diffing stay consistent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, PlainSerializer


def parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 string, tolerating a trailing ``Z``."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _to_naive_utc(parsed)


def parse_epoch_ms(value: Any) -> datetime | None:
    """Parse epoch milliseconds."""
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return _to_naive_utc(datetime.fromtimestamp(value / 1000, tz=UTC))
    except (OverflowError, OSError, ValueError):
        return None


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _serialize_utc(value: datetime) -> str:
    return _to_naive_utc(value).isoformat() + "Z"


# Keep comparisons internally in UTC, and make that timezone explicit on the
# wire. Browsers otherwise interpret naive ISO dates as the viewer's local time.
UTCDateTime = Annotated[
    datetime,
    AfterValidator(_to_naive_utc),
    PlainSerializer(_serialize_utc, return_type=str, when_used="json"),
]
