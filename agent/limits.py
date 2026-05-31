"""Circuit Breaker — 무한 루프 / 무한 과금 방지.

RunLimits 에 정의된 상한을 초과하면 LimitExceeded 를 발생시키고
종료 코드 42 로 프로세스를 종료한다.

CLI 플래그나 환경변수로 기본값 재정의 가능:
    CANDYDATE_MAX_STUBS, CANDYDATE_COST_CAP, CANDYDATE_MAX_CALLS,
    CANDYDATE_TIME_CAP, CANDYDATE_MAX_PAGES
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).parent / ".logs"


class LimitExceeded(Exception):
    """Circuit breaker 트리핑 — 상한 초과."""
    def __init__(self, limit_name: str, current: float, cap: float) -> None:
        self.limit_name = limit_name
        self.current = current
        self.cap = cap
        super().__init__(f"한도 초과 [{limit_name}]: {current} / {cap}")


@dataclass(frozen=True)
class RunLimits:
    max_new_stubs: int = int(os.getenv("CANDYDATE_MAX_STUBS", "20"))
    max_tier2_usd: float = float(os.getenv("CANDYDATE_COST_CAP", "1.0"))
    max_tier2_calls: int = int(os.getenv("CANDYDATE_MAX_CALLS", "50"))
    max_wallclock_minutes: int = int(os.getenv("CANDYDATE_TIME_CAP", "30"))
    max_pages_modified: int = int(os.getenv("CANDYDATE_MAX_PAGES", "200"))


@dataclass
class RunCounter:
    """실행 중 누적 카운터. 각 도구 호출 직전에 check() 를 호출한다."""
    limits: RunLimits = field(default_factory=RunLimits)
    new_stubs: int = 0
    tier2_calls: int = 0
    pages_modified: int = 0
    _start_time: float = field(default_factory=time.monotonic, repr=False)

    # ------------------------------------------------------------------
    def check_stubs(self, adding: int = 1) -> None:
        if self.new_stubs + adding > self.limits.max_new_stubs:
            self._trip("max_new_stubs", self.new_stubs + adding, self.limits.max_new_stubs)

    def check_tier2_call(self) -> None:
        if self.tier2_calls + 1 > self.limits.max_tier2_calls:
            self._trip("max_tier2_calls", self.tier2_calls + 1, self.limits.max_tier2_calls)

    def check_cost(self, current_usd: float) -> None:
        if current_usd > self.limits.max_tier2_usd:
            self._trip("max_tier2_usd", current_usd, self.limits.max_tier2_usd)

    def check_time(self) -> None:
        elapsed = (time.monotonic() - self._start_time) / 60
        if elapsed > self.limits.max_wallclock_minutes:
            self._trip("max_wallclock_minutes", elapsed, self.limits.max_wallclock_minutes)

    def check_pages(self, adding: int = 1) -> None:
        if self.pages_modified + adding > self.limits.max_pages_modified:
            self._trip("max_pages_modified", self.pages_modified + adding, self.limits.max_pages_modified)

    # ------------------------------------------------------------------
    def record_stub(self) -> None:
        self.new_stubs += 1

    def record_tier2_call(self) -> None:
        self.tier2_calls += 1

    def record_page_modified(self) -> None:
        self.pages_modified += 1

    # ------------------------------------------------------------------
    def elapsed_minutes(self) -> float:
        return (time.monotonic() - self._start_time) / 60

    def summary(self) -> dict:
        return {
            "new_stubs": self.new_stubs,
            "tier2_calls": self.tier2_calls,
            "pages_modified": self.pages_modified,
            "elapsed_minutes": round(self.elapsed_minutes(), 2),
        }

    # ------------------------------------------------------------------
    def _trip(self, limit_name: str, current: float, cap: float) -> None:
        exc = LimitExceeded(limit_name, current, cap)
        self._log_trip(limit_name, current, cap)
        logger.error("Circuit breaker: %s", exc)
        raise exc

    def _log_trip(self, limit_name: str, current: float, cap: float) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOGS_DIR / "limits_tripped.json"
        try:
            data = json.loads(log_path.read_text()) if log_path.exists() else []
        except Exception:
            data = []
        data.append({
            "limit": limit_name,
            "current": current,
            "cap": cap,
            "summary": self.summary(),
        })
        log_path.write_text(json.dumps(data, indent=2))


_global_counter: RunCounter | None = None


def _get_counter() -> RunCounter:
    """실행 중 싱글톤 RunCounter 반환."""
    global _global_counter
    if _global_counter is None:
        _global_counter = RunCounter()
    return _global_counter


def reset_counter(limits: RunLimits | None = None) -> RunCounter:
    """새 RunCounter 로 초기화하고 반환."""
    global _global_counter
    _global_counter = RunCounter(limits=limits or RunLimits())
    return _global_counter


def exit_with_partial(counter: RunCounter, reason: str) -> None:
    """부분 커밋 후 종료 코드 42 로 종료."""
    logger.warning("부분 완료 종료: %s | %s", reason, counter.summary())
    sys.exit(42)
