"""[Tier 1] 입장 추출 + escalation 큐 enqueue.

Tier 1 confidence < 0.7 또는 position=mixed / quotes 없음 이면
`.cache/escalation/pending.jsonl` 에 적재한다 (sw-factory candidate IC 가 처리).
OpenAI Batch / sync Tier 2 경로는 제거됨.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ESCALATION_DIR = Path(__file__).parent.parent / ".cache" / "escalation"
# 하위 호환: 예전 Batch 경로를 가리키던 이름
BATCH_DIR = ESCALATION_DIR
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
    no_batch: bool = False,  # deprecated, ignored
    no_escalate: bool = False,
) -> dict:
    """입장 추출. Tier 1 confidence 미달 시 escalation 큐에 enqueue.

    Returns:
        {position, summary, quotes, confidence, escalated: bool}
    """
    del no_batch  # OpenAI sync fallback 제거
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

    cached = cache.get("extract_stance", cache_key)
    if cached:
        return cached.get("result", _unknown_stance())

    if model is None:
        logger.warning("Tier 1 없음 — stance unknown")
        return _unknown_stance()

    prompt = STANCE_PROMPT.format(
        person=person_name, issue=issue_slug, text=combined[:6000], criteria=criteria
    )
    try:
        response = model.invoke(prompt)
        result = _parse_stance_json(response.content)
    except Exception as exc:
        logger.warning("Tier 1 stance 추출 실패: %s", exc)
        result = _unknown_stance()

    result["escalated"] = False

    needs_escalation = (
        not no_escalate
        and (
            result.get("confidence", 0) < ESCALATION_THRESHOLD
            or result.get("position") == "mixed"
            or not result.get("quotes")
        )
    )

    if needs_escalation:
        _enqueue_escalation(
            combined, person_slug, person_name, issue_slug, criteria, cache_key, result
        )
        result["escalated"] = True

    cache.put("extract_stance", cache_key, {"result": result})
    return result


def _enqueue_batch(
    text: str,
    person_slug: str,
    person_name: str,
    issue_slug: str,
    criteria: str = DEFAULT_STANCE_CRITERIA,
    cache_key: str = "",
) -> None:
    """하위 호환 별칭 — escalation 큐에 적재."""
    _enqueue_escalation(
        text, person_slug, person_name, issue_slug, criteria, cache_key, None
    )


def _enqueue_escalation(
    text: str,
    person_slug: str,
    person_name: str,
    issue_slug: str,
    criteria: str = DEFAULT_STANCE_CRITERIA,
    cache_key: str = "",
    tier1_result: dict | None = None,
) -> None:
    """candidate IC 용 escalation 항목을 pending.jsonl 에 추가."""
    ESCALATION_DIR.mkdir(parents=True, exist_ok=True)
    pending = ESCALATION_DIR / "pending.jsonl"

    entry = {
        "cache_key": cache_key,
        "person_slug": person_slug,
        "person_name": person_name,
        "issue_slug": issue_slug,
        "criteria": criteria,
        "text": text[:12000],
        "tier1_result": tier1_result,
    }
    with open(pending, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _record_pending_issue(issue_slug)
    logger.info("Escalation enqueue: person=%s issue=%s", person_slug, issue_slug)


def _record_pending_issue(issue_slug: str) -> None:
    path = ESCALATION_DIR / PENDING_ISSUES_FILE
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception:
        existing = []
    issues = sorted({*(s for s in existing if isinstance(s, str)), issue_slug})
    path.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_stance_json(text: str) -> dict:
    from processors.llm_json import extract_json_object

    data = extract_json_object(text)
    if not data:
        return _unknown_stance()
    try:
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
    return {
        "position": "unknown",
        "summary": "",
        "quotes": [],
        "confidence": 0.0,
        "escalated": False,
    }
