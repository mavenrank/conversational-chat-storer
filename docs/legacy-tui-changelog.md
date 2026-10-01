# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-06-21

### Second development session — Performance, stability, edit diff, timestamps

### Added

- **Lazy loading for large sessions** — first 30 messages mounted immediately,
  then 10 more loaded automatically when the user scrolls within 5px of the
  bottom. Uses `set_interval(0.3)` polling to avoid reactive-watcher cascade
  when `max_scroll_y` changes mid-mount.
- **One-message-per-iteration mounting** — messages are mounted one at a time
  via `call_later()` instead of batch-mounting in a synchronous loop. Keeps
  the TUI responsive on 200+ message sessions.
- **Edit tool side-by-side diff** — `tool: "edit"` content rendered as a Rich
  `Table` with "Removed" (red) and "Added" (green) columns in the TUI.
  In markdown export, rendered as a ````diff` code block.
- **Edit content markers** — `EDIT_MARKER`, `EDIT_OLD_START`, `EDIT_OLD_END`,
  `EDIT_NEW_START`, `EDIT_NEW_END`, `EDIT_END_MARKER` constants wrapping edit
  tool old/new strings. Prevents diff text from leaking into surrounding
  markdown rendering.
- **`format_timestamp()` helper** — renders `YYYY-MM-DD HH:MM:SS` for the
  first message of a day, `HH:MM:SS` only for subsequent messages on the
  same day. Applied to TUI, markdown export, and CLI `show` output.
- **`code_fence()` helper** — generates a variable-length `~` fence that is
  guaranteed not to appear in the content being quoted. Prevents premature
  code-block closure when file content contains `~~~`.
- **`close_fences()` helper** — ensures all backtick code fences (`` ``` ``)
  in message content are properly paired before rendering. Appends a closing
  `` ``` `` if count is odd.
- **Versioning infrastructure** — `VERSION.txt` as single source of truth,
  `CHANGELOG.md` following Keep a Changelog 1.1.0. Hatchling reads version
  from `VERSION.txt` at build time via `[tool.hatch.version]`.

### Changed

- **Widget consolidation** — reduced from 5–8 widgets per message (header
  Static, 1–3 content Statics, 1–2 Collapsibles, divider) to 2 widgets
  (header Static + content Static). Eliminated `Collapsible` widget usage
  that was causing freezes at 200+ messages.
- **`_mount_message` rendering** — now builds a single Rich Markdown string
  per message instead of mounting separate widget nodes for each content
  part. Thinking markers become blockquotes, file read markers become
  `### Read:` headers, edit markers become Rich `Table` widgets.
- **Scroll detection** — replaced `watch_scroll_y` reactive watcher with
  `set_interval(0.3)` polling via `_check_scroll()`. Avoids cascade
  re-entry when mounting new widgets changes `max_scroll_y`.
- **Scroll keybindings** — changed from `scroll_down(N)` / `scroll_up(N)`
  to `scroll_relative(y=±5)` (Textual API: `scroll_down`/`scroll_up` take
  no positional arguments).
- **Session header `[dim]` markup** — replaced `[dim]{timestamp}[/]` with
  Rich `_` italics inside `Markdown()` strings (Textual markup doesn't
  render inside Rich `Markdown()`).
- **Divider line** — changed from Rich-styled `[dim]─...[/]` (rendered
  literally inside `Markdown()`) to plain Markdown `---` or separate
  `Static("[dim]─...[/]")` widget.
- **Version source** — `pyproject.toml` uses `dynamic = ["version"]` with
  `[tool.hatch.version]` reading from `VERSION.txt`.
- **Side-by-side edit diff in markdown export** — edits rendered as:
  ````md
  ### Edit: path/to/file

  ```diff
  -old line
  +new line
  ```
  ````

### Fixed

- **TUI freeze with 200+ message sessions** — three root causes fixed:
  1. Batch mounting 30 messages synchronously in `_load_initial_chunk()`
     blocked the event loop. Fixed by mounting one message per `call_later()`.
  2. `_mount_chunk()` mounted 10 messages synchronously in
     `_append_next_chunk()`. Fixed by routing through `_mount_next()`.
  3. `Collapsible` widgets per thinking/file-read block added ~500+ widgets
     for large sessions, overwhelming Textual's layout engine. Removed
     `Collapsible` in favour of inline markdown rendering.
- **Infinite loop in `to_markdown()`** — when a message had
  `THINKING_MARKER` but no matching `THINKING_END_MARKER`, `content.find()`
  returned -1, causing `pos` to never advance. Fixed with
  `if end == -1: end = len(content)` guard.
- **Infinite loop in `_mount_message()`** — same bug present in the TUI
  rendering path. Applied the same `end = len(content)` guard.
- **Export formatting breaks at first unpaired `` ``` ``** — messages with
  unpaired backtick code fences (indices 72, 102, 103, 242 in the
  226-message session) opened a code block that swallowed the rest of the
  document. Fixed with `close_fences()`.
- **File-read `~~~` code fence collision** — when quoted file content
  contained `~~~`, it closed the enclosing code block prematurely. Fixed
  with `code_fence()`.
- **`[dim]` / `[/]` rendering literally** — Textual markup passed inside
  `Markdown()` was rendered as literal text. Fixed by using pure markdown
  syntax or separate `Static()` widgets.
- **`can-focus: false` CSS error** — invalid Textual CSS property caused
  TUI crash on launch. Removed.
- **Scroll timer cascade** — `watch_scroll_y` triggered `_load_more()`
  even when content fit on screen (`max_scroll_y = 0`; `0 >= -5` was
  true). Fixed by requiring `max_y > 5`.
- **Duplicate `_mount_message` definition** — old implementation remained
  after class rewrite, creating an unreachable code path. Removed.
- **Unused imports** — `Collapsible`, `Horizontal`, `BATCH_SIZE` removed
  after widget consolidation.
- **`<!--/THINKING-->` leaking into Markdown export** — `pos = end` did
  not skip past `THINKING_END_MARKER`, so the HTML comment appeared
  literally in exported files. Fixed with
  `pos = end if end >= len(content) else end + len(THINKING_END_MARKER)`.
- **Edit-Tool markers not closed** — `EDIT_MARKER` concatenation with
  `EDIT_OLD_START` created ambiguous HTML comment boundaries. Fixed by
  inserting `-->` between the path and `EDIT_OLD_START`.

### Removed

- `Collapsible` widget usage — replaced by inline blockquote/code-block
  markdown rendering.
- `BATCH_SIZE` constant — superseded by `INITIAL_CHUNK` + `SCROLL_CHUNK`.
- Original `.venv/`, `ccs.egg-info/`, `__pycache__/` directories from pip
  era. Cleaned up as part of UV migration.

### Security

- SQLite `PRAGMA query_only=ON` added to all reader connections,
  preventing accidental write operations.


## [0.1.1] - 2026-05-20 … 2026-05-21

### First development session — Migration, sidebar, markers, export fixes

### Added

- **Tool-error state annotation** — when a tool call fails (status `"error"`),
  the message body is annotated with `[ERROR: {message}]` so the failure is
  visible in both TUI and export.
- **Session title sidebar** — sidebar now shows the session title (no tool
  name or timestamp). Titles longer than the sidebar width wrap with proper
  indent via `padding-left: 2`. Gray selection highlight using `$boost`.
  Vertical `margin-bottom: 1` between items for readability.
- **Fixed session header** — session info (title, ID, tool, started,
  directory) extracted into a pinned `SessionHeader` widget that stays
  visible above the scrollable chat area.
- **Thinking / reasoning rendering** — originally implemented using Textual
  `Collapsible` widgets per thinking block (collapsed by default, clickable
  to expand). Later replaced in 0.2.0 with inline blockquote rendering for
  performance.
- **File read rendering** — originally implemented using Textual
  `Collapsible` widgets per file read. Later replaced in 0.2.0 with
  `### Read: {path}` header + `~~~` fenced code block.
- **Read tool output cleanup** — `_clean_read_output()` strips XML wrapper
  (`<path>`, `<type>`, `<content>`) and line-number prefixes (`1:`, `2:`,
  etc.) from file content displayed in chat messages.
- **GeminiReader role mapping** — Gemini uses `type` field values
  (`user`, `gemini`, `info`, `error`) instead of standard `role`. Reader
  maps these to `user`/`assistant` with fallback for unknown types.
- **CLI `resolve_session()`** — `export` and `show` commands accept either
  a raw session ID or a partial (case-insensitive) title substring match.
  Ambiguous matches are printed for disambiguation.
- **Backup rotation** — when a backup destination already exists, the
  existing file is renamed with a `.old_YYYYMMDD_HHMMSS` suffix before
  the new backup is written, preventing accidental data loss.
- **Export filename defaults to title** — output file defaults to
  `{sanitised_title}.{ext}` instead of the raw session ID. Duplicate
  extensions stripped (e.g., `Plan from HANDOVER.md` → `Plan from
  HANDOVER.md`, not `.md.md`).
- **SQLite busy/timeout handling** — all SQLite connections use
  `timeout=10.0` and `PRAGMA query_only=ON` for safe concurrent reads
  alongside a running agent.
- **Emoji-free formatting** — removed `🧠` emoji from thinking blockquote
  header in response to user feedback. Blockquote reads `> **Thinking:**`.

### Changed

- **Project scaffold** — migrated from `pip` + `setuptools` to `uv` +
  `hatchling`. `pyproject.toml` uses `hatchling.build` backend.
- **Project location** — original copy from
  `~/Downloads/backup/data/conversational-chat-storer/` to
  `~/Documents/non-git-code/conversational-chat-storer/` for active
  development. Original backup preserved unchanged.
- **Python minimum** — bumped from `>=3.8` to `>=3.12`.
- **Dependencies** — `pyproject.toml` now lists `textual>=1.0.0` and
  `rich>=13.0.0` explicitly (previously empty array).
- **Type hints** — modernised to 3.12 syntax:
  `list[X]` not `List[X]`, `X | None` not `Optional[X]`.
  Removed all `from typing import List, Optional` across all files.
- **Sidebar width** — increased from 28 to 40 characters for readable
  title display.
- **`SessionItem` height** — changed from fixed `height: 2` to auto-height
  with `padding-left: 2` for wrapped title indent.
- **CLI `cmd_list` display** — shows session title (not raw ID) as the
  primary column.
- **CLI `cmd_show`** — uses `resolve_session()` for title-based lookup.
- **Export session resolution** — `cmd_export` uses `resolve_session()`
  instead of `find_reader()` + direct `get_session()`.
- **README.md** — original README included with project.

### Fixed

- **Sidebar showing only session IDs** — originally displayed raw
  `opencode_ses_...` IDs. Changed to use the `title` column from the
  database.
- **Sidebar alignment / wrap mismatch** — title line had `prefix "▸ "`
  (3 visual chars) but wrapped continuation lines started at column 0.
  Fixed by truncating titles to 35 characters and matching info-line
  indent to title-line prefix.
- **Sidebar multi-line title clip** — `height: 2` widget clipped titles
  to 2 lines. Changed to auto-height with `padding-left: 2`.
- **Sidebar tool/time info line** — removed the secondary info line
  (tool name + timestamp) that cluttered the sidebar.
- **Session header scrolls away** — session info was inside `ChatArea`
  (a `VerticalScroll`), so it scrolled out of view. Extracted into a
  pinned `SessionHeader` widget.
- **`ChatArea` not scrollable** — `VerticalScroll` had no constrained
  height, so it expanded to fit all content. Added `height: 1fr` CSS.
- **Read tool output: raw XML and line numbers visible** — file content
  included `<path>`, `<type>`, `<content>` tags and `1:` / `2:` line
  number prefixes. Fixed with `_clean_read_output()`.
- **Thinking not distinguishable from answers** — `<thinking>` tags were
  rendered literally. Fixed with `<!--THINKING-->` / `<!--/THINKING-->`
  markers that become blockquotes in export and were Collapsible in TUI.
- **File-read not clearly contained** — file content had no clear visual
  boundary and its markdown could break the surrounding formatting.
  Fixed with `<!--FILEREAD:path-->...<!--/FILEREAD-->` markers rendered
  as `### Read:` headers with `~~~` code blocks.
- **Markdown code-block collision in file reads** — ` ``` ` used as code
  fence, but file content containing ` ``` ` closed it prematurely.
  Initial fix used `~~~` fences. Later hardened with `code_fence()`.
- **No emojis in UI** — removed `🧠` emoji from thinking blockquote
  header per user request.
- **Export filename double extension** — session title `Plan from
  HANDOVER.md` produced `Plan from HANDOVER.md.md`. Fixed by stripping
  existing extension before appending.


## [0.1.0] - 2026-02-24

### Initial public release (by original author)

### Added

- Project scaffold: Python 3.8, `pip` + `setuptools` build system.
  Single editable install (`pip install -e .`).
- 4 readers: Claude Code (JSONL files in `~/.claude/`), Gemini CLI
  (JSON files in `~/.gemini/`), OpenCode (SQLite in
  `~/.config/opencode/opencode.db`), Kilocode (SQLite in
  `~/.local/share/kilo/`).
- CLI commands: `list`, `show`, `export`, `paths`, `tui`, `backup`,
  `restore`, `backups`. `list` and `export` accept `ls` / `-o` aliases.
- Export to markdown (`.md`) and JSON (`.json`) formats via
  `Session.to_markdown()` and `Session.to_dict()`.
- Backup/restore for cross-device chat storage migration:
  - Generates SHA-256 manifest for integrity verification.
  - Creates timestamped backup directories.
  - Supports full restore from a backup directory.
- TUI built with Textual + Rich, showing session list in a 28-char
  sidebar and messages in a scrollable markdown-rendered chat area.
  Selected session highlighted with primary color background.
- `Session` and `Message` data models with `to_dict()` and
  `to_markdown()` serialisation. `Message.__init__` accepts
  `str`, `list`, or `dict` content values.
- Reader pattern: each tool has its own reader class inheriting
  from `BaseReader` with `list_sessions()` / `get_session()` /
  `is_available()` / `get_storage_path()` methods.
- `OpenCodeReader` reads from `opencode.db` SQLite database with
  `session`, `message`, and `part` tables. Session ID prefixed
  with `opencode_`. Messages ordered by `time_created`.
- `KilocodeReader` reads from Kilocode SQLite database with
  same session/message/part structure. Session ID prefixed
  with `kilocode_`.
- `ClaudeReader` reads from JSONL conversation files in
  `~/.claude/projects/*/conversations/`. Session ID prefixed
  with `claude_`.
- `GeminiReader` reads from JSON files in
  `~/.gemini/tmp/<project-hash>/chats/`. Maps Gemini `type`
  field (`user`, `gemini`, `info`, `error`) to `role`.
  Session ID prefixed with `gemini_`.
- 10 CLI commands with argument parsers: list, show, export,
  paths, tui, backup, restore, backups, and their aliases.

[0.2.0]: https://github.com/anomalyco/opencode/issues
[0.1.1]: https://github.com/anomalyco/opencode/issues
[0.1.0]: https://github.com/anomalyco/opencode/issues
