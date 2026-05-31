"""Tier 1 (Ollama/SGLang) / Tier 2 (OpenAI) 모델 핸들 + Tier 2 비용 누적.

싱글톤 패턴으로 모듈 임포트 시 한 번만 초기화된다.
Tier 1은 기본 Ollama를 유지하되, Kubernetes 운영 환경에서는
TIER1_BACKEND=sglang 으로 SGLang OpenAI-compatible endpoint를 사용할 수 있다.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 모델 설정 상수
# ---------------------------------------------------------------------------

TIER1_BACKEND = os.getenv("TIER1_BACKEND", "ollama").strip().lower()
if TIER1_BACKEND == "sglang":
    TIER1_MODEL = os.getenv("TIER1_MODEL") or os.getenv("SGLANG_MODEL", "QuantTrio/gemma-4-31B-it-AWQ")
else:
    # Backward compatibility: existing Ollama deployments used OLLAMA_MODEL.
    TIER1_MODEL = os.getenv("TIER1_MODEL") or os.getenv("OLLAMA_MODEL", "exaone3.5:7.8b")
TIER2_SYNC_MODEL = os.getenv("OPENAI_SYNC_MODEL", "gpt-5.4-mini")  # 오케스트레이터
TIER2_BATCH_MODEL = os.getenv("OPENAI_BATCH_MODEL", "gpt-5.4")     # batch escalation

# OpenAI 단가 (USD / 1M tokens) — 2026-04 기준
_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini":  {"input": 0.150, "output": 0.600},
    "gpt-4o":       {"input": 2.50,  "output": 10.0},
    "gpt-5.4-nano": {"input": 0.20,  "output": 1.25},
    "gpt-5.4-mini": {"input": 0.75,  "output": 4.50},
    "gpt-5.4":      {"input": 2.50,  "output": 15.0},
}

LOGS_DIR = Path(__file__).parent / ".logs"


# ---------------------------------------------------------------------------
# Tier 2 비용 누적기
# ---------------------------------------------------------------------------

@dataclass
class CostAccumulator:
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    cache_hit_tokens: int = 0   # prompt cache 히트 토큰 수 (입력 -90% 적용)
    batch_tokens: int = 0       # Batch API 경유 출력 토큰 수 (-50% 적용)
    _usd: float = field(default=0.0, repr=False)

    def record(
        self,
        input_tokens: int,
        output_tokens: int,
        *,
        cache_hit: bool = False,
        batch: bool = False,
    ) -> float:
        """토큰 소비를 기록하고 해당 호출 비용(USD)을 반환."""
        pricing = _PRICING.get(self.model_id, {"input": 3.0, "output": 15.0})
        in_rate = pricing["input"] / 1_000_000
        out_rate = pricing["output"] / 1_000_000

        # 캐시 히트: 입력 -90%
        effective_in = input_tokens * (0.10 if cache_hit else 1.0)
        # Batch API: 전체 -50%
        batch_factor = 0.5 if batch else 1.0

        cost = (effective_in * in_rate + output_tokens * out_rate) * batch_factor

        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1
        if cache_hit:
            self.cache_hit_tokens += input_tokens
        if batch:
            self.batch_tokens += output_tokens
        self._usd += cost
        return cost

    def total_usd(self) -> float:
        return self._usd

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_hit_tokens": self.cache_hit_tokens,
            "batch_tokens": self.batch_tokens,
            "total_usd": round(self._usd, 6),
        }


# 싱글톤 누적기
_cost_sync = CostAccumulator(model_id=TIER2_SYNC_MODEL)
_cost_batch = CostAccumulator(model_id=TIER2_BATCH_MODEL)


def get_cost_accumulator(batch: bool = False) -> CostAccumulator:
    return _cost_batch if batch else _cost_sync


def total_tier2_usd() -> float:
    return _cost_sync.total_usd() + _cost_batch.total_usd()


def dump_cost_log() -> None:
    """비용 로그를 .logs/cost.json 에 저장."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "sync": _cost_sync.to_dict(),
        "batch": _cost_batch.to_dict(),
        "total_usd": round(total_tier2_usd(), 6),
    }
    (LOGS_DIR / "cost.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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
    model = ChatOllama(
        model=TIER1_MODEL,
        base_url=host,
        temperature=0.0,
        num_ctx=8192,
    )
    logger.info("Tier 1 Ollama 모델 초기화: model=%s host=%s", TIER1_MODEL, host)
    return model


def _build_tier1_sglang():
    """SGLang OpenAI-compatible ChatModel 생성. langchain-openai 미설치 시 None."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning("langchain-openai 미설치 — Tier 1 SGLang 비활성화")
        return None

    base_url = os.getenv("SGLANG_BASE_URL", "http://sglang-gemma4-31b.llm-serving.svc.cluster.local:30000/v1")
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


# ---------------------------------------------------------------------------
# Tier 2 — OpenAI (sync)
# ---------------------------------------------------------------------------

_openai_model = None


def get_tier2_model():
    """ChatOpenAI 싱글톤 반환. API 키 미설정 시 None."""
    global _openai_model
    if _openai_model is not None:
        return _openai_model
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY 미설정 — Tier 2 sync 비활성화")
        return None
    try:
        from langchain_openai import ChatOpenAI
        _openai_model = ChatOpenAI(
            model=TIER2_SYNC_MODEL,
            api_key=api_key,
            temperature=0.0,
        )
        logger.info("Tier 2 OpenAI 모델 초기화: model=%s", TIER2_SYNC_MODEL)
    except ImportError:
        logger.warning("langchain-openai 미설치 — Tier 2 비활성화")
        _openai_model = None
    return _openai_model
