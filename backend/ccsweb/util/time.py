"""Timestamp parsing.

Sources disagree on format: Gemini and Claude Code write ISO-8601 strings with a
trailing ``Z``, opencode and kilocode write epoch milliseconds. Everything is
normalised to naive UTC ``datetime`` so sorting and diffing stay consistent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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
        return _to_naive_utc(datetime.fromtimestamp(value / 1000, tz=timezone.utc))
    except (OverflowError, OSError, ValueError):
        return None


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
