from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from time import sleep

from ccsweb.models import Message, SessionSummary
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
