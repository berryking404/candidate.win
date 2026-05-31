"""OpenAI Batch API 제출·polling·결과 적재.

Phase B: pending.jsonl → POST /v1/batches → active.json 에 batch_id 저장
Phase C: batch 완료 확인 → 결과를 LLM 캐시에 적재
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

BATCH_DIR = Path(__file__).parent.parent / ".cache" / "batch"
ACTIVE_FILE = BATCH_DIR / "active.json"
PENDING_FILE = BATCH_DIR / "pending.jsonl"
PENDING_ISSUES_FILE = BATCH_DIR / "pending_issues.json"


# ---------------------------------------------------------------------------
# Phase B — 제출
# ---------------------------------------------------------------------------

def submit() -> str | None:
    """pending.jsonl 을 OpenAI Batch API 로 제출.

    Returns:
        batch_id (str) 또는 None (제출 항목 없음).
    """
    if not PENDING_FILE.exists() or PENDING_FILE.stat().st_size == 0:
        logger.info("Batch: pending 항목 없음")
        return None

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.error("OPENAI_API_KEY 미설정 — Batch 제출 불가")
        return None

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    # 입력 파일 업로드
    with open(PENDING_FILE, "rb") as f:
        file_obj = client.files.create(file=f, purpose="batch")

    batch = client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    batch_id = batch.id

    issue_slugs = _read_pending_issue_slugs()

    # active.json 저장
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(
        json.dumps({
            "batch_id": batch_id,
            "submitted_at": time.time(),
            "file_id": file_obj.id,
            "issue_slugs": issue_slugs,
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    # pending 초기화
    PENDING_FILE.write_text("", encoding="utf-8")
    PENDING_ISSUES_FILE.unlink(missing_ok=True)

    logger.info("Batch 제출 완료: batch_id=%s", batch_id)
    return batch_id


def _read_pending_issue_slugs() -> list[str]:
    """pending.jsonl sidecar에서 batch 완료 후 재적용할 issue slug 목록을 읽는다."""
    try:
        data = json.loads(PENDING_ISSUES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return sorted({item for item in data if isinstance(item, str) and item})


# ---------------------------------------------------------------------------
# Phase C — polling + 결과 적재
# ---------------------------------------------------------------------------

def poll_and_ingest(*, timeout_minutes: int = 60) -> bool:
    """Batch 완료 여부 확인 후 결과를 LLM 캐시에 적재.

    Returns:
        True: 완료 + 적재 성공 / False: 아직 진행 중 또는 실패.
    """
    if not ACTIVE_FILE.exists():
        logger.info("Batch: active 파일 없음")
        return False

    state = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
    batch_id = state["batch_id"]

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return False

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    batch = client.batches.retrieve(batch_id)
    status = batch.status

    logger.info("Batch 상태: %s (id=%s)", status, batch_id)

    if status not in ("completed", "failed", "expired", "cancelled"):
        return False  # 아직 진행 중

    if status != "completed":
        logger.error("Batch 실패: status=%s", status)
        ACTIVE_FILE.unlink(missing_ok=True)
        return False

    # 결과 다운로드 + 캐시 적재
    output_file_id = batch.output_file_id
    if not output_file_id:
        logger.error("Batch: output_file_id 없음")
        return False

    content = client.files.content(output_file_id).text
    ingested = 0
    import cache

    for line in content.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            custom_id = item.get("custom_id", "")
            response_body = item.get("response", {}).get("body", {})
            choices = response_body.get("choices", [])
            if not choices:
                continue
            text = choices[0].get("message", {}).get("content", "")
            from processors.stance_extractor import _parse_stance_json
            stance = _parse_stance_json(text)
            stance["escalated"] = True
            cache.put("extract_stance", custom_id, {"result": stance})
            ingested += 1
        except Exception as exc:
            logger.warning("Batch 결과 파싱 실패: %s", exc)

    ACTIVE_FILE.unlink(missing_ok=True)
    logger.info("Batch 결과 적재: %d 항목", ingested)
    return True
