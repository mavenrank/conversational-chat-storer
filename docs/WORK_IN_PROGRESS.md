# Paused work — October 2, 2026

The user asked to stop, commit the current work, and resume only when requested.
This is a checkpoint, not a claim that every change has completed live validation.
Do not continue implementation, merge, or start scheduled follow-ups until asked.

## Branch and publishing

- Current branch: `fix/codex-history-and-loading`.
- Canonical remote: `github`, `mavenrank/conversational-chat-storer`.
- The user authorized committing and pushing all current changes. Save the checkpoint
  on this branch; do not merge unfinished work into main.
- The earlier repository migration and history cleanup are already complete.
  Do not repeat them. Keep documentation and commit descriptions free of model
  authorship/provenance statements.
- Local diagnostics, screenshots, chat samples, and logs stay in ignored
  `.migration/`; they must not be committed.

## Implemented

- Codex CLI/Desktop adapter: native identities, titles, current and archived
  rollouts, distinct forks, child/automatic review runs, modern display events,
  legacy fallback, deduplicated usage, model information, and meaningful activity
  dates. Read-only native SQLite metadata supports WAL. Full details use bounded
  caching; first listings use metadata/head/tail reads.
- Shared registry scans reduce repeated initial loading. Frontend pagination loads
  every chat, periodic refresh updates active chats, and incomplete counts are
  shown honestly. UTC serialization and local date formatting are covered by tests.
- Fixed Markdown parsing stalls caused by Windows newlines and malformed headings.
- A shadcn-style sidebar with accessible mobile drawer and persistent resizable
  desktop width. Transcript splits collapse to one readable pane when narrow.
- Geist Sans throughout the UI. Removed the monospace font package and compacted
  chat rows, headers, tabs, message spacing, and navigation.
- Bundled Claude, OpenAI, OpenCode, Gemini, and Kilocode SVG brand icons; compact
  source filters and larger source-color rails/badges.
- Settings cog at the far right, with working theme and agent-history preferences.
- Latest selection change: 25% source-color fill, 70% border, additional ring,
  full-height thicker rail, semibold title, and check mark. This last change still
  needs visual verification in light/dark themes.
- New active verified pricing catalog, dated 2026-10-02, with primary provider
  source links. Background cost service reads local request usage without sending
  chats to external services. Recorded costs remain separate from current standard
  API estimates. Unknown models and missing usage remain unpriced.
- Per-request Codex context tiers and model switches; native ledger/event
  deduplication. Claude cache reads, short writes, and one-hour writes are separate.
  Added Settings cost progress, coverage, unknown model list, and transcript estimate
  labels. Older unused Modelly/YAML utilities remain separate.

## Validation at checkpoint

- Backend: 38 tests passed, including 5 new pricing tests.
- Frontend: 5 tests passed; TypeScript and production Vite build passed.
- Earlier read-only Codex verification matched all local native IDs, human/child
  grouping, archive coverage, and modern transcript prose. Diagnostics are private.
- Earlier browser checks covered 772×489 and 1440×900 layouts, mouse/keyboard resizing,
  width reset, settings focus/theme controls, search persistence, and narrow agent
  navigation. A 390×844 mobile check began but drawer/focus validation is unfinished.
- The latest selection styling, container-query cascade fix, and cost UI have not
  received final browser/live API verification.
- Ruff previously reported pre-existing repository issues (FastAPI Query defaults,
  some line lengths and zip strictness). Unrelated automatic fixes were removed.
  Check only relevant changes before deciding whether broader cleanup is warranted.

## Runtime and next steps when asked to resume

1. Inspect Git status and this branch before editing. Preserve any intervening work.
2. Format newly rewritten TSX/CSS files for readability without unrelated changes.
3. Review pricing implementation against actual source records:
   - The local Modelly API was unavailable; active prices use the verified JSON.
   - Estimates use current standard text API rates, not historical/subscription
     bills. Service-tier premiums, regional modifiers, multimedia, tools, and
     cache-storage fees are outside this estimate.
   - Internal review models and models without a verified entry must stay unknown.
   - Check source-file changes during calculation, summary/detail cache signatures,
     background progress/errors, model changes, duplicate request IDs, and whether
     usage missing from a transcript needs an explicit partial-coverage flag.
   - Settings Recheck currently requests the snapshot; background refresh has a
     30-second throttle. Confirm the button behavior matches its wording.
4. Restart only the verified CCS backend process so the new `/api/costs` route
   and response fields load. The API runs on 127.0.0.1:8787; frontend Vite on :5173.
   Existing API process was started without auto-reload. Inspect exact executable,
   command, workspace, and port owner before stopping it. Use hidden windows for
   background helpers. Logs live in ignored `.migration/`.
5. Exercise live costs: check background completion, reported-zero preservation,
   totals including agent runs, partial/unpriced labels, and a real Codex estimate.
   Ensure history loading remains responsive while pricing runs.
6. Finish browser checks at desktop, 772×489, and 390×844. Verify selected cards are
   unmistakable in both themes, brand filters, mobile drawer focus/auto-close,
   resizing, settings, narrow agent navigation, font sizes, and no page overflow.
   Restore theme/preferences and reset temporary viewport overrides afterwards.
7. Save a current screenshot in ignored `.migration/` and show it with the result.
8. Run checks appropriate to any further fixes, inspect the final diff, commit/push
   additional work, and create/attach a neutral PR if appropriate. Do not force push
   or merge main merely to publish this feature branch.

Browser context at pause: Codex in-app browser ID 2; healthy preview tab ID 3 at
`http://127.0.0.1:5173/`. Older user tab ID 2 had a focus timeout after dependency/HMR
changes. Reuse the browser binding; do not close the user's tab. Browser handles
may need rebinding after resumption. Read computer-use documentation before acting.
The temporary viewport override should be reset as part of pausing.

The private live Codex diagnostic has a hardcoded prompt count for an actively
changing chat. Treat that expected count as stale; fixture test counts remain
valid. Do not alter recorded chats or publish private diagnostic data.
