# Conversational Chat Storer — Web

A unified, read-only web viewer for chat history across AI coding tools. Reads
each tool's native storage directly: no wrapper, no daemon, no impact on the
tools themselves.

## Supported sources

| Tool | Storage | Status |
|------|---------|--------|
| OpenCode | `~/.local/share/opencode/opencode.db` (SQLite) | verified against real data |
| Gemini CLI | `~/.gemini/tmp/<projectHash>/chats/*.json` | verified against real data |
| Kilocode | `<VS Code globalStorage>/kilocode.kilo-code/tasks/<id>/` | verified against real data |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | verified against real data |
| Claude Code | `~/.claude/projects/<encoded-cwd>/<uuid>.jsonl` | verified against real data |

Every root can be overridden, which is what makes the app work on WSL, portable
installs, or a relocated `globalStorage`:

```
CCSWEB_OPENCODE_ROOT   CCSWEB_GEMINI_ROOT   CCSWEB_KILOCODE_ROOT
CCSWEB_CODEX_ROOT      CCSWEB_CLAUDE_ROOT   CCSWEB_ELIDE_THRESHOLD
CCSWEB_ARCHIVE_ROOT
```

## Running

Backend (Python, [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv venv
uv pip install -e ".[dev]"
uv run ccsweb --reload          # http://127.0.0.1:8787
```

Frontend ([bun](https://bun.sh)):

```bash
cd frontend
bun install
bun dev                         # http://localhost:5173
```

Vite proxies `/api` to the backend, so the browser stays on one origin.

## Design notes

### Structured blocks, not marker strings

A message body is a list of typed blocks (`text`, `thinking`, `tool_use`), and
each tool block carries a typed payload (`file_read`, `file_edit`, `command`,
`subagent`, …). The TUI predecessor embedded HTML-comment markers in one flat
string and re-parsed prose to render; keeping the structure lets the UI render
real diffs and subagent cards, and makes the markdown exporter a pure projection
rather than a second parser.

### Lazy payloads

Session responses omit file contents, command output, thinking bodies and
subagent results above `elide_threshold_bytes`, replacing them with a byte size.
The client fetches a block's full payload only when its accordion is opened:

```
GET /api/sessions/{id}                    elided transcript
GET /api/sessions/{id}/blocks/{m}.{b}     one block, in full
```

Block addresses are positional (`<messageIndex>.<blockIndex>`) and derived from
the same ordered read on both requests, so nothing needs persisting.

### Tabs and panes

Sessions open as browser-style tabs, persisted across reloads. A single click
opens a *preview* tab (italic) that the next preview replaces; double click pins
it. `Ctrl+Tab` cycles, `Ctrl+W` closes. Subagents open in a resizable split pane
beside the parent so both can be read at once.

### Token counts

Agent loops resend the whole conversation on every request, so summing
per-request `input` across a session counts the same context dozens of times —
one 3-task kilocode dataset totalled 4.5M that way against 70k actually
generated. The UI therefore leads with **output** tokens and keeps the
input/cached/thinking breakdown in a tooltip.

### Archive

`POST /api/archive/run` (the **Backup** button) snapshots every session into
`~/.ccsweb/archive` using this app's normalised schema, so restoring never
depends on the original tool's format still being parseable. Content-hashed, so
repeat runs only write what changed. Strictly additive — it never deletes from a
source.

### Subagents

Delegated runs are stored by these tools as ordinary sessions, which is why they
previously appeared as normal chats — on the reference OpenCode store, 161 of
251 sessions (64%) were subagent children. They are detected via
`session.parent_id` and via the `task_id:` prefix OpenCode writes into `task`
tool output, hidden from the default listing, and shown inline under the call
that spawned them.

### Reading live stores safely

Everything is opened read-only, and SQLite is opened with `immutable=1` so a
running agent is never locked or blocked. Malformed JSON lines are skipped
rather than raised, because transcripts are frequently mid-write.

## Testing

```bash
cd backend
uv run pytest                                  # unit tests over synthetic fixtures
uv run python scripts/verify_sources.py        # assert parsing rules against your real data
```

`verify_sources.py` is standard-library only and runs before dependencies are
installed. It checks the invariants that the source adapters depend on — Gemini
snapshot de-duplication, OpenCode subagent classification, task-id linking — and
fails loudly if a tool changes its layout.

See [`CHANGELOG.md`](CHANGELOG.md) for the specific bugs this rewrite fixes and
the evidence behind each one.
