# History and UI work — October 2, 2026

The paused checkpoint was resumed and its remaining implementation and validation
completed. This file records the resulting behavior and follow-up boundaries.

## Publishing

- Feature branch: `fix/codex-history-and-loading`.
- Canonical remote: `github`, `mavenrank/conversational-chat-storer`.
- Publish through a pull request into `main`; the earlier repository migration
  is complete and does not need to be repeated.
- Local diagnostics, screenshots, chat samples, and logs remain in ignored
  `.migration/` and must not be committed.

## Delivered

- Codex CLI/Desktop history uses native identities and titles, includes local
  current and archived rollouts, keeps actual forks distinct, and attaches child
  and automatic review runs to their parent. Modern display events and legacy
  records are deduplicated, including request usage. Native SQLite is read-only
  and supports WAL. Bounded head/tail and detail caches reduce listing work.
- Shared registry scans, full frontend pagination, periodic refresh, explicit UTC
  serialization, and local date display keep active history current. Counts that
  require opening a transcript are marked as incomplete.
- Fixed Markdown parsing stalls from Windows line endings and malformed headings.
- Added a shadcn-style sidebar with persistent desktop resizing and an accessible
  mobile drawer. Switching between mobile and desktop restores its pixel width.
  Agent transcripts use a resizable split when space permits and one readable
  pane with Back to chat when narrow.
- Geist Sans replaces monospace presentation. Compact typography, spacing,
  navigation, and transcript metadata fit small windows.
- Bundled source SVG logos, source badges and rails, and a clearly selected card
  with source-color fill, border, ring, full-height rail, and check mark.
- Far-right Settings cog with theme, agent-history preferences, and cost coverage.
- Verified standard API pricing catalog dated 2026-10-02. Background pricing keeps
  source-recorded costs separate from estimates and preserves recorded zeroes.
  Per-request model/context tiers, cache categories, and response deduplication
  are covered by tests. Missing rates or usage remain partial or unavailable.
- Recheck explicitly starts a background refresh. Progress preserves the last
  completed totals, read failures can be retried, and active chats keep a marked
  last-priced snapshot while new usage is awaiting calculation.

## Validation

- Backend: 41 tests passed. Targeted Ruff checks and formatting passed for the
  new pricing modules and tests.
- Frontend: 5 tests passed, TypeScript checks passed, production Vite build passed.
- Read-only local verification matched all 355 native Codex thread identities:
  72 human chats, including 3 archives, and 283 child runs. Modern display prose
  matched across 71 human chats; the remaining chat uses the legacy format.
  Counts are a snapshot and grow as the source histories change.
- Codex listing measured 0.468 seconds cold and 0.032 seconds warm in that check.
- Live cost refresh processed 768 sessions with no read failures. Source-recorded
  totals matched the stats endpoint. Manual refresh and a complete stable Codex
  estimate passed. The cost snapshot returned in 0.024 seconds.
- Browser checks covered 1440×900, 772×489, and 390×844: light/dark selected-card
  contrast, source icons, keyboard resizing and width reset, desktop/mobile
  transitions, drawer focus and close behavior, persistent search, settings,
  narrow agent navigation, compact typography, and no horizontal page overflow.
- Broader Ruff checks have existing unrelated issues, including FastAPI Query
  defaults and line lengths. They were not included in this work.

## Scope for future work

- Regular ChatGPT and cloud-only Work histories are not imported. See
  [history sources](history-sources.md) for the local histories CCS reads.
- API estimates use current standard text rates rather than historical invoices
  or subscription charges. Premium tiers, regional modifiers, multimedia, tool
  fees, and cache storage fees are outside their scope. See [pricing](pricing.md).
- Missing model IDs, internal review models, and models without verified rates
  stay unknown. Updating rates requires a reviewed catalog update.
- Native source files and databases remain read-only. Diagnostics should compare
  current records rather than assume fixed prompt or session counts.
- Development preview runs on `127.0.0.1:5173`, with API on `127.0.0.1:8787`.
  The backend does not auto-reload; after backend edits restart only the verified
  CCS process. Logs and private validation artifacts remain in `.migration/`.
