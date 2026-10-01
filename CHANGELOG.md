# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed (data correctness)

- **One conversation was listed as seven sessions.** Claude Code writes a brand
  new transcript file on every resume/fork, each containing the *entire* prior
  history. All seven reference transcripts shared the same first-message uuid
  and were near-perfect prefixes of one another (963 → 1114 → 1157 → 1208 →
  1263 → 1277 → 1294 turns). Transcripts are now grouped into lineages by root
  uuid; only the longest is listed and the rest are attached as `forks`.
- **Token counts were inflated 3.3x.** Claude Code splits a single API response
  across several assistant records and repeats the identical `usage` object on
  each, so summing per record triple-counted. On one transcript that read
  776,718 output tokens against a true 235,336. Usage is now summed once per
  `requestId` (falling back to `message.id`), and `Message` carries a
  `request_id` so the detail path dedupes the same way.
- **Message counts were meaningless.** "580 messages" counted the agent talking
  to itself. Claude Code also files tool *results* as `user` records — 497 of
  515 on the reference transcript — so counting by role was no better. A human
  prompt is now identified as a user record whose content carries no
  `tool_result` block: 18, not 515, not 1294. Every adapter populates
  `user_message_count`, and the UI leads with it.
- **OpenCode sessions had no token figures at all.** The list view never
  populated `usage`. Totals are now aggregated per session from `step-finish`
  parts (~8.4k rows, ~2.5s on a 457 MB store) and cached against the database
  mtime.

### Changed (space + legibility)

- Markdown gained tables, blockquotes and horizontal rules; GFM tables were
  previously rendered as raw pipe-delimited text.
- User turns use a dedicated `--user-surface` token — a real surface several
  steps off the page background, not a 7%-opacity tint — with a matching border
  and the label "User".
- Consecutive agent turns no longer repeat their header. A run of 40 tool calls
  renders as one block with a single heading instead of announcing "Agent" 40
  times.
- Session list rows went from four lines to two: the source is a 3px colour bar
  instead of a text label, and date/prompts/tokens/subagents/project collapse
  onto one 11px line with detail in tooltips.
- Source names in the nav are set in their own colour instead of pairing a
  coloured dot with plain text. The subagent pill is now plain `⑂n`.

### Changed (density + typography pass)

- **Self-hosted Geist.** `@fontsource/geist-sans` and `@fontsource/geist-mono`
  ship the woff2 files inside the packages, so Vite fingerprints and emits them
  into the bundle — the app renders correctly with no network at all. Only the
  weights in use are imported (sans 400/500/600/700, mono 400/500); each weight
  is a separate file, so pulling the full 100–900 range would ship ~9x the bytes
  for nothing. Cascadia Code is gone; fallbacks are system faces only.
- **One type scale instead of eight.** The UI had accumulated `text-[10px]`
  through `text-[13.5px]` in arbitrary steps, which is what made it feel
  cramped. Now: 11px caps labels, 12px metadata, 13px UI text, 14–15px body,
  larger for headings. Base font raised 14px → 15px, prose line-height to 1.75.
- **Vertical rhythm.** Message turns went from `py-3 pl-8` to `py-7 pl-14` with
  a separator between them; tool rows from `py-1` to `py-2`; session list rows
  from `py-2.5` to `py-4`; nav 48px → 56px; tabs 36px → 44px; controls 28/32px →
  32/36px. Block spacing went from `space-y-px` (1px!) to `space-y-2`.
- **Session header metadata** is 13px with `·` separators, so
  source/date/messages/tokens/cost read as a list rather than one run-on string.

### Added

- **Claude Code adapter.** Reads `~/.claude/projects/<encoded-cwd>/<uuid>.jsonl`.
  Verified against 7 real transcripts (9,193 records): titles resolve from
  `ai-title`/`custom-title` records rather than the first prompt, and 3,248 of
  3,250 `tool_use` blocks join to their result via `tool_use_id`. Results are
  collected in a first pass because Claude Code emits them on the *following*
  user record, not on the assistant turn. Subagent handling via `isSidechain` is
  implemented to spec but unverified — the reference dataset contained no
  sidechains and no `Task` calls.
- **Browser-style tabs.** Sessions open as tabs, persisted to `localStorage` so
  the working set survives a reload. Single click opens a preview (italic,
  replaced by the next preview), double click pins it. `Ctrl+Tab` cycles,
  `Ctrl+W` closes, middle click closes.
- **Subagent split pane.** Subagents open in a resizable pane beside the parent
  transcript, reachable both from the `Task` tool call and from buttons in the
  session header. Drag the divider to resize; double click to reset.
- **Local archive** (`ccsweb/archive.py`, `POST /api/archive/run`). Snapshots
  every session into `~/.ccsweb/archive` in this app's normalised schema, so
  history survives a source tool pruning its store or being reinstalled.
  Content-hashed, so re-running only writes what changed; strictly additive and
  never deletes from a source. Stores the full payload rather than the elided
  form, otherwise the archive would drop the file contents worth keeping.

### Changed

- **Token figures are no longer summed into one headline.** The sidebar read
  "Tokens 4.70M" for what was, in reality, 3 kilocode tasks and 11 Gemini
  sessions. That number was 82 API requests' worth of `tokensIn` (2.64M — the
  same conversation resent every turn) plus `cacheReads` (1.81M) added on top.
  Actual text generated: 69,660 tokens. `/api/stats` now returns
  input/output/cached/thinking separately, and the UI leads with **output**,
  the only figure that reflects text the models really produced. The full
  breakdown is one hover away.
- **Real shadcn component layer** (`components/ui/`): Button, Badge, Tooltip,
  ToggleGroup, Separator, on shadcn's HSL token convention with light and dark
  themes. Sources moved from a sidebar into a top nav bar as a multi-select
  toggle group, where empty selection means "all".
- Typography flipped to sans-first with mono reserved for paths, sizes, models,
  timestamps and token counts. Contrast raised to near-black/near-white.
- Motion: a shared `cubic-bezier(0.32, 0.72, 0, 1)` easing across tabs, panes
  and accordions, plus enter animations on tabs and the split pane.

### Changed (previous pass)

- **Terminal-leaning theme.** The near-black base is kept, but surfaces now
  carry a slight blue cast across four elevation steps so stacked elements read
  as layered rather than flat. Accents are desaturated to roughly 40–55% chroma —
  saturated terminal colours are tiring over long reading sessions.
- **Tool rows are single lines, not cards.** Type is carried by a 2px coloured
  rail rather than a full border box, so a turn with a dozen tool calls reads as
  a compact list. Each tool family has its own hue and glyph: read `◇` cyan,
  write `+` green, edit `±` amber, command `$` orange, search `⌕` teal,
  subagent `⑂` violet, thinking `✻` grey.
- **Prompt-style role markers.** `❯` for user turns, `⏺` for the agent, `!` for
  errors, each with a matching left rail, replacing the per-turn pill badges.
- **Typography split.** Monospace is the default — paths, sizes, models,
  timestamps and token counts are all tabular so the metadata columns align.
  Prose switches to a proportional face at a larger size via `.prose-body`.
  Long directory paths are elided from the left, keeping the filename visible.

### Fixed

- `GET /api/sessions/{id}` returned 500 for every session.
  `ThinkingBlock` did not inherit `Heavy`, so it had no `elided` / `size_bytes`
  fields, and pydantic rejects assignment to undeclared fields — the first
  reasoning block in any transcript raised
  `ValueError: "ThinkingBlock" object has no field "size_bytes"`.
  `Heavy` now sits in its own section documenting the invariant, and two tests
  guard it: one asserting every category in `lazy._HEAVY_FIELDS` maps to a
  `Heavy` subclass with that field, and one running the real elision path over a
  block of every detail category.

## [0.1.0] - 2026-08-04

Initial scaffold of the web version of Conversational Chat Storer.

### Added

- **Structured content model.** Messages are modelled as a list of typed,
  discriminated blocks (`text`, `thinking`, `tool_use`) instead of a single flat
  string with embedded HTML-comment markers. Tool blocks carry a typed `detail`
  payload (`file_read`, `file_edit`, `file_write`, `command`, `search`,
  `subagent`, `generic`) so the web UI can render real diffs, file viewers and
  subagent cards without re-parsing prose.
- **Source adapter architecture** (`backend/ccsweb/sources/`) with one small
  module per tool and a shared `SourceAdapter` protocol.
- **Markdown exporter** (`backend/ccsweb/export/markdown.py`), ported from the
  TUI's exporter and driven by structured blocks rather than marker strings.
- `VERSION.txt` and this changelog.

### Fixed

Carried over from the TUI implementation, with root causes identified against
real on-disk data:

- **Subagent sessions were listed as ordinary chats (opencode).** The session
  list did not filter on `session.parent_id`. On the reference dataset this made
  161 of 251 sessions (64%) bogus top-level entries. Root sessions are now
  selected with `parent_id IS NULL`, and child sessions are attached to the
  originating `task` tool call. The link is resolved two ways: `session.parent_id`,
  and the `task_id: <session-id>` prefix that opencode writes into the `task`
  tool output.
- **Gemini listed the same conversation several times, one entry containing the
  whole chat.** Gemini CLI writes repeated *snapshots* of a live session to
  `~/.gemini/tmp/<projectHash>/chats/session-<ts>-<tag>.json`. Successive
  snapshots of one session share an internal `sessionId` but differ in filename,
  so de-duplicating by filename stem (as the TUI did) kept them all — the newest
  snapshot being a superset of the others. Sessions are now de-duplicated by the
  internal `sessionId`, keeping the snapshot with the latest `lastUpdated`.
- **Gemini metadata was discarded.** The reader only read `content`, dropping the
  `thoughts`, `tokens`, `model` and `toolCalls` fields that Gemini records on
  every assistant message. All four are now parsed.
- **Claude Code sessions were never found.** The reader looked for
  `~/.claude/projects/<project>/<session>/session.json` plus `messages.jsonl`.
  Claude Code actually stores one JSONL file per session at
  `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`. The adapter now reads
  that layout and uses `isSidechain` to identify subagent turns.
- **Gemini `logs.json` is no longer mistaken for session data.** It is a
  per-project flat log of user prompts, not a transcript.
- **OpenCode reported no token or cost figures.** Usage lives on `step-finish`
  parts (`tokens.{input,output,reasoning,cache.read}` plus `cost`), which the
  TUI skipped as "metadata only". They are now summed per message and per
  session.
- **OpenCode reasoning is parsed per provider.** Reasoning parts differ by model
  vendor. Measured over 4,746 parts in the reference store: `anthropic` (1,134)
  and providers with no metadata (3,351) put plain prose in `text`; `openai`
  (255) writes a `**Caption**` heading followed by the body on 150 parts and
  leaves `text` empty on the other 105, which carry only an opaque `itemId`;
  `copilot` (6) exposes no readable text. Captions are lifted into
  `ThinkingBlock.subject` so they match Gemini's `{subject, description}` shape,
  and text-less parts are dropped instead of rendering as empty accordions.
- **OpenCode synthetic text parts are hidden.** Parts flagged `synthetic` are
  harness nudges ("Continue if you have next steps…"), not model output.

### Performance

- Heavy payloads (file contents, command output, thinking bodies, subagent
  results) are elided from the session response and fetched per block when the
  user expands an accordion. Collapsed rows still show a byte size.
- The opencode database is opened with `immutable=1`, taking no locks against a
  possibly-running agent.

[Unreleased]: https://github.com/kaitranntt/ccs-web/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kaitranntt/ccs-web/releases/tag/v0.1.0
