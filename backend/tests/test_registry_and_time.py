from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from time import sleep

from ccsweb.models import Message, SessionDetail, SessionSummary
from ccsweb.registry import Registry
from ccsweb.sources.base import SourceAdapter


class CountingAdapter(SourceAdapter):
    source_id = "codex"
    display_name = "Codex"
    calls = 0

    @staticmethod
    def default_root():
        from pathlib import Path

        return Path(__file__).parent

    def list_sessions(self):
        self.calls += 1
        sleep(0.02)  # overlapping initial HTTP requests
        return [SessionSummary(id="native", source="codex", fork_of="parent")]

    def get_session(self, session_id):
        return None


def test_concurrent_initial_requests_share_one_scan_and_keep_native_ids():
    adapter = CountingAdapter()
    registry = Registry(adapters={"codex": adapter})
    barrier = Barrier(3)

    def request(i):
        barrier.wait()
        return (
            registry.statuses() if i == 0 else registry.list_sessions(include_subagents=bool(i - 1))
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(request, range(3)))
    assert adapter.calls == 1
    assert registry._index["codex"][1][0].id == "native"
    assert registry.list_sessions()[0].fork_of == "codex:parent"
    registry.index_ttl_seconds = 0
    registry.list_sessions()
    assert adapter.calls == 2


def test_timestamp_serialization_is_utc_and_backups_round_trip_without_mixed_zones():
    local = datetime(2026, 10, 1, 17, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    summary = SessionSummary(id="chat", source="codex", created_at=local)
    message = Message(id="m", role="user", started_at=local, completed_at=local)
    assert summary.model_dump(mode="json")["created_at"] == "2026-10-01T11:30:00Z"
    assert message.model_dump(mode="json")["started_at"] == "2026-10-01T11:30:00Z"
    restored = SessionSummary.model_validate_json(summary.model_dump_json())
    assert restored.created_at == datetime(2026, 10, 1, 11, 30)
    assert restored.created_at.tzinfo is None


def test_approval_reviews_and_agents_have_independent_visibility_and_global_links():
    parent = SessionSummary(id="parent", source="codex")
    agent = SessionSummary(id="agent", source="codex", is_subagent=True, parent_session_id="parent")
    review = SessionSummary(
        id="review", source="codex", is_approval_review=True, parent_session_id="parent"
    )

    class Adapter(CountingAdapter):
        def list_sessions(self):
            return [parent, agent, review]

        def get_session(self, id):
            return SessionDetail(
                **parent.model_dump(), subagents=[agent], approval_reviews=[review]
            )

    registry = Registry(adapters={"codex": Adapter()})
    assert [s.id for s in registry.list_sessions()] == ["codex:parent"]
    assert {s.id for s in registry.list_sessions(include_subagents=True)} == {
        "codex:parent",
        "codex:agent",
    }
    assert {s.id for s in registry.list_sessions(include_approval_reviews=True)} == {
        "codex:parent",
        "codex:review",
    }
    assert len(registry.list_sessions(include_subagents=True, include_approval_reviews=True)) == 3
    detail = registry.get_session("codex:parent")
    assert detail.approval_reviews[0].id == "codex:review"
    assert detail.approval_reviews[0].parent_session_id == "codex:parent"
    assert registry.statuses()[0].session_count == 1
