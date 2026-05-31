"""[Tier 1→2] 입장 추출 + Tier 2 에스컬레이션.

Tier 1 confidence < 0.7 또는 position=mixed 이면 Batch buffer 에 enqueue.
--no-batch 플래그 시 동기 Tier 2 fallback.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

BATCH_DIR = Path(__file__).parent.parent / ".cache" / "batch"
ESCALATION_THRESHOLD = 0.7
DEFAULT_STANCE_CRITERIA = "지지/반대 판정 기준이 명시되지 않았습니다. 일반적인 맥락에서 판단하십시오."
PENDING_ISSUES_FILE = "pending_issues.json"

VALID_POSITIONS = {"support", "oppose", "neutral", "mixed", "unknown"}


def extract_stance(
    chunks: list[str],
    person_slug: str,
    person_name: str,
    issue_slug: str,
    criteria: str = DEFAULT_STANCE_CRITERIA,
    *,
    model=None,
    no_batch: bool = False,
    no_escalate: bool = False,
) -> dict:
    """입장 추출. Tier 1 confidence 미달 시 Batch 에 enqueue.

    Returns:
        {position, summary, quotes, confidence, escalated: bool}
    """
    from prompts import STANCE_PROMPT, STANCE_PROMPT_VERSION
    import cache
    from models import get_tier1_model, TIER1_MODEL

    if model is None:
        model = get_tier1_model()

    combined = "\n\n".join(chunks)
    cache_key = cache.make_key(
        "extract_stance", TIER1_MODEL, STANCE_PROMPT_VERSION,
        combined, person=person_slug, issue=issue_slug, criteria=criteria,
    )

    # 캐시 hit (Batch 결과 포함)
    cached = cache.get("extract_stance", cache_key)
    if cached:
        return cached.get("result", _unknown_stance())

    if model is None:
        logger.warning("Tier 1 없음 — stance unknown")
        return _unknown_stance()

    prompt = STANCE_PROMPT.format(person=person_name, issue=issue_slug, text=combined[:6000], criteria=criteria)
    try:
        response = model.invoke(prompt)
        result = _parse_stance_json(response.content)
    except Exception as exc:
        logger.warning("Tier 1 stance 추출 실패: %s", exc)
        result = _unknown_stance()

    result["escalated"] = False

    # 에스컬레이션 판단
    needs_escalation = (
        not no_escalate
        and (
            result.get("confidence", 0) < ESCALATION_THRESHOLD
            or result.get("position") == "mixed"
            or not result.get("quotes")
        )
    )

    if needs_escalation:
        if no_batch:
            # 동기 Tier 2 fallback
            result = _escalate_sync(combined, person_name, issue_slug, criteria, cache_key)
        else:
            _enqueue_batch(combined, person_slug, person_name, issue_slug, criteria, cache_key)
            result["escalated"] = True

    cache.put("extract_stance", cache_key, {"result": result})
    return result


# ---------------------------------------------------------------------------

def _escalate_sync(
    text: str,
    person_name: str,
    issue_slug: str,
    criteria: str,
    cache_key: str,
) -> dict:
    """동기 Tier 2 호출 (--no-batch 모드)."""
    from models import get_tier2_model, get_cost_accumulator, TIER2_SYNC_MODEL
    import cache as cache_mod
    from prompts import STANCE_PROMPT, STANCE_PROMPT_VERSION

    model = get_tier2_model()
    if model is None:
        return _unknown_stance()

    prompt = STANCE_PROMPT.format(person=person_name, issue=issue_slug, text=text[:12000], criteria=criteria)
    try:
        response = model.invoke(prompt)
        result = _parse_stance_json(response.content)
        result["escalated"] = True

        # 비용 기록
        usage = getattr(response, "usage_metadata", {}) or {}
        acc = get_cost_accumulator(batch=False)
        acc.record(
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )
        cache_mod.put("extract_stance", cache_key, {"result": result})
        return result
    except Exception as exc:
        logger.warning("Tier 2 sync 에스컬레이션 실패: %s", exc)
        return _unknown_stance()


def _enqueue_batch(
    text: str,
    person_slug: str,
    person_name: str,
    issue_slug: str,
    criteria: str = DEFAULT_STANCE_CRITERIA,
    cache_key: str = "",
) -> None:
    """Batch 요청을 pending.jsonl 에 추가."""
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    pending = BATCH_DIR / "pending.jsonl"
    from prompts import STANCE_PROMPT, STANCE_PROMPT_VERSION
    from models import TIER2_BATCH_MODEL as model_id

    entry = {
        "custom_id": cache_key,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model_id,
            "messages": [
                {"role": "system", "content": "입장 추출 전문가."},
                {"role": "user", "content": STANCE_PROMPT.format(
                    person=person_name, issue=issue_slug, text=text[:12000], criteria=criteria
                )},
            ],
            "temperature": 0,
        },
    }
    with open(pending, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _record_pending_issue(issue_slug)
    logger.info("Batch enqueue: person=%s issue=%s", person_slug, issue_slug)


def _record_pending_issue(issue_slug: str) -> None:
    """Batch request top-level schema를 건드리지 않고 issue slug sidecar를 기록한다."""
    path = BATCH_DIR / PENDING_ISSUES_FILE
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception:
        existing = []
    issues = sorted({*(s for s in existing if isinstance(s, str)), issue_slug})
    path.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_stance_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return _unknown_stance()
    try:
        data = json.loads(match.group())
        position = data.get("position", "unknown")
        if position not in VALID_POSITIONS:
            position = "unknown"
        return {
            "position": position,
            "summary": data.get("summary", ""),
            "quotes": data.get("quotes", []),
            "confidence": float(data.get("confidence", 0.5)),
        }
    except Exception:
        return _unknown_stance()


def _unknown_stance() -> dict:
    return {"position": "unknown", "summary": "", "quotes": [], "confidence": 0.0, "escalated": False}
