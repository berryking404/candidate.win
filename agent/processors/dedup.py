"""URL + 내용 해시 기반 중복 제거 및 원문 저장.

수집 결과를 캐시에 저장해 재크롤링을 방지한다.
캐시 파일: agent/.cache/dedup/{source}/{url_hash}.json
seen 목록: agent/.cache/dedup/seen_{source}.json
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / ".cache" / "dedup"


class DedupResult(TypedDict):
    new: list[dict]       # 신규 항목
    duplicate: int        # 중복 건수
    total: int            # 입력 총 건수


def dedup(items: list[dict], source: str = "default") -> DedupResult:
    """입력 항목에서 중복을 제거하고 신규 항목만 반환·저장.

    항목은 반드시 `url` 키를 포함해야 한다.
    `text` 키가 있으면 내용 해시도 추가로 검사한다.

    Args:
        items: Article 또는 VideoTranscript 딕셔너리 목록.
        source: 캐시 네임스페이스 (예: "naver", "youtube").

    Returns:
        DedupResult: 신규 항목 목록과 통계.
    """
    cache_dir = CACHE_DIR / source
    cache_dir.mkdir(parents=True, exist_ok=True)

    seen = _load_seen(source)
    new_items: list[dict] = []
    dup_count = 0

    for item in items:
        url = item.get("url", item.get("video_id", ""))
        url_key = _hash(url)
        text = item.get("text", item.get("transcript", ""))
        text_key = _hash(text) if text else None

        if url_key in seen or (text_key and text_key in seen):
            dup_count += 1
            continue

        seen.add(url_key)
        if text_key:
            seen.add(text_key)

        # 원문 저장
        (cache_dir / f"{url_key}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        new_items.append(item)

    _save_seen(source, seen)

    logger.info(
        "dedup [source=%s]: 입력=%d, 신규=%d, 중복=%d",
        source, len(items), len(new_items), dup_count,
    )
    return DedupResult(new=new_items, duplicate=dup_count, total=len(items))


def load_cached(source: str, limit: int | None = None) -> list[dict]:
    """저장된 원문 캐시를 전부 로드."""
    cache_dir = CACHE_DIR / source
    if not cache_dir.exists():
        return []
    files = sorted(cache_dir.glob("*.json"))
    if limit:
        files = files[:limit]
    results = []
    for f in files:
        try:
            results.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results


# ---------------------------------------------------------------------------

def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:24]


def _seen_path(source: str) -> Path:
    return CACHE_DIR / f"seen_{source}.json"


def _load_seen(source: str) -> set[str]:
    p = _seen_path(source)
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def _save_seen(source: str, seen: set[str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _seen_path(source).write_text(
        json.dumps(list(seen), ensure_ascii=False), encoding="utf-8"
    )
