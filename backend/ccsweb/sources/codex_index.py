"""Read Codex's local index without scanning every full transcript.

The state database is optional. CLI-only and older installs still work from
rollouts. Read-only SQLite connections include the WAL, which contains changes
from running chats; ``immutable=1`` would silently miss those changes.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ccsweb.util.jsonio import iter_jsonl


def read_state(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    databases = sorted(
        (p for p in root.glob("state_*.sqlite") if re.fullmatch(r"state_\d+", p.stem)),
        key=lambda p: int(p.stem.split("_")[1]),
        reverse=True,
    )
    for path in databases:
        try:
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.2)) as db:
                db.row_factory = sqlite3.Row
                # Select only index metadata, never credentials or full prompts.
                columns = {r[1] for r in db.execute("PRAGMA table_info(threads)")}
                wanted = [
                    c
                    for c in (
                        "id",
                        "rollout_path",
                        "created_at",
                        "updated_at",
                        "created_at_ms",
                        "updated_at_ms",
                        "recency_at",
                        "recency_at_ms",
                        "source",
                        "thread_source",
                        "cwd",
                        "title",
                        "name",
                        "model",
                        "model_provider",
                        "archived",
                        "agent_nickname",
                    )
                    if c in columns
                ]
                if "id" not in wanted:
                    continue
                rows = {
                    r["id"]: dict(r) for r in db.execute(f"SELECT {','.join(wanted)} FROM threads")
                }
                parents: dict[str, str] = {}
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='thread_spawn_edges'"
                ).fetchone():
                    parents = dict(
                        db.execute(
                            "SELECT child_thread_id,parent_thread_id FROM thread_spawn_edges"
                        )
                    )
                return rows, parents
        except (OSError, sqlite3.Error):
            continue
    return {}, {}


def read_names(root: Path) -> dict[str, str]:
    names = {}
    for row in iter_jsonl(root / "session_index.jsonl"):
        if row.get("id") and row.get("thread_name"):
            names[str(row["id"])] = str(row["thread_name"])
    return names


def read_meta(path: Path) -> dict[str, Any]:
    for index, record in enumerate(iter_jsonl(path)):
        if record.get("type") == "session_meta":
            payload = record.get("payload") or {}
            return {
                k: payload[k]
                for k in (
                    "id",
                    "session_id",
                    "timestamp",
                    "cwd",
                    "source",
                    "thread_source",
                    "parent_thread_id",
                    "forked_from_id",
                    "model",
                    "model_provider",
                )
                if k in payload
            }
        if index >= 15:
            break
    return {}


def read_tail(path: Path, size: int = 262_144) -> list[dict[str, Any]]:
    """Bounded read for the latest timestamp, model, and cumulative usage."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            offset = max(0, handle.tell() - size)
            handle.seek(offset)
            if offset:
                handle.readline()  # the first line can be a partial record
            lines = handle.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def subagent_parent(meta: dict[str, Any], row: dict[str, Any]) -> tuple[bool, str | None]:
    source = meta.get("source") or row.get("source") or {}
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except ValueError:
            source = {}
    subagent = source.get("subagent") if isinstance(source, dict) else None
    spawn = subagent.get("thread_spawn", {}) if isinstance(subagent, dict) else {}
    is_child = bool(subagent) or (meta.get("thread_source") or row.get("thread_source")) in {
        "subagent",
        "guardian_review",
    }
    parent = meta.get("parent_thread_id") or spawn.get("parent_thread_id")
    return is_child, str(parent) if parent else None


def is_approval_review(meta: dict[str, Any], row: dict[str, Any]) -> bool:
    if (meta.get("thread_source") or row.get("thread_source")) == "guardian_review":
        return True
    source = meta.get("source") or row.get("source") or {}
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except ValueError:
            return False
    child = source.get("subagent") if isinstance(source, dict) else None
    return isinstance(child, dict) and child.get("other") == "guardian"
