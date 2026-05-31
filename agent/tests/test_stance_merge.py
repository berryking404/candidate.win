"""stance_merge 병합·중복 키 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))

from publishers.stance_merge import merge_stance_sections, parse_stance_merge_key


LINE_A = (
    "- [김봉철](/people/gim-bong-cheol) — **지지**: 부산시의 골목상권. "
    "[출처](https://www.kmib.co.kr/article/view.asp?arcid=0029807934&code=61141111&cp=nv)"
)
LINE_A2 = (
    "- [김봉철](/people/gim-bong-cheol) — **지지**: 다른 언론 동일 보도. "
    "[출처](https://example.com/other)"
)
LINE_B = "- [이영희](/people/i-yeong-hui) — **반대**: 반대 요약. [출처](https://x.com/y)"


def test_parse_key_issue_page():
    assert parse_stance_merge_key(LINE_A) == "p:gim-bong-cheol:지지"
    assert parse_stance_merge_key(LINE_B) == "p:i-yeong-hui:반대"


def test_parse_key_people_page():
    line = "- [상권](/issues/local-commerce-2026) — **지지**: 요약. [출처](https://a)"
    assert parse_stance_merge_key(line) == "i:local-commerce-2026:지지"


def test_parse_key_no_link_returns_none():
    line = "- **이름** — **지지**: 요약. [출처](https://a)"
    assert parse_stance_merge_key(line) is None


def test_merge_skips_duplicate_person_stance():
    existing = LINE_A
    incoming = "\n".join([LINE_A2, LINE_B])
    out = merge_stance_sections(existing, incoming)
    assert LINE_A in out
    assert "i-yeong-hui" in out
    assert "example.com/other" not in out


def test_merge_appends_new_person():
    existing = LINE_A
    incoming = LINE_B
    out = merge_stance_sections(existing, incoming)
    assert out.index("gim-bong-cheol") < out.index("i-yeong-hui")


def test_merge_preserves_existing_when_incoming_empty():
    existing = LINE_A + "\n" + LINE_B
    assert merge_stance_sections(existing, "").strip() == existing.strip()


def test_merge_unknown_lines_always_appended():
    existing = "- raw line without link"
    incoming = "- another raw"
    out = merge_stance_sections(existing, incoming)
    assert "raw line" in out
    assert "another raw" in out
