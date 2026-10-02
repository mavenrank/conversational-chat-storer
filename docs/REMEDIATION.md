# Quality-of-life remediation

Requested October 2, 2026. All current fixes are implemented and validated on
`fix/codex-history-and-loading`, awaiting merge through [PR #2](https://github.com/mavenrank/conversational-chat-storer/pull/2).
Mermaid and backup changes remain deferred. Each item identifies the exact files
and acceptance checks. GitHub issues stay open until their fixes land on `main`.

Validation: 49 backend tests, 10 frontend tests, targeted Ruff checks, TypeScript,
and production build passed. Browser checks cover concurrent refreshes, approvals,
clipboard scopes, table scrolling, and selection geometry across desktop/mobile.

## [Show reliable running status for local chats](https://github.com/mavenrank/conversational-chat-storer/issues/3)

Status: Implemented and validated; awaiting merge.

Active chats are indistinguishable from recently updated chats. Add a running indicator grounded in source lifecycle events, with an explicit unknown state when a source cannot establish liveness.

Remediation:

- [x] Define status metadata in `backend/ccsweb/models/session.py`.
- [x] Read Codex lifecycle events using bounded/cached reads in `backend/ccsweb/sources/codex.py` and `codex_index.py`; handle completion, interruption, and stale unfinished runs.
- [x] Display status in `frontend/src/components/SessionList.tsx` and `TranscriptView.tsx` without using recency alone as proof of running.
- [x] Test starts, completions, aborts, stale records, and concurrent live chats.
- [x] Use compact accessible spinners in `RunStatus.tsx` and `RunSpinner.tsx`.
- [x] Bound animation work using stepped CSS, one shared viewport observer, hidden-page pause, and reduced-motion support.
- [x] Keep the running count consistent with visible search/source filters.

Priority: current work.

Implemented and validated in [PR #2](https://github.com/mavenrank/conversational-chat-storer/pull/2); awaiting merge.

Validation: Lifecycle fixtures cover starts, final replies, completion, aborts, stale cached runs, and meaningful item-start timestamps. Live concurrent chats show compact spinners and completed chats lose them. Animation uses eight steps over 1.6 seconds; offscreen rows stop animating, hidden pages pause, and reduced motion disables it. Windows GPU counters describe the shared desktop process, so no feature-specific GPU percentage is claimed.

## [Keep the history list steady during concurrent chat updates](https://github.com/mavenrank/conversational-chat-storer/issues/4)

Status: Implemented and validated; awaiting merge.

Periodic recency refresh reorders multiple active chats, moving rows while the user is reading or selecting them.

Remediation:

- [x] Preserve existing visible chat positions during background refresh in `frontend/src/App.tsx` and `SessionList.tsx`.
- [x] Update titles, timestamps, and status in place; retain new chats and removed-chat handling.
- [x] Provide an explicit action to apply the latest recency order.
- [x] Preserve ordering across sidebar hide/show and responsive transitions.
- [x] Test concurrent updates, new chats, removals, and source filters.

Priority: current work.

Implemented and validated in [PR #2](https://github.com/mavenrank/conversational-chat-storer/pull/2); awaiting merge.

Validation: Concurrent refreshes preserve row positions while metadata changes. Unit checks cover additions/removals; live checks cover explicit sorting, source filters, sidebar hide/show, and mobile transitions. Prompt counts remain in the reader header so lazy count loading does not resize history rows.

## [Separate Guardian approval reviews from delegated agents](https://github.com/mavenrank/conversational-chat-storer/issues/5)

Status: Implemented and validated; awaiting merge.

Codex automatic approval/Guardian reviews currently appear as subagents, obscuring actual delegated work. Users need a separate visibility preference.

Remediation:

- [x] Classify approval reviews from native metadata in `backend/ccsweb/sources/codex.py` and `codex_index.py`.
- [x] Keep distinct review relationships/counts in `backend/ccsweb/models/session.py`.
- [x] Add independent listing support in `backend/ccsweb/registry.py` and `api/routes.py`; preserve cost accounting for hidden reviews.
- [x] Add a persistent Settings preference and separate review section in `frontend/src/App.tsx`, `TopNav.tsx`, and `TranscriptView.tsx`.
- [x] Test that delegated agents remain visible and review hiding does not alter history or costs.

Priority: current work. Default: approval reviews hidden.

Implemented and validated in [PR #2](https://github.com/mavenrank/conversational-chat-storer/pull/2); awaiting merge.

Validation: Native metadata separates Guardian reviews from true delegated agents. Default-off visibility works independently of the agent setting and closes an open approval pane when disabled. Live API checks preserve all identities, parent relationships, costs, and ordinary source counts; title-only matches are not classified as reviews.

## [Make transcript table borders and spacing consistent](https://github.com/mavenrank/conversational-chat-storer/issues/6)

Status: Implemented and validated; awaiting merge.

Markdown tables have inconsistent header, body, and outer borders; narrow panes can squeeze columns excessively.

Remediation:

- [x] Use one clearly visible border treatment for the outer frame, rows, and columns in `frontend/src/index.css`.
- [x] Match header/body padding and alignment in `frontend/src/components/Markdown.tsx`.
- [x] Keep row column boundaries consistent for uneven Markdown input.
- [x] Contain horizontal scrolling to the table and support keyboard access.
- [x] Verify light/dark themes and desktop/mobile sizes.

Priority: current work.

Implemented and validated in [PR #2](https://github.com/mavenrank/conversational-chat-storer/pull/2); awaiting merge.

Validation: Uneven Markdown rows retain the header's column count. Outer, row, and column borders share one color and padding. Light/dark checks pass; a phone-width table scrolls internally by keyboard while the document remains within the viewport.

## [Simplify and clarify message copy controls](https://github.com/mavenrank/conversational-chat-storer/issues/7)

Status: Implemented and validated; awaiting merge.

Repeated Answer and All buttons add visual clutter and can represent identical actions on plain-text messages.

Remediation:

- [x] Provide a compact, clearly named default copy action in `frontend/src/components/MessageView.tsx`.
- [x] Offer additional copy scopes only when they produce distinct content.
- [x] Improve labels, focus visibility, and copy feedback in `frontend/src/components/CopyButton.tsx`.
- [x] Verify user prompts, assistant prose, and messages containing reasoning/tools.

Priority: current quality-of-life work.

Implemented and validated in [PR #2](https://github.com/mavenrank/conversational-chat-storer/pull/2); awaiting merge.

Validation: Plain messages offer one copy action. Additional scopes appear in a compact disclosure only when they add content; collapsed reasoning/tool details are fetched only for the chosen scope. Live clipboard checks cover a user prompt and reasoning/tools, with copied feedback and Escape dismissal. Loading failures retain an honest retry state.

## [Identify the specific extension or tool in transcript rows](https://github.com/mavenrank/conversational-chat-storer/issues/8)

Status: Implemented and validated; awaiting merge.

Generic Extension rows do not identify the actual integration or operation being used.

Remediation:

- [x] Preserve native tool/server/function identifiers in `backend/ccsweb/sources/codex.py`.
- [x] Render concise, meaningful labels with access to the complete identifier in `frontend/src/components/BlockView.tsx`.
- [x] Keep unknown operations honest rather than guessing a tool name.
- [x] Test representative extension/MCP/native-tool records and lazy details.

Priority: current quality-of-life work.

Implemented and validated in [PR #2](https://github.com/mavenrank/conversational-chat-storer/pull/2); awaiting merge.

Validation: Web extensions identify Search, Open page, Find in page, and other recorded operations; MCP rows preserve server/tool identifiers. Native tests retain arguments and outputs, and live transcript checks show qualified names instead of generic Extension labels.

## [Keep selected chat rows from shifting in narrow history layouts](https://github.com/mavenrank/conversational-chat-storer/issues/11)

Status: Implemented and validated; awaiting merge.

Selecting a chat changes the title weight and adds a check mark, reducing available width. Narrow history rows can wrap differently and shift when selected.

Remediation:

- [x] Remove the selected-row check mark from `frontend/src/components/SessionList.tsx`.
- [x] Keep title weight and available width consistent for selected, unselected, and already-open chats.
- [x] Position the open-tab indicator without consuming title width.
- [x] Retain the visible source-color fill, border, and rail, with accessible selected state.
- [x] Verify row height, title width, and wrapping before/after selection in narrow layouts.

Priority: current work. Requested October 2, 2026.


Implemented and validated in [PR #2](https://github.com/mavenrank/conversational-chat-storer/pull/2); awaiting merge.

Validation: The check mark and selected-only title weight are removed. Open-tab dots use absolute positioning, so selecting or opening a chat does not consume title width. Browser checks confirm unchanged title width/height, row height, and font weight before/after real selection in narrow desktop and mobile layouts.

## [Add a Mermaid diagram viewer with code toggle and export](https://github.com/mavenrank/conversational-chat-storer/issues/9)

Status: Deferred.

Mermaid fences currently show only source code. Add an optional diagram view with a code/diagram toggle and an export action.

Remediation when scheduled:

- [ ] Add a lazy-loaded Mermaid renderer around fences in `frontend/src/components/Markdown.tsx`.
- [ ] Handle untrusted diagram input, parse errors, themes, and responsive sizing.
- [ ] Provide source/diagram switching and SVG/image export.
- [ ] Verify accessibility and preserve plain-code fallback.

Deferred at the user's request; do not implement in the current pass.
## [Plan automatic backups, alternate destinations, and incremental storage](https://github.com/mavenrank/conversational-chat-storer/issues/10)

Status: Deferred.

The user wants future automatic backups, configurable storage destinations, and gradual/block-level backup writes.

Remediation when scheduled:

- [ ] Design scheduling and destination preferences around `backend/ccsweb/archive.py`, configuration, and Settings.
- [ ] Compare content-addressed/block-level incremental storage with the current additive snapshots.
- [ ] Define restore verification, interruption recovery, retention, and destination failures.
- [ ] Preserve source stores and provide clear backup/restore status.

Deferred at the user's request; design and implementation require a later pass.
