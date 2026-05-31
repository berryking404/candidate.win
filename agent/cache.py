"""LLM 응답 캐시 (sha256 키 + prompt VERSION 무효화).

저장 위치: agent/.cache/llm/{tool_name}/{key_prefix}/{key}.json
키 구성:   sha256(tool_name + model_id + prompt_version + input_text + extra_args)

Batch 결과도 동일 키 스킴으로 적재해 Pass D 에서 투명하게 hit.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_ROOT = Path(__file__).parent / ".cache" / "llm"
LOGS_DIR = Path(__file__).parent / ".logs"


def make_key(
    tool_name: str,
    model_id: str,
    prompt_version: str,
    input_text: str,
    **extra: Any,
) -> str:
    """캐시 키 생성."""
    raw = json.dumps(
        {
            "tool": tool_name,
            "model": model_id,
            "version": prompt_version,
            "input": input_text,
            **extra,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def get(tool_name: str, key: str) -> dict | None:
    """캐시 히트 시 결과 dict 반환, 미스 시 None."""
    path = _cache_path(tool_name, key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _record_hit(tool_name)
        logger.debug("캐시 hit [tool=%s key=%s]", tool_name, key[:12])
        return data
    except Exception:
        return None


def put(tool_name: str, key: str, result: dict) -> None:
    """결과를 캐시에 저장."""
    path = _cache_path(tool_name, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {**result, "_cached_at": time.time(), "_key": key}
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug("캐시 저장 [tool=%s key=%s]", tool_name, key[:12])


def invalidate(tool_name: str | None = None) -> int:
    """캐시 삭제. tool_name=None 이면 전체 삭제."""
    target = CACHE_ROOT / tool_name if tool_name else CACHE_ROOT
    if not target.exists():
        return 0
    files = list(target.rglob("*.json"))
    for f in files:
        f.unlink(missing_ok=True)
    logger.info("캐시 삭제: %d 파일 [tool=%s]", len(files), tool_name or "ALL")
    return len(files)


# ---------------------------------------------------------------------------

def _cache_path(tool_name: str, key: str) -> Path:
    return CACHE_ROOT / tool_name / key[:2] / f"{key}.json"


def _record_hit(tool_name: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "cache_hit_rate.json"
    try:
        data = json.loads(log_path.read_text()) if log_path.exists() else {}
    except Exception:
        data = {}
    data[tool_name] = data.get(tool_name, 0) + 1
    log_path.write_text(json.dumps(data, indent=2))
