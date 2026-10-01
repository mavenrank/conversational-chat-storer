"""Fault-tolerant JSON and JSONL reading.

Chat stores are written by live processes, so a transcript can be mid-write,
truncated or contain a corrupt line. A single bad record must never take down a
listing, so every helper here degrades instead of raising.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


def read_json(path: Path) -> Any:
    """Parse a JSON file, returning ``None`` on any read or parse failure."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield each well-formed JSON object from a JSONL file.

    Malformed lines are skipped rather than raising, which matters for the last
    line of a transcript that is still being appended to.
    """
    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return

    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                yield record
