"""CLI entry point for CCS - Unified chat viewer."""

import argparse
import sys
from pathlib import Path


from datetime import datetime

from ccs import __version__
from ccs.models import format_timestamp
from ccs.readers import ClaudeReader, GeminiReader, OpenCodeReader, KilocodeReader


def get_all_readers():
    """Get all available readers."""
    return [
        ClaudeReader(),
        GeminiReader(),
        OpenCodeReader(),
        KilocodeReader(),
    ]


def list_all_sessions() -> list[dict]:
    """List sessions from all available tools."""
    all_sessions = []
    for reader in get_all_readers():
        if reader.is_available():
            try:
                sessions = reader.list_sessions()
                all_sessions.extend(sessions)
            except Exception as e:
                print(
                    f"Warning: Error reading {reader.tool_name}: {e}", file=sys.stderr
                )

    def get_sort_key(x):
        ts = x.get("start_time")
        if ts is None:
            return datetime.min
        if ts.tzinfo is not None:
            return ts.replace(tzinfo=None)
        return ts

    return sorted(all_sessions, key=get_sort_key, reverse=True)


def find_reader(session_id: str):
    """Find the appropriate reader for a session ID."""
    for reader in get_all_readers():
        if session_id.startswith(f"{reader.tool_name}_"):
            return reader
    return None


def resolve_session(query: str):
    """Resolve a session ID or title to a (reader, session) pair."""
    reader = find_reader(query)
    if reader:
        session = reader.get_session(query)
        if session:
            return reader, session

    sessions = list_all_sessions()
    query_lower = query.lower()
    matches = [s for s in sessions if query_lower in s.get("title", "").lower()]

    if not matches:
        return None, None

    if len(matches) == 1:
        sid = matches[0]["session_id"]
        reader = find_reader(sid)
        if reader:
            return reader, reader.get_session(sid)
        return None, None

    print(f"Multiple sessions match '{query}':", file=sys.stderr)
    for s in matches:
        start = s.get("start_time")
        start_str = start.strftime("%Y-%m-%d %H:%M") if start else "unknown"
        print(
            f"  {s['session_id']:<40} {s.get('title', ''):<35} {start_str}",
            file=sys.stderr,
        )
    return None, None


def cmd_list(args):
    """List all sessions from all tools."""
    sessions = list_all_sessions()

    if not sessions:
        print("No sessions found.")
        print("\nChecked locations:")
        for reader in get_all_readers():
            status = "available" if reader.is_available() else "not found"
            print(f"  {reader.tool_name}: {reader.get_storage_path()} ({status})")
        return 0

    print(f"{'Title':<55} {'Tool':<10} {'Started'}")
    print("-" * 80)

    for s in sessions:
        title = s.get("title") or s["session_id"]
        start = s.get("start_time")
        start_str = format_timestamp(start) if start else "unknown"
        print(f"{title:<55} {s['tool_name']:<10} {start_str}")

    return 0


def cmd_show(args):
    """Show a specific session."""
    reader, session = resolve_session(args.session_id)
    if not session:
        print(f"Session not found: {args.session_id}", file=sys.stderr)
        return 1

    title = session.title or session.session_id
    print(f"Title: {title}")
    print(f"Session: {session.session_id}")
    print(f"Tool: {session.tool_name}")
    if session.start_time:
        print(f"Started: {session.start_time}")
    if session.working_directory:
        print(f"Working Directory: {session.working_directory}")
    print(f"Messages: {len(session.messages)}")
    if session.source_path:
        print(f"Source: {session.source_path}")
    print()
    print("=" * 80)
    print()

    last_ts = None
    for msg in session.messages:
        ts_str = format_timestamp(msg.timestamp, last_ts)
        last_ts = msg.timestamp
        role = msg.role.upper()
        model = msg.model
        model_str = f" (model: {model})" if model else ""
        print(f"[{ts_str}] {role}{model_str}:")
        print(msg.content)
        print()
        print("-" * 40)
        print()

    return 0


def cmd_export(args):
    """Export a session to file."""
    reader, session = resolve_session(args.session_id)
    if not session:
        print(f"Session not found: {args.session_id}", file=sys.stderr)
        return 1

    if args.format == "json":
        import json

        content = json.dumps(session.to_dict(), indent=2, ensure_ascii=False)
        ext = "json"
    else:
        content = session.to_markdown()
        ext = "md"

    if args.output:
        output_path = Path(args.output)
    else:
        name = session.title.replace("/", "_") if session.title else session.session_id
        name = name.removesuffix(f".{ext}")
        output_path = Path(f"{name}.{ext}")

    output_path.write_text(content, encoding="utf-8")
    print(f"Exported to: {output_path}")

    return 0


def cmd_paths(args):
    """Show storage paths for all tools."""
    print("Storage paths:")
    for reader in get_all_readers():
        path = reader.get_storage_path()
        status = "exists" if reader.is_available() else "not found"
        print(f"  {reader.tool_name}: {path} ({status})")
    return 0


def cmd_tui(args):
    """Launch the TUI."""
    from ccs.tui import run_tui

    run_tui()
    return 0


def cmd_backup(args):
    """Backup all chat storage."""
    from ccs.backup import cmd_backup as _cmd_backup

    return _cmd_backup(args)


def cmd_restore(args):
    """Restore chat storage from backup."""
    from ccs.backup import cmd_restore as _cmd_restore

    return _cmd_restore(args)


def cmd_backups(args):
    """List available backups."""
    from ccs.backup import cmd_list_backups as _cmd_list_backups

    return _cmd_list_backups(args)


def main():
    parser = argparse.ArgumentParser(
        prog="ccs",
        description="Conversational Chat Storer - Unified viewer for CLI chat sessions",
    )
    parser.add_argument("--version", action="version", version=f"ccs {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    list_parser = subparsers.add_parser(
        "list", aliases=["ls"], help="List all sessions from all tools"
    )
    list_parser.set_defaults(func=cmd_list)

    show_parser = subparsers.add_parser("show", help="Show a session")
    show_parser.add_argument("session_id", help="Session ID or title (partial match)")
    show_parser.set_defaults(func=cmd_show)

    export_parser = subparsers.add_parser("export", help="Export a session")
    export_parser.add_argument("session_id", help="Session ID or title (partial match)")
    export_parser.add_argument(
        "--format",
        "-f",
        choices=["json", "md"],
        default="md",
        help="Export format (default: md)",
    )
    export_parser.add_argument("--output", "-o", help="Output file path")
    export_parser.set_defaults(func=cmd_export)

    paths_parser = subparsers.add_parser("paths", help="Show storage paths")
    paths_parser.set_defaults(func=cmd_paths)

    tui_parser = subparsers.add_parser("tui", help="Launch interactive TUI")
    tui_parser.set_defaults(func=cmd_tui)

    # Backup commands
    backup_parser = subparsers.add_parser("backup", help="Backup all chat storage")
    backup_parser.add_argument(
        "--output", "-o", help="Output directory (default: ~/ccs_backups)"
    )
    backup_parser.set_defaults(func=cmd_backup)

    restore_parser = subparsers.add_parser(
        "restore", help="Restore chat storage from backup"
    )
    restore_parser.add_argument("backup_dir", help="Backup directory to restore from")
    restore_parser.set_defaults(func=cmd_restore)

    backups_parser = subparsers.add_parser("backups", help="List available backups")
    backups_parser.add_argument(
        "--path", "-p", help="Backups directory (default: ~/ccs_backups)"
    )
    backups_parser.set_defaults(func=cmd_backups)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if hasattr(args, "func"):
        return args.func(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
