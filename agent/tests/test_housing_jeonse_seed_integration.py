"""housing-jeonse-crisis-2026 seed must cover 8·13 부동산 대책 signals (ticket #1501)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data" / "issues" / "housing-jeonse-crisis-2026.yaml"

REQUIRED_KEYWORD_FRAGMENTS = (
    "부동산 대책",
    "주택 신속공급",
    "전월세",
    "금융 종합대책",
)


def test_housing_jeonse_seed_includes_813_policy_keywords():
    data = yaml.safe_load(SEED.read_text(encoding="utf-8"))
    assert data["slug"] == "housing-jeonse-crisis-2026"
    assert data["status"] == "ongoing"

    keywords = data.get("keywords") or []
    joined = " ".join(keywords)
    for frag in REQUIRED_KEYWORD_FRAGMENTS:
        assert frag in joined, f"missing keyword fragment: {frag}"

    summary = data.get("summary") or ""
    assert "8·13" in summary or "8.13" in summary or "부동산 대책" in summary
    # Policy issue: no person names as primary crawl keys
    assert not any(k for k in keywords if k.endswith(" 대통령") or k.endswith(" 장관"))
