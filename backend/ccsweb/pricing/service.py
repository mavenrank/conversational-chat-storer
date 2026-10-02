"""Background, file-signature cached pricing so opening history stays fast."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock, Thread
from time import monotonic

from ccsweb.models import SessionSummary
from ccsweb.models.session import CostEstimate
from ccsweb.pricing.estimates import codex_requests, estimate, rates, transcript_requests
from ccsweb.registry import Registry

logger = logging.getLogger(__name__)


class CostService:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self._lock = RLock()
        self._running = False
        self._last_refresh = -30.0
        self._cache: dict[str, tuple[tuple, CostEstimate]] = {}
        self._stats: dict = {}
        self._error: str | None = None

    def snapshot(self, force: bool = False) -> dict:
        with self._lock:
            if not self._running and (force or monotonic() - self._last_refresh >= 30):
                self._running = True
                self._last_refresh = monotonic()
                self._error = None
                self._stats = {**self._stats, "processed_sessions": 0}
                Thread(target=self._refresh, name="ccs-costs", daemon=True).start()
            return {
                "recorded_usd": 0.0,
                "estimated_usd": None,
                "session_count": 0,
                "processed_sessions": 0,
                "estimated_sessions": 0,
                "unpriced_sessions": 0,
                "failed_sessions": 0,
                "unpriced_models": [],
                "updated_at": None,
                **self._stats,
                "running": self._running,
                "error": self._error,
                "rates_verified_at": rates()["verified_at"],
                "sources": rates()["sources"],
            }

    def session(self, summary: SessionSummary) -> CostEstimate | None:
        with self._lock:
            cached = self._cache.get(summary.id)
            if cached and cached[0] == self._signature(summary):
                return cached[1].model_copy(deep=True)
            if cached and cached[0][0] == summary.source_path:
                # A live chat keeps growing. Show its last priced snapshot explicitly as partial.
                return cached[1].model_copy(deep=True, update={"is_stale": True, "complete": False})
        return None

    @staticmethod
    def _signature(session: SessionSummary) -> tuple:
        try:
            stat = Path(session.source_path).stat()
            file = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            file = ()
        if session.source in {"codex", "claude", "gemini"}:
            return session.source_path, file
        return (session.source_path, file, tuple(session.models), session.usage.model_dump_json())

    def _refresh(self) -> None:
        try:
            self._calculate()
        except Exception:  # noqa: BLE001 - surface background failure without breaking history
            logger.exception("Cost calculation failed")
            with self._lock:
                self._error = "Cost calculation failed. Use Recheck to retry."
        finally:
            with self._lock:
                self._running = False

    def _calculate(self) -> None:
        sessions = self.registry.list_sessions(include_subagents=True)
        stats = {
            "recorded_usd": 0.0,
            "estimated_usd": None,
            "session_count": len(sessions),
            "processed_sessions": 0,
            "estimated_sessions": 0,
            "unpriced_sessions": 0,
            "failed_sessions": 0,
            "unpriced_models": [],
            "updated_at": None,
        }
        estimated = 0.0
        unknown = set()
        live_ids = set()
        for summary in sessions:
            if summary.usage.cost_usd is not None:
                stats["recorded_usd"] += summary.usage.cost_usd
            else:
                live_ids.add(summary.id)
                signature = self._signature(summary)
                with self._lock:
                    cached = self._cache.get(summary.id)
                if cached and cached[0] == signature:
                    priced = cached[1]
                else:
                    failed = False
                    try:
                        if summary.source == "codex":
                            requests = codex_requests(Path(summary.source_path))
                        else:
                            detail = self.registry.get_session(summary.id)
                            requests = transcript_requests(detail) if detail else []
                        priced = estimate(requests, expected_usage=summary.usage)
                    except Exception:  # noqa: BLE001 - isolate and retry unreadable sources
                        logger.exception("Could not calculate a session cost")
                        failed = True
                        stats["failed_sessions"] += 1
                        priced = CostEstimate(rates_verified_at=rates()["verified_at"])
                    # A changing file keeps a marked snapshot and is recalculated next time.
                    if not failed:
                        if self._signature(summary) != signature:
                            priced.is_stale = True
                            priced.complete = False
                        with self._lock:
                            self._cache[summary.id] = signature, priced
                if priced.estimated_usd is not None:
                    estimated += priced.estimated_usd
                    stats["estimated_sessions"] += 1
                if not priced.complete:
                    stats["unpriced_sessions"] += 1
                unknown.update(priced.unpriced_models)
            stats["processed_sessions"] += 1
            stats["estimated_usd"] = round(estimated, 4) if stats["estimated_sessions"] else None
            stats["unpriced_models"] = sorted(unknown)
            with self._lock:
                # Keep the previous completed totals visible while updating progress.
                self._stats = {
                    **self._stats,
                    "session_count": stats["session_count"],
                    "processed_sessions": stats["processed_sessions"],
                }
        stats["recorded_usd"] = round(stats["recorded_usd"], 4)
        stats["updated_at"] = datetime.now(UTC).isoformat()
        with self._lock:
            self._stats = stats
            self._cache = {key: value for key, value in self._cache.items() if key in live_ids}
