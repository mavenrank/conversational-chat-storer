"""Typed content blocks.

A message body is a list of blocks. Every block is discriminated on ``kind``,
and tool blocks carry a further ``detail`` payload discriminated on ``category``.

This replaces the TUI's approach of embedding HTML-comment markers
(``<!--THINKING-->``, ``<!--EDIT:...-->``) inside one flat string. Markers are
fine for a terminal renderer but force every consumer to re-parse prose. Keeping
the structure lets the web UI render diffs, file viewers and subagent cards
directly, and lets the markdown exporter stay a pure projection of this model.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Lazy-loading support
# --------------------------------------------------------------------------- #


class Heavy(BaseModel):
    """Base for anything whose bulk is elided until the user expands it.

    The session endpoint returns transcripts with heavy fields blanked and
    ``elided`` set, so opening a long session stays cheap. The client fetches the
    real content per block when an accordion is opened. ``size_bytes`` is always
    populated so the UI can show "12.4 KB" on a collapsed row.

    Inherited by every tool detail payload *and* by :class:`ThinkingBlock`.
    Anything ``ccsweb.lazy`` writes ``elided``/``size_bytes`` onto must inherit
    this — pydantic rejects assignment to undeclared fields, so forgetting it is
    a runtime error rather than a silent no-op.
    """

    #: True when the bulky field has been stripped from this response.
    elided: bool = False
    #: Size of the elided payload, in bytes, regardless of elision.
    size_bytes: int = 0


# --------------------------------------------------------------------------- #
# Tool detail payloads
# --------------------------------------------------------------------------- #


class FileReadDetail(Heavy):
    """A file the agent read."""

    category: Literal["file_read"] = "file_read"
    path: str
    content: str = ""
    truncated: bool = False


class FileWriteDetail(Heavy):
    """A file the agent created or overwrote."""

    category: Literal["file_write"] = "file_write"
    path: str
    content: str = ""


class FileEditDetail(Heavy):
    """An in-place edit.

    Sources supply edits in one of two shapes and the UI renders either:

    * ``old_text``/``new_text`` — opencode and Gemini give the before/after
      strings and the diff is computed client-side.
    * ``unified_diff`` — kilocode already stores a unified diff, so it is passed
      through verbatim rather than round-tripped through a reconstruction.
    """

    category: Literal["file_edit"] = "file_edit"
    path: str
    old_text: str = ""
    new_text: str = ""
    unified_diff: str = ""

    #: Reported by the source when available, otherwise derived client-side.
    additions: int = 0
    deletions: int = 0


class CommandDetail(Heavy):
    """A shell command execution."""

    category: Literal["command"] = "command"
    command: str
    output: str = ""
    exit_code: int | None = None


class SearchDetail(Heavy):
    """Glob / grep / web search."""

    category: Literal["search"] = "search"
    query: str
    output: str = ""


class SubagentDetail(Heavy):
    """A delegated sub-task.

    ``child_session_id`` points at a session the source tool stored separately.
    Resolving it is what stops subagents from appearing as ordinary top-level
    chats in the session list.
    """

    category: Literal["subagent"] = "subagent"
    agent_type: str = ""
    description: str = ""
    prompt: str = ""
    result: str = ""
    child_session_id: str | None = None


class GenericDetail(Heavy):
    """Anything without a first-class renderer."""

    category: Literal["generic"] = "generic"
    input: dict = Field(default_factory=dict)
    output: str = ""


ToolDetail = Annotated[
    Union[
        FileReadDetail,
        FileWriteDetail,
        FileEditDetail,
        CommandDetail,
        SearchDetail,
        SubagentDetail,
        GenericDetail,
    ],
    Field(discriminator="category"),
]


# --------------------------------------------------------------------------- #
# Blocks
# --------------------------------------------------------------------------- #


class TextBlock(BaseModel):
    """Prose, rendered as markdown by the client."""

    kind: Literal["text"] = "text"
    text: str


class ThinkingBlock(Heavy):
    """Reasoning / thought summary.

    ``subject`` is populated by Gemini, which stores thoughts as
    ``{subject, description, timestamp}`` records rather than raw text, and by
    OpenAI-family models, whose reasoning leads with a ``**Caption**`` heading.

    Inherits ``Heavy`` because reasoning bodies are collapsed by default and are
    elided from session responses: the subject is the accordion label, the body
    is fetched on expand.
    """

    kind: Literal["thinking"] = "thinking"
    text: str
    subject: str | None = None


ToolStatus = Literal["pending", "running", "completed", "error"]


class ToolUseBlock(BaseModel):
    """A tool invocation and its result."""

    kind: Literal["tool_use"] = "tool_use"
    tool_id: str | None = None
    name: str
    status: ToolStatus = "completed"
    error: str | None = None
    duration_ms: int | None = None
    detail: ToolDetail


Block = Annotated[
    Union[TextBlock, ThinkingBlock, ToolUseBlock],
    Field(discriminator="kind"),
]
