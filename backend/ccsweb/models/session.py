"""Session, message and usage models.

Two levels of detail are exposed deliberately:

``SessionSummary`` is what the list view needs and must be cheap to produce —
adapters build it without parsing full transcripts. ``SessionDetail`` adds the
messages and is only built when a session is opened.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from ccsweb.models.blocks import Block

SourceId = Literal["claude", "gemini", "opencode", "kilocode", "codex"]

Role = Literal["user", "assistant", "system", "info", "error"]


class Usage(BaseModel):
    """Token accounting for one message or a whole session.

    Fields are optional because no single tool reports all of them: Gemini gives
    the full breakdown including ``cached`` and ``thoughts``, opencode reports
    input/output/reasoning, Claude Code reports cache reads and writes
    separately.
    """

    #: Uncached input; cached input is counted separately in cached_tokens.
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    thinking_tokens: int = 0
    tool_tokens: int = 0
    cost_usd: float | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_tokens(self) -> int:
        """Every token in one request.

        Correct for a *single* message — it reproduces the figure the provider
        itself reports. Do not sum it across a session: each request re-sends the
        whole conversation, so the context gets counted once per turn. Use
        :attr:`generated_tokens` or ``cost_usd`` for aggregates.
        """
        return (
            self.input_tokens
            + self.output_tokens
            + self.cached_tokens
            + self.thinking_tokens
            + self.tool_tokens
        )

    @property
    def generated_tokens(self) -> int:
        """Tokens the model actually produced.

        Safe to sum: output and reasoning are new on every turn, never resent.
        """
        return self.output_tokens + self.thinking_tokens

    @property
    def context_tokens(self) -> int:
        """Tokens fed back in as context.

        Grows roughly quadratically over a conversation because each turn
        resends everything before it. Meaningful per request, misleading as a
        sum, so it is reported separately and never folded into a headline
        "tokens used" figure.
        """
        return self.input_tokens + self.cached_tokens

    def __add__(self, other: "Usage") -> "Usage":
        cost: float | None
        if self.cost_usd is None and other.cost_usd is None:
            cost = None
        else:
            cost = (self.cost_usd or 0.0) + (other.cost_usd or 0.0)
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            thinking_tokens=self.thinking_tokens + other.thinking_tokens,
            tool_tokens=self.tool_tokens + other.tool_tokens,
            cost_usd=cost,
        )


class Message(BaseModel):
    """One turn in a conversation."""

    id: str
    role: Role
    blocks: list[Block] = Field(default_factory=list)

    started_at: datetime | None = None
    completed_at: datetime | None = None

    model: str | None = None
    provider: str | None = None
    usage: Usage | None = None

    #: Identifies the API response this turn came from. Several turns can share
    #: one — Claude Code splits a response across records and repeats the usage
    #: object — so totals must be summed once per request, not per message.
    request_id: str | None = None

    #: True when this turn belongs to a subagent rather than the main thread.
    is_sidechain: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_ms(self) -> int | None:
        """How long the model took to produce this turn."""
        if self.started_at is None or self.completed_at is None:
            return None
        delta = (self.completed_at - self.started_at).total_seconds() * 1000
        return int(delta) if delta >= 0 else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def text(self) -> str:
        """Concatenated prose, used for search and previews."""
        return "\n".join(b.text for b in self.blocks if b.kind == "text")


class ProjectRef(BaseModel):
    """The workspace a session belonged to."""

    #: Stable identifier, source-specific (a path hash for Gemini/Claude, a row
    #: id for opencode).
    id: str
    name: str = ""
    path: str = ""


class SessionSummary(BaseModel):
    """List-view metadata. Must be cheap for adapters to produce."""

    id: str
    source: SourceId
    title: str = ""
    project: ProjectRef | None = None
    cwd: str = ""

    created_at: datetime | None = None
    updated_at: datetime | None = None

    #: Every turn, user + assistant. Useful, but a poor headline: agents emit
    #: dozens of turns per human instruction.
    message_count: int = 0
    #: Turns the human actually typed. This is what the UI leads with.
    user_message_count: int = 0
    models: list[str] = Field(default_factory=list)
    #: Provider/gateway ids the session used (opencode's ``providerID``).
    #: Required for pricing: the same model costs different amounts on
    #: OpenCode Go versus Zen, so the model id alone cannot price a session.
    providers: list[str] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)

    #: Set when this session is itself a subagent run. Such sessions are hidden
    #: from the default list and surfaced inline under their parent instead.
    is_subagent: bool = False
    parent_session_id: str | None = None
    subagent_count: int = 0

    #: Alternate transcripts of the same conversation. Claude Code writes a new
    #: file on every resume/fork, each containing the whole prior history, so one
    #: conversation can appear as a dozen near-identical sessions. Only the
    #: longest is listed; the rest hang off it here.
    is_fork: bool = False
    fork_of: str | None = None
    fork_count: int = 0

    #: Where the data came from on disk, shown in the UI and used for debugging.
    source_path: str = ""


class SessionDetail(SessionSummary):
    """Full transcript."""

    messages: list[Message] = Field(default_factory=list)

    #: Subagent runs spawned by this session, resolved from the tool calls.
    subagents: list[SessionSummary] = Field(default_factory=list)

    #: Earlier/alternate transcripts of this same conversation.
    forks: list[SessionSummary] = Field(default_factory=list)
