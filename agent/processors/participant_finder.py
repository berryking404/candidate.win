"""[Tier 1] 이슈 텍스트에서 발언자 후보 정규화·매칭.

Tier 0 NER 결과를 Tier 1 모델로 정규화하고 기존 인물 목록과 매칭.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DATA_PEOPLE_DIR = Path(__file__).parent.parent.parent / "data" / "people"
MIN_MENTIONS = 2


def find_participants(
    chunks: list[str],
    issue_slug: str,
    *,
    model=None,
) -> list[dict]:
    """청크 목록에서 발언자 후보 목록 반환.

    Returns:
        [{name_ko, role_hint, mention_count, sample_quote, matched_slug (or None)}]
    """
    from processors.ner_kr import extract_person_candidates
    from prompts import PARTICIPANTS_PROMPT, PARTICIPANTS_PROMPT_VERSION
    import cache
    from models import get_tier1_model, TIER1_MODEL
    import json, re

    # Tier 0: NER 로 빠른 후보 추출
    ner_candidates = extract_person_candidates(chunks, min_mentions=1)
    if not ner_candidates:
        return []

    combined = "\n\n".join(chunks)
    cache_key = cache.make_key(
        "find_participants", TIER1_MODEL, PARTICIPANTS_PROMPT_VERSION,
        combined, issue=issue_slug,
    )
    cached = cache.get("find_participants", cache_key)
    if cached:
        return _match_existing(cached.get("result", []))

    if model is None:
        model = get_tier1_model()

    if model is None:
        # Tier 1 없으면 Tier 0 결과만 반환
        raw = [{"name_ko": c.name, "role_hint": "", "mention_count": c.mention_count, "sample_quote": ""} for c in ner_candidates]
        return _match_existing(raw)

    prompt = PARTICIPANTS_PROMPT.format(issue=issue_slug, text=combined[:8000])
    try:
        response = model.invoke(prompt)
        match = re.search(r"\[.*?\]", response.content, re.DOTALL)
        result = json.loads(match.group()) if match else []
    except Exception as exc:
        logger.warning("find_participants Tier 1 실패: %s", exc)
        result = [{"name_ko": c.name, "role_hint": "", "mention_count": c.mention_count, "sample_quote": ""} for c in ner_candidates]

    cache.put("find_participants", cache_key, {"result": result})
    return _match_existing(result)


# ---------------------------------------------------------------------------

def _match_existing(candidates: list[dict]) -> list[dict]:
    """기존 data/people/ 의 인물과 이름·aliases 기준 매칭."""
    registry = _load_registry()
    for c in candidates:
        name = c.get("name_ko", "")
        c["matched_slug"] = registry.get(name)
    return [c for c in candidates if c.get("mention_count", 0) >= MIN_MENTIONS]


def _load_registry() -> dict[str, str]:
    """name_ko / aliases → slug 매핑 테이블."""
    mapping: dict[str, str] = {}
    if not DATA_PEOPLE_DIR.exists():
        return mapping
    for f in DATA_PEOPLE_DIR.glob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        slug = data.get("slug", f.stem)
        for key in [data.get("name_ko"), data.get("hangul_name")] + (data.get("aliases") or []):
            if key:
                mapping[key] = slug
    return mapping
