"""Tier 1 (Ollama/SGLang) 모델 핸들.

싱글톤 패턴으로 모듈 임포트 시 한 번만 초기화된다.
기본은 Ollama `gemma4:e2b-mlx`. 레거시로 TIER1_BACKEND=sglang 지원.
오케스트레이터·OpenAI Tier 2 는 제거됨 — 저신뢰 재분석은 escalation 큐 + sw-factory IC.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 모델 설정 상수
# ---------------------------------------------------------------------------

TIER1_BACKEND = os.getenv("TIER1_BACKEND", "ollama").strip().lower()
if TIER1_BACKEND == "sglang":
    TIER1_MODEL = os.getenv("TIER1_MODEL") or os.getenv(
        "SGLANG_MODEL", "QuantTrio/gemma-4-31B-it-AWQ"
    )
else:
    TIER1_MODEL = os.getenv("TIER1_MODEL") or os.getenv("OLLAMA_MODEL", "gemma4:e2b-mlx")

# ---------------------------------------------------------------------------
# Tier 1 — Ollama / SGLang
# ---------------------------------------------------------------------------

_tier1_model = None


def _build_tier1_ollama():
    """Ollama ChatModel 생성. langchain-ollama 미설치 시 None."""
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        logger.warning("langchain-ollama 미설치 — Tier 1 Ollama 비활성화")
        return None

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    kwargs = {
        "model": TIER1_MODEL,
        "base_url": host,
        "temperature": 0.0,
        "num_ctx": 8192,
    }
    # Gemma thinking 비활성 — JSON 추출 안정화 (미지원 버전이면 무시)
    try:
        model = ChatOllama(**kwargs, think=False)
    except TypeError:
        model = ChatOllama(**kwargs)
    logger.info("Tier 1 Ollama 모델 초기화: model=%s host=%s", TIER1_MODEL, host)
    return model


def _build_tier1_sglang():
    """SGLang OpenAI-compatible ChatModel 생성. langchain-openai 미설치 시 None."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning("langchain-openai 미설치 — Tier 1 SGLang 비활성화")
        return None

    base_url = os.getenv(
        "SGLANG_BASE_URL",
        "http://sglang-gemma4-31b.llm-serving.svc.cluster.local:30000/v1",
    )
    api_key = os.getenv("SGLANG_API_KEY", "EMPTY")
    model = ChatOpenAI(
        model=TIER1_MODEL,
        base_url=base_url,
        api_key=api_key,
        temperature=0.0,
    )
    logger.info("Tier 1 SGLang 모델 초기화: model=%s base_url=%s", TIER1_MODEL, base_url)
    return model


def get_tier1_model():
    """Tier 1 ChatModel 싱글톤 반환. 백엔드는 TIER1_BACKEND로 선택한다."""
    global _tier1_model
    if _tier1_model is not None:
        return _tier1_model

    if TIER1_BACKEND == "ollama":
        _tier1_model = _build_tier1_ollama()
    elif TIER1_BACKEND == "sglang":
        _tier1_model = _build_tier1_sglang()
    else:
        logger.warning("지원하지 않는 TIER1_BACKEND=%s — Tier 1 비활성화", TIER1_BACKEND)
        _tier1_model = None
    return _tier1_model
