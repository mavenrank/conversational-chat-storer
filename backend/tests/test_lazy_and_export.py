"""Lazy elision and markdown export."""

from __future__ import annotations

from ccsweb.export.markdown import session_to_markdown
from ccsweb.lazy import elide_session, locate_block, parse_block_ref
from ccsweb.models import (
    FileReadDetail,
    Message,
    SessionDetail,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    Usage,
)


def _session() -> SessionDetail:
    big = "x" * 5000
    return SessionDetail(
        id="opencode:s1",
        source="opencode",
        title="Test session",
        messages=[
            Message(
                id="m0",
                role="user",
                blocks=[TextBlock(text="do the thing")],
            ),
            Message(
                id="m1",
                role="assistant",
                model="claude-sonnet",
                usage=Usage(input_tokens=100, output_tokens=20, cost_usd=0.001),
                blocks=[
                    ThinkingBlock(text=big, subject="Planning"),
                    ToolUseBlock(
                        name="read",
                        detail=FileReadDetail(path="a.py", content=big),
                    ),
                    TextBlock(text="Done."),
                ],
            ),
        ],
    )


def test_heavy_payloads_are_elided_with_sizes():
    session = elide_session(_session(), threshold=2000)
    thinking, tool, text = session.messages[1].blocks

    assert thinking.elided is True
    assert thinking.text == ""
    assert thinking.size_bytes == 5000

    assert tool.detail.elided is True
    assert tool.detail.content == ""
    assert tool.detail.size_bytes == 5000

    # Short prose is never elided — it is the thing you actually read.
    assert text.text == "Done."


def test_small_payloads_stay_inline():
    session = _session()
    session.messages[1].blocks[0].text = "short"
    session = elide_session(session, threshold=2000)
    assert session.messages[1].blocks[0].elided is False
    assert session.messages[1].blocks[0].text == "short"


def test_block_refs_round_trip():
    session = _session()
    assert parse_block_ref("1.2") == (1, 2)
    assert parse_block_ref("nope") is None
    assert locate_block(session, "1.0").kind == "thinking"
    assert locate_block(session, "9.9") is None


def test_every_elidable_type_inherits_heavy():
    """Guard against the elision target drifting away from the model.

    pydantic raises on assignment to an undeclared field, so any block or detail
    that ``lazy`` writes ``elided``/``size_bytes`` onto must inherit ``Heavy``.
    ``ThinkingBlock`` did not, which turned every session fetch into a 500.
    """
    from ccsweb.lazy import _HEAVY_FIELDS
    from ccsweb.models.blocks import Heavy, ThinkingBlock
    from ccsweb.models import blocks as blocks_module

    assert issubclass(ThinkingBlock, Heavy)

    for category, field in _HEAVY_FIELDS.items():
        detail_cls = next(
            cls
            for cls in vars(blocks_module).values()
            if isinstance(cls, type)
            and issubclass(cls, Heavy)
            and getattr(cls.model_fields.get("category"), "default", None) == category
        )
        assert issubclass(detail_cls, Heavy), f"{category} must inherit Heavy"
        assert field in detail_cls.model_fields, f"{category} has no field {field!r}"


def test_elision_survives_every_detail_category():
    """Run the real elision path over one block of each category."""
    from ccsweb.models import (
        CommandDetail,
        FileEditDetail,
        FileWriteDetail,
        GenericDetail,
        SearchDetail,
        SubagentDetail,
    )

    big = "y" * 4000
    details = [
        FileReadDetail(path="a", content=big),
        FileWriteDetail(path="a", content=big),
        FileEditDetail(path="a", unified_diff=big),
        CommandDetail(command="ls", output=big),
        SearchDetail(query="q", output=big),
        SubagentDetail(agent_type="explore", result=big),
        GenericDetail(input={"a": 1}, output=big),
    ]
    session = SessionDetail(
        id="opencode:s",
        source="opencode",
        messages=[
            Message(
                id="m",
                role="assistant",
                blocks=[ThinkingBlock(text=big)]
                + [ToolUseBlock(name="t", detail=d) for d in details],
            )
        ],
    )

    elided = elide_session(session, threshold=2000)
    for block in elided.messages[0].blocks:
        target = block if block.kind == "thinking" else block.detail
        assert target.elided is True
        assert target.size_bytes == 4000


def test_markdown_export_shape():
    markdown = session_to_markdown(_session())

    assert markdown.startswith("# Test session")
    assert "**Source:** opencode" in markdown
    assert "### User" in markdown
    assert "> **Thinking — Planning**" in markdown
    assert "#### Read: a.py" in markdown
    assert "(model: claude-sonnet)" in markdown


def test_export_fence_cannot_be_escaped():
    """A file containing ``~~~`` must not break out of its own fence."""
    session = _session()
    session.messages[1].blocks[1].detail.content = "~~~\nnot the end\n~~~"
    markdown = session_to_markdown(session)
    assert "~~~~" in markdown, "fence should widen past the content"


def test_unbalanced_code_fence_is_closed():
    session = _session()
    session.messages[0].blocks[0] = TextBlock(text="```python\nprint(1)")
    markdown = session_to_markdown(session)
    assert markdown.count("```") % 2 == 0
