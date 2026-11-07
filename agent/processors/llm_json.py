"""LLM 출력에서 JSON 객체/배열을 안전하게 추출한다.

Gemma thinking 채널·코드펜스·다중 블록이 섞여도 마지막 유효 JSON을 우선한다.
"""

from __future__ import annotations

import json
import re

_THINK_RE = re.compile(
    r"<\|?channel\|?>thought.*?<channel\|>|"
    r"<\|think\|>.*?(?:</\|think\|>|<channel\|>)|"
    r"<think>.*?</think>",
    re.DOTALL | re.IGNORECASE,
)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """thinking / channel 블록을 제거한다."""
    cleaned = _THINK_RE.sub("", text or "")
    return cleaned.strip()


def _candidate_blobs(text: str) -> list[str]:
    cleaned = strip_thinking(text)
    blobs: list[str] = []
    for m in _FENCE_RE.finditer(cleaned):
        blobs.append(m.group(1).strip())
    blobs.append(cleaned)
    return blobs


def extract_json_object(text: str) -> dict | None:
    """텍스트에서 JSON object 하나를 파싱한다. 실패 시 None."""
    for blob in _candidate_blobs(text):
        for match in reversed(list(re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", blob, re.DOTALL))):
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
        # greedy fallback for nested objects
        match = re.search(r"\{.*\}", blob, re.DOTALL)
        if not match:
            continue
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def extract_json_array(text: str) -> list | None:
    """텍스트에서 JSON array 하나를 파싱한다. 실패 시 None."""
    for blob in _candidate_blobs(text):
        match = re.search(r"\[.*\]", blob, re.DOTALL)
        if not match:
            continue
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return data
    return None
