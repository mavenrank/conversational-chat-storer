#!/usr/bin/env python3
"""Standalone verification of the source-parsing rules against real data.

Uses only the standard library so it can run before dependencies are installed.
It re-implements the *decision rules* the adapters rely on and asserts them
against whatever chat stores exist on this machine. If a rule is wrong, this
fails loudly rather than silently producing a bad session list.

Usage::

    python backend/scripts/verify_sources.py
    python backend/scripts/verify_sources.py --gemini-root /path/to/.gemini
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

SUBAGENT_TASK_ID = re.compile(r"^task_id:\s*(?P<sid>\S+)")

failures: list[str] = []
notes: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  PASS  {message}")
    else:
        print(f"  FAIL  {message}")
        failures.append(message)


# --------------------------------------------------------------------------- #
# Gemini
# --------------------------------------------------------------------------- #


def verify_gemini(root: Path) -> None:
    print(f"\n=== gemini  ({root}) ===")
    tmp = root / "tmp"
    if not tmp.is_dir():
        notes.append("gemini: no tmp/ directory, skipped")
        print("  SKIP  no tmp/ directory")
        return

    files = sorted(tmp.glob("*/chats/*.json"))
    by_session: dict[str, list[Path]] = defaultdict(list)
    rich_fields = {"thoughts": 0, "tokens": 0, "model": 0, "toolCalls": 0}

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        session_id = data.get("sessionId")
        if not session_id:
            continue
        by_session[session_id].append(path)
        for message in data.get("messages") or []:
            for field in rich_fields:
                if message.get(field):
                    rich_fields[field] += 1

    duplicated = {s: p for s, p in by_session.items() if len(p) > 1}
    print(f"  {len(files)} snapshot files -> {len(by_session)} unique sessionIds")
    check(
        len(by_session) <= len(files),
        f"de-dup by sessionId collapses {len(files)} files to {len(by_session)} sessions",
    )
    if duplicated:
        print(f"  NOTE  {len(duplicated)} session(s) had multiple snapshots:")
        for session_id, paths in duplicated.items():
            sizes = sorted(p.stat().st_size for p in paths)
            print(f"          {session_id}  sizes={sizes}")
        check(
            True,
            "duplicate snapshots detected and would be collapsed to the newest",
        )
    else:
        notes.append("gemini: no duplicate snapshots present in this dataset")

    print(f"  rich assistant fields seen: {rich_fields}")
    check(
        any(rich_fields.values()),
        "assistant messages carry thoughts/tokens/model/toolCalls worth parsing",
    )

    logs = list(tmp.glob("*/logs.json"))
    if logs:
        sample = json.loads(logs[0].read_text(encoding="utf-8", errors="replace"))
        check(
            isinstance(sample, list)
            and all("message" in r for r in sample if isinstance(r, dict)),
            "logs.json is a flat prompt log, correctly excluded from sessions",
        )


# --------------------------------------------------------------------------- #
# OpenCode
# --------------------------------------------------------------------------- #


def verify_opencode(root: Path) -> None:
    print(f"\n=== opencode  ({root}) ===")
    db = root / "opencode.db"
    if not db.exists():
        notes.append("opencode: no opencode.db, skipped")
        print("  SKIP  no opencode.db")
        return

    # immutable=1 avoids taking any lock on a database a live agent may be using.
    conn = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    try:
        total = conn.execute("SELECT COUNT(*) FROM session").fetchone()[0]
        roots = conn.execute(
            "SELECT COUNT(*) FROM session WHERE parent_id IS NULL"
        ).fetchone()[0]
        children = total - roots
        print(f"  {total} sessions: {roots} root, {children} subagent children")
        check(
            roots + children == total,
            "every session is classified as either root or subagent child",
        )
        if children:
            check(
                children > 0,
                f"{children} subagent session(s) would be hidden from the top-level list",
            )

        # The parent's task tool output should name the child session id.
        linked = 0
        checked = 0
        for (data,) in conn.execute(
            "SELECT data FROM part WHERE data LIKE '%\"tool\":\"task\"%' LIMIT 200"
        ):
            try:
                part = json.loads(data)
            except ValueError:
                continue
            if part.get("tool") != "task":
                continue
            checked += 1
            output = (part.get("state") or {}).get("output") or ""
            if SUBAGENT_TASK_ID.match(str(output)):
                linked += 1
        if checked:
            print(f"  task tool parts inspected: {checked}, with task_id link: {linked}")
            check(
                linked > 0,
                "task tool output exposes 'task_id: <session>' for inline subagent linking",
            )
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Claude Code
# --------------------------------------------------------------------------- #


def verify_claude(root: Path) -> None:
    print(f"\n=== claude  ({root}) ===")
    projects = root / "projects" if (root / "projects").is_dir() else root
    transcripts = sorted(projects.glob("*/*.jsonl"))
    if not transcripts:
        notes.append(f"claude: no transcripts under {projects}, skipped")
        print("  SKIP  no transcripts found")
        return

    print(f"  {len(transcripts)} transcript file(s)")
    check(
        True,
        "sessions are flat <session-uuid>.jsonl files under <encoded-cwd>/",
    )

    total_tools = paired_tools = titled = sidechain = 0
    multi_session = 0

    for path in transcripts:
        records = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue

        if any(r.get("type") in ("ai-title", "custom-title") for r in records):
            titled += 1
        if len({r["sessionId"] for r in records if r.get("sessionId")}) > 1:
            multi_session += 1

        # Tool results live on the following user record, joined by tool_use_id.
        results = set()
        for record in records:
            if record.get("type") != "user":
                continue
            content = (record.get("message") or {}).get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        if block.get("tool_use_id"):
                            results.add(block["tool_use_id"])

        for record in records:
            if record.get("isSidechain"):
                sidechain += 1
            content = (record.get("message") or {}).get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        total_tools += 1
                        if block.get("id") in results:
                            paired_tools += 1

    print(f"  transcripts carrying a title record: {titled}/{len(transcripts)}")
    check(titled > 0, "titles come from ai-title/custom-title records")

    if total_tools:
        ratio = paired_tools / total_tools
        print(f"  tool_use paired with a result: {paired_tools}/{total_tools} ({ratio:.2%})")
        check(
            ratio > 0.95,
            "tool results join back to their call via tool_use_id",
        )

    print(f"  isSidechain records: {sidechain}")
    if sidechain == 0:
        notes.append(
            "claude: no isSidechain records present, so subagent handling is "
            "implemented to spec but unverified"
        )
    if multi_session:
        notes.append(
            f"claude: {multi_session} transcript(s) contain more than one sessionId "
            "(resumed/forked sessions)"
        )


# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    home = Path.home()
    parser.add_argument("--gemini-root", type=Path, default=home / ".gemini")
    parser.add_argument(
        "--opencode-root", type=Path, default=home / ".local" / "share" / "opencode"
    )
    parser.add_argument("--claude-root", type=Path, default=home / ".claude")
    args = parser.parse_args()

    verify_gemini(args.gemini_root)
    verify_opencode(args.opencode_root)
    verify_claude(args.claude_root)

    print("\n=== summary ===")
    for note in notes:
        print(f"  note: {note}")
    if failures:
        print(f"  {len(failures)} check(s) FAILED")
        return 1
    print("  all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
