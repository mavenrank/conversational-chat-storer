# Conversational Chat Storer (CCS)

Unified viewer for CLI chat sessions from various AI coding tools.

## Supported Tools

| Tool | Storage Location | Portable? |
|------|-----------------|-----------|
| Claude Code | `~/.claude/` | ✅ Yes |
| Gemini CLI | `~/.gemini/` | ✅ Yes |
| OpenCode | `~/.config/opencode/` | ✅ Yes |
| Kilocode | `~/.local/share/kilo/` | ✅ Yes |

## Installation

```bash
pip install -e .
```

## Usage

### Interactive TUI

```bash
ccs tui
```

Opens an interactive terminal UI where you can:
- Browse sessions from all tools
- Click to view session content
- Scroll through messages with proper markdown rendering
- Press `e` to export current session
- Press `q` to quit

### List all sessions

```bash
ccs list
```

### Show a specific session

```bash
ccs show <session-id>
```

### Export a session

```bash
ccs export <session-id>                 # Export as markdown (default)
ccs export <session-id> -f json         # Export as JSON
ccs export <session-id> -o output.md    # Export to specific file
```

### Backup & Restore (Cross-Device)

```bash
# Create backup of all chat storage
ccs backup                              # Saves to ~/ccs_backups/
ccs backup -o /path/to/external/drive   # Save to external drive

# List available backups
ccs backups

# Restore from backup
ccs restore ~/ccs_backups/ccs_backup_2026-02-25_19-35-45
```

### Show storage paths

```bash
ccs paths
```

## How It Works

CCS reads directly from each tool's native storage format - no wrapper needed. This means:

- No performance impact on your tools
- No risk of breaking tool behavior
- Access to all historical sessions immediately
- Works with tools you've already used

## Features

- **Markdown rendering**: Tables, code blocks, bold/italic render properly in TUI
- **Model tracking**: Shows which model was used for each message (when available)
- **Clean TUI**: Uses alternate screen buffer - exits cleanly without polluting terminal
- **Session metadata**: Shows working directory, timestamps, source path
- **Backup/Restore**: Migrate chats across devices or Linux distros

## Why Gemini Chats "Disappear"

Gemini CLI stores chats in `~/.gemini/tmp/<project-hash>/chats/`. The project hash is based on your working directory - if you change directories, Gemini creates a new "project" folder and your old chats seem to disappear. **They're not deleted, just stored elsewhere!**

CCS finds all these "hidden" sessions across all project folders, so you can see chats that Gemini's UI doesn't show.