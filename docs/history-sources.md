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
- Attach delegated and automatic review runs to their parent conversation.
  **Include agent runs** also exposes them in the sidebar, including runs whose
  parent transcript is no longer available.
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
sidebar hides unavailable counts instead of displaying invented zeros. With no
native index, CCS scans rollouts and caches their summaries by file modification
time and size. Malformed trailing records from running chats are skipped and
re-read after the file changes.

All session pages are fetched; history is not limited to the API's default first
200 entries. Source, timeline and statistics requests share a short-lived index.
The timeline and open transcript refresh every ten seconds and on window focus.
