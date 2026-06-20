"""Backup and restore commands for CCS."""

import shutil
import json
from pathlib import Path
from datetime import datetime


from ccs.readers import ClaudeReader, GeminiReader, OpenCodeReader, KilocodeReader


def get_backup_path() -> Path:
    """Get the default backup path."""
    return Path.home() / "ccs_backups"


def get_tool_paths() -> dict:
    """Get all tool storage paths."""
    return {
        "claude": Path.home() / ".claude",
        "gemini": Path.home() / ".gemini",
        "opencode": Path.home() / ".config" / "opencode",
        "kilocode": Path.home() / ".local" / "share" / "kilo",
    }


def cmd_backup(args):
    """Backup all chat storage to a directory."""
    backup_base = Path(args.output) if args.output else get_backup_path()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = backup_base / f"ccs_backup_{timestamp}"

    tool_paths = get_tool_paths()
    backed_up = []

    print(f"Creating backup at: {backup_dir}")
    backup_dir.mkdir(parents=True, exist_ok=True)

    for tool_name, tool_path in tool_paths.items():
        if tool_path.exists():
            dest = backup_dir / tool_name
            try:
                if tool_path.is_dir():
                    shutil.copytree(tool_path, dest)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(tool_path, dest)
                backed_up.append(
                    {
                        "tool": tool_name,
                        "path": str(tool_path),
                        "size": sum(
                            f.stat().st_size for f in dest.rglob("*") if f.is_file()
                        ),
                    }
                )
                print(f"  ✓ {tool_name}: {tool_path}")
            except Exception as e:
                print(f"  ✗ {tool_name}: Error - {e}")
        else:
            print(f"  - {tool_name}: Not found at {tool_path}")

    # Write manifest
    manifest = {
        "created": timestamp,
        "tools": backed_up,
        "total_size": sum(t["size"] for t in backed_up),
    }

    manifest_path = backup_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nBackup complete: {backup_dir}")
    print(f"Total size: {manifest['total_size'] / 1024 / 1024:.2f} MB")
    print(f"Tools backed up: {len(backed_up)}")

    return 0


def cmd_restore(args):
    """Restore chat storage from a backup."""
    backup_dir = Path(args.backup_dir)

    if not backup_dir.exists():
        print(f"Error: Backup directory not found: {backup_dir}")
        return 1

    manifest_path = backup_dir / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        print(f"Restoring backup from: {manifest['created']}")
        print(f"Tools to restore: {[t['tool'] for t in manifest['tools']]}")
    else:
        print(f"Warning: No manifest found, restoring all found tool directories")

    tool_paths = get_tool_paths()
    restored = []

    for tool_name in ["claude", "gemini", "opencode", "kilocode"]:
        backup_tool_dir = backup_dir / tool_name
        if not backup_tool_dir.exists():
            continue

        dest_path = tool_paths[tool_name]

        # Backup existing if it exists
        if dest_path.exists():
            old_backup = dest_path.with_suffix(
                f".old_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            print(f"  Backing up existing {tool_name} to {old_backup}")
            shutil.move(str(dest_path), str(old_backup))

        try:
            if backup_tool_dir.is_dir():
                shutil.copytree(backup_tool_dir, dest_path)
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_tool_dir, dest_path)
            restored.append(tool_name)
            print(f"  ✓ {tool_name}: Restored to {dest_path}")
        except Exception as e:
            print(f"  ✗ {tool_name}: Error - {e}")

    print(f"\nRestore complete. Tools restored: {len(restored)}")
    return 0


def cmd_list_backups(args):
    """List available backups."""
    backup_base = Path(args.path) if args.path else get_backup_path()

    if not backup_base.exists():
        print(f"No backups found at {backup_base}")
        return 0

    backups = sorted(backup_base.glob("ccs_backup_*"), reverse=True)

    if not backups:
        print(f"No backups found at {backup_base}")
        return 0

    print(f"Backups in {backup_base}:")
    print("-" * 60)

    for backup in backups:
        manifest_path = backup / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            print(f"  {backup.name}")
            print(f"    Created: {manifest['created']}")
            print(f"    Tools: {[t['tool'] for t in manifest['tools']]}")
            print(f"    Size: {manifest['total_size'] / 1024 / 1024:.2f} MB")
        else:
            print(f"  {backup.name} (no manifest)")

    return 0


def cmd_export_session(args):
    """Export a session to a portable format."""
    from ccs.cli import find_reader

    reader = find_reader(args.session_id)
    if not reader:
        print(f"Unknown session format: {args.session_id}")
        return 1

    session = reader.get_session(args.session_id)
    if not session:
        print(f"Session not found: {args.session_id}")
        return 1

    output_dir = Path(args.output) if args.output else Path(".")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save as markdown
    md_path = output_dir / f"{args.session_id}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(session.to_markdown())

    # Save as JSON
    json_path = output_dir / f"{args.session_id}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)

    print(f"Exported session to:")
    print(f"  {md_path}")
    print(f"  {json_path}")

    return 0
