import pytest

from ccsweb.models import Message, SessionDetail, SessionSummary, TextBlock, Usage
from ccsweb.pricing.estimates import (
    codex_record_requests,
    estimate,
    price_request,
    transcript_requests,
)
from ccsweb.pricing.service import CostService
from ccsweb.sources.claude import _parse_usage


def test_openai_cache_and_reasoning_are_disjoint_and_long_context_is_per_request():
    short = Usage(
        input_tokens=100_000, cached_tokens=172_000, output_tokens=200, thinking_tokens=100
    )
    assert price_request("gpt-6.1-sol", "openai", short) == pytest.approx(0.2202)
    long = short.model_copy(update={"cached_tokens": 172_001})
    assert price_request("gpt-6.1-sol", "openai", long) == pytest.approx(0.4389002)
    # The cumulative input is over the tier boundary but neither request is.
    assert estimate([("gpt-6.1-sol", "openai", short)] * 2).estimated_usd == pytest.approx(0.4404)


def test_unknown_models_and_wrong_providers_remain_unpriced():
    usage = Usage(input_tokens=1000)
    assert price_request("made-up-free", "openai", usage) is None
    assert price_request("gpt-6.1-sol", "opencode-go", usage) is None
    result = estimate([("made-up-free", "openai", usage), ("gpt-6.1-sol", "openai", usage)])
    assert result.estimated_usd == 0.002
    assert not result.complete
    assert result.unpriced_models == ["made-up-free"]
    assert estimate([]).estimated_usd is None


def test_claude_cache_writes_are_not_charged_as_reads_and_split_usage_is_deduped():
    usage = _parse_usage(
        {
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 200,
            "cache_creation": {"ephemeral_1h_input_tokens": 50},
        }
    )
    assert usage.cached_tokens == 100
    assert usage.cache_write_tokens == 150
    assert usage.cache_write_1h_tokens == 50
    assert usage.total_tokens == 330
    assert (Usage() + usage).cache_write_tokens == 150
    messages = [
        Message(
            id=str(i),
            request_id="request",
            role="assistant",
            model="claude-opus-5",
            usage=usage,
            blocks=[TextBlock(text="part")],
        )
        for i in range(2)
    ]
    session = SessionDetail(id="c", source="claude", messages=messages)
    result = estimate(transcript_requests(session))
    assert result.priced_requests == 1
    assert result.estimated_usd == pytest.approx(0.002038, abs=0.000001)


def test_codex_native_ledger_supersedes_legacy_events_and_preserves_model_switches():
    raw = {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 20}
    records = [
        {"type": "turn_context", "payload": {"turn_id": "a", "model": "gpt-6.1-sol"}},
        {
            "type": "event_msg",
            "payload": {"type": "token_count", "info": {"total_token_usage": raw}},
        },
        {"type": "token_usage_record", "payload": {"response_id": "r", "usage": raw}},
        {"type": "token_usage_record", "payload": {"response_id": "r", "usage": raw}},
        {"type": "turn_context", "payload": {"turn_id": "b", "model": "gpt-6-luna"}},
        {"type": "token_usage_record", "payload": {"response_id": "s", "usage": raw}},
    ]
    requests = list(codex_record_requests(records))
    assert [m for m, _, _ in requests] == ["gpt-6.1-sol", "gpt-6-luna"]
    assert requests[0][2].input_tokens == 50
    assert estimate(requests).priced_requests == 2


def test_cost_service_preserves_recorded_zero_and_invalidates_changed_files(tmp_path):
    path = tmp_path / "chat.jsonl"
    path.write_text(
        '{"type":"session_meta","payload":{"model":"gpt-6.1-sol"}}\n'
        '{"type":"token_usage_record","payload":{"usage":{"input_tokens":100}}}\n'
    )
    summary = SessionSummary(id="codex:c", source="codex", source_path=str(path))
    recorded = SessionSummary(id="opencode:r", source="opencode", usage=Usage(cost_usd=0))

    class RegistryStub:
        def list_sessions(self, **kwargs):
            return [summary, recorded]

        def get_session(self, id):
            raise AssertionError("Recorded cost must not trigger transcript loading")

    service = CostService(RegistryStub())
    service._calculate()
    assert service._stats["recorded_usd"] == 0
    assert service._stats["estimated_sessions"] == 1
    assert service._stats["unpriced_sessions"] == 0
    assert service.session(summary).estimated_usd == 0.0002
    # A detail may have fuller model/count information than its fast summary.
    assert service.session(summary.model_copy(update={"models": ["extra"]})) is not None
    path.write_text(path.read_text() + "\n")
    assert service.session(summary) is None
