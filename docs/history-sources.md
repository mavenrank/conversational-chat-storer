# History coverage

CCS currently reads local histories from Claude Code, Codex CLI/Desktop,
Gemini CLI, OpenCode, and Kilocode. The conversation's source is the application
that stored it, rather than the model it happened to use. Personal research and
planning chats belong here just as much as coding chats, when a supported source
has stored their transcript locally.

Regular ChatGPT and ChatGPT Work histories need a separate importer or supported
connection. They are not retrieved from a Codex login or its local rollout
directory. Cloud-only tasks without a local transcript are also outside the
current local-file adapters' coverage.

## Conversations and relationships

- Keep each genuine conversation and fork under its own native identity.
- Collapse repeated snapshots of the same native conversation, selecting its
  current indexed rollout where available.
- Include Codex's native archived conversations and label them as archived.
- Attach delegated runs to their parent conversation. **Include agent runs**
  also exposes them in the sidebar, including runs whose parent transcript is
  no longer available.
- Classify Codex Guardian approval reviews separately from delegated agents.
  **Show approval reviews** in Settings exposes their own parent section and
  history rows; it is off by default. Hiding reviews preserves their history,
  token usage, costs, and coverage in existing manual backups.
- Preserve human prompts, assistant replies, readable reasoning, tool calls and
  tool results in their recorded order. Do not count injected environment or
  developer instructions as human prompts. Encrypted reasoning is unavailable.

Codex Desktop's completed display items take precedence over duplicate wire
messages. Older CLI display events and wire-only transcripts are supported as
fallbacks, including histories containing more than one format version.
Image attachments currently appear as attachment markers; a complete media
viewer is still needed.

## Dates and loading

Creation time describes when the conversation began. Last activity includes
recent transcript progress as well as the native recency index; settings changes
alone do not make a quiet chat look newly active. Copied messages in forks retain
their original display timestamps when the source records them.

Internal timestamps use UTC. JSON responses include `Z`, and the viewer converts
them to the browser's local timezone. Older CCS snapshots containing naive UTC
dates remain compatible.

The Codex list reads its native metadata index and a bounded tail of changed
rollouts. Exact prompt/turn counts require opening the full transcript, so the
reader shows exact counts after loading the transcript. History rows keep their
metadata compact and stable. With no
native index, CCS scans rollouts and caches their summaries by file modification
time and size. Malformed trailing records from running chats are skipped and
re-read after the file changes.

All session pages are fetched; history is not limited to the API's default first
200 entries. Source, timeline and statistics requests share a short-lived index.
The timeline and open transcript refresh every ten seconds and on window focus.

## Live status and steady browsing

Codex status comes from recorded turn starts, progress, final replies,
completions, and interruptions. A compact green spinner denotes recent progress
on an unfinished turn. Archived chats are idle; an unfinished turn without
progress for ten minutes becomes unknown because a rollout cannot prove the
application is still running. Other adapters currently report unknown rather
than inferring liveness from a recent file modification.

Spinners rotate in eight steps over 1.6 seconds, with one shared viewport
observer. Offscreen rows and hidden pages do not animate; reduced-motion settings
also disable animation. There is no JavaScript animation loop or extra polling.

History refresh updates existing rows in place and appends new conversations.
Use **Sort by latest** to apply recency order explicitly. Source and visibility
views retain their own order during the current browsing session, including
sidebar hide/show and mobile transitions. Reloading begins in recency order.

Selected rows retain the same title weight and width as other rows. Selection
uses the source-color fill, border, and rail, plus accessible selected state.
