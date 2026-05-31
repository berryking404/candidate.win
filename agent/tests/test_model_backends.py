"""Tier 1 모델 백엔드 선택 테스트.

Kubernetes 운영 환경에서는 Ollama 대신 SGLang OpenAI-compatible endpoint를
사용하므로, models.get_tier1_model()이 env 설정에 따라 올바른 LangChain
어댑터를 생성하는지 검증한다.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))


class FakeChatOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeChatOllama:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _reload_models(monkeypatch):
    sys.modules.pop("models", None)
    import models

    return importlib.reload(models)


def test_tier1_sglang_backend_uses_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setenv("TIER1_BACKEND", "sglang")
    monkeypatch.setenv("SGLANG_BASE_URL", "http://sglang-gemma4-31b.llm-serving.svc.cluster.local:30000/v1")
    monkeypatch.setenv("SGLANG_MODEL", "QuantTrio/gemma-4-31B-it-AWQ")
    monkeypatch.setenv("SGLANG_API_KEY", "EMPTY")
    monkeypatch.setitem(sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI))

    models = _reload_models(monkeypatch)
    model = models.get_tier1_model()

    assert isinstance(model, FakeChatOpenAI)
    assert models.TIER1_BACKEND == "sglang"
    assert models.TIER1_MODEL == "QuantTrio/gemma-4-31B-it-AWQ"
    assert model.kwargs["model"] == "QuantTrio/gemma-4-31B-it-AWQ"
    assert model.kwargs["base_url"] == "http://sglang-gemma4-31b.llm-serving.svc.cluster.local:30000/v1"
    assert model.kwargs["api_key"] == "EMPTY"
    assert model.kwargs["temperature"] == 0.0


def test_tier1_ollama_backend_keeps_legacy_ollama_env(monkeypatch):
    monkeypatch.setenv("TIER1_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "exaone3.5:7.8b")
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama.local:11434")
    monkeypatch.setitem(sys.modules, "langchain_ollama", types.SimpleNamespace(ChatOllama=FakeChatOllama))

    models = _reload_models(monkeypatch)
    model = models.get_tier1_model()

    assert isinstance(model, FakeChatOllama)
    assert models.TIER1_BACKEND == "ollama"
    assert models.TIER1_MODEL == "exaone3.5:7.8b"
    assert model.kwargs["model"] == "exaone3.5:7.8b"
    assert model.kwargs["base_url"] == "http://ollama.local:11434"
    assert model.kwargs["temperature"] == 0.0
    assert model.kwargs["num_ctx"] == 8192
