"""[Tier 1] 모델 기반 행적 이벤트 추출.

입력: 청킹된 텍스트 목록 + 인물 slug
출력: [{date, event, source_url}]
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


def extract_events(
    chunks: list[str],
    person_slug: str,
    person_name: str,
    *,
    model=None,
) -> list[dict]:
    """청크 목록에서 인물 행적을 추출.

    Args:
        chunks: chunker.py 가 만든 텍스트 청크 목록.
        person_slug: 인물 slug (캐시 키용).
        person_name: 실제 이름 (프롬프트 삽입).
        model: Tier 1 ChatModel 인스턴스. None 이면 models.get_tier1_model() 사용.

    Returns:
        [{date, event, source_url}] 목록. 출처 없는 항목은 제외.
    """
    from prompts import EVENTS_PROMPT, EVENTS_PROMPT_VERSION
    import cache
    from models import get_tier1_model, TIER1_MODEL

    if model is None:
        model = get_tier1_model()
    if model is None:
        logger.warning("Tier 1 모델 없음 — extract_events 건너뜀")
        return []

    events: list[dict] = []
    seen_events: set[str] = set()

    for chunk in chunks:
        cache_key = cache.make_key(
            "extract_events", TIER1_MODEL, EVENTS_PROMPT_VERSION,
            chunk, person=person_slug,
        )
        cached = cache.get("extract_events", cache_key)
        if cached:
            _merge_events(events, cached.get("result", []), seen_events)
            continue

        prompt = EVENTS_PROMPT.format(person=person_name, text=chunk)
        try:
            response = model.invoke(prompt)
            parsed = _parse_json_list(response.content)
            cache.put("extract_events", cache_key, {"result": parsed})
            _merge_events(events, parsed, seen_events)
        except Exception as exc:
            logger.warning("extract_events 실패: %s", exc)

    return sorted(events, key=lambda e: e.get("date") or "", reverse=True)


# ---------------------------------------------------------------------------

def _merge_events(
    events: list[dict],
    new: list[dict],
    seen: set[str],
) -> None:
    for item in new:
        if not item.get("source_url"):
            continue
        key = f"{item.get('date', '')}:{item.get('event', '')[:40]}"
        if key not in seen:
            seen.add(key)
            events.append(item)


def _parse_json_list(text: str) -> list[dict]:
    """LLM 출력에서 JSON 배열 추출."""
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if not match:
        return []
    try:
        result = json.loads(match.group())
        return [r for r in result if isinstance(r, dict)]
    except json.JSONDecodeError:
        return []
