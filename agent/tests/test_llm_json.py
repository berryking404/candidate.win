"""LLM JSON 추출 — thinking/코드펜스 내성."""

from __future__ import annotations

import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))

from processors.llm_json import extract_json_array, extract_json_object, strip_thinking


def test_strip_thinking_removes_channel_block():
    raw = "<|channel>thought\nreason\n<channel|>{\"position\": \"support\"}"
    assert "thought" not in strip_thinking(raw)
    assert "support" in strip_thinking(raw)


def test_extract_json_object_from_thinking_wrapped():
    raw = (
        "<|channel>thought\n나는 고민한다\n<channel|>"
        '```json\n{"position": "oppose", "confidence": 0.9}\n```'
    )
    data = extract_json_object(raw)
    assert data == {"position": "oppose", "confidence": 0.9}


def test_extract_json_object_picks_last_valid_when_multiple():
    raw = '{"noise": true}\n최종: {"position": "neutral", "confidence": 0.5}'
    data = extract_json_object(raw)
    assert data is not None
    assert data.get("position") == "neutral"


def test_extract_json_array_basic():
    raw = '앞에 설명\n[{"name_ko": "이재명"}]\n끝'
    data = extract_json_array(raw)
    assert data == [{"name_ko": "이재명"}]
