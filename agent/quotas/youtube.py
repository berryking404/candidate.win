"""YouTube Data API v3 quota 추적·임계 알람.

무료 한도: 10,000 units/day/project
  search.list  = 100 units
  videos.list  = 1 unit
  channels.list = 1 unit

사용법:
    from quotas.youtube import YouTubeQuota, QuotaExhausted

    quota = YouTubeQuota()
    quota.charge(100)          # search.list 1회
    units = quota.remaining()  # 남은 units
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

DAILY_LIMIT = int(os.getenv("YOUTUBE_QUOTA_LIMIT", "10000"))
WARN_THRESHOLD = float(os.getenv("YOUTUBE_QUOTA_WARN", "0.80"))

CACHE_DIR = Path(__file__).parent.parent / ".cache" / "quota"

# 단위별 비용
UNIT_COSTS = {
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.list": 1,
}


class QuotaExhausted(Exception):
    """YouTube API 일일 quota 소진."""


class YouTubeQuota:
    def __init__(self, limit: int = DAILY_LIMIT) -> None:
        self.limit = limit
        self._cache_path = CACHE_DIR / f"youtube_{date.today():%Y%m%d}.json"
        self._used: int = self._load()

    # ------------------------------------------------------------------
    def charge(self, units: int, operation: str = "") -> None:
        """units 소비 전 quota 점검 후 누적.

        Raises:
            QuotaExhausted: 잔여 quota 가 units 보다 적을 때.
        """
        if self._used + units > self.limit:
            raise QuotaExhausted(
                f"YouTube quota 소진: used={self._used}, requested={units}, limit={self.limit}"
            )
        self._used += units
        self._save()

        ratio = self._used / self.limit
        if ratio >= 1.0:
            logger.error("YouTube quota 100%% 도달 (%d/%d)", self._used, self.limit)
        elif ratio >= WARN_THRESHOLD:
            logger.warning(
                "YouTube quota %.0f%% 사용 (%d/%d) [operation=%s]",
                ratio * 100, self._used, self.limit, operation,
            )

    def charge_op(self, operation: str, count: int = 1) -> None:
        """operation 이름으로 단가를 자동 계산해 charge."""
        cost = UNIT_COSTS.get(operation, 1) * count
        self.charge(cost, operation)

    def remaining(self) -> int:
        return max(0, self.limit - self._used)

    def used(self) -> int:
        return self._used

    def usage_ratio(self) -> float:
        return self._used / self.limit

    # ------------------------------------------------------------------
    def _load(self) -> int:
        try:
            return json.loads(self._cache_path.read_text())["used"]
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            return 0

    def _save(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps({"date": str(date.today()), "used": self._used, "limit": self.limit})
        )
