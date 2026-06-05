from __future__ import annotations

import json
from pathlib import Path

import issue_radar


def test_parse_approvals_korean_and_english():
    assert issue_radar.parse_approvals("승인: 1, 3\n반려: 2") == {1: "approve", 3: "approve", 2: "reject"}
    assert issue_radar.parse_approvals("approve: 4 reject: 5") == {4: "approve", 5: "reject"}


def test_score_candidate_standalone():
    score, rec, merge_target, breakdown = issue_radar.score_candidate(
        keyword="국회 특검법 논란",
        title="국회 특검법 논란 확산",
        articles=[{"url": "https://a.example/x"}, {"url": "https://b.example/y"}, {"url": "https://c.example/z"}],
        outlet_count=3,
        actors=["국민의힘", "민주당"],
        official_count=1,
        duplicate_matches=[],
    )
    assert score >= 7
    assert rec == "독립 이슈"
    assert merge_target is None
    assert breakdown["news_volume"] == 2


def test_score_candidate_duplicate_merge():
    score, rec, merge_target, _ = issue_radar.score_candidate(
        keyword="개인정보 유출 정부 대응",
        title="개인정보 유출 정부 대응 논란",
        articles=[{"url": "https://a.example/x"}, {"url": "https://b.example/y"}, {"url": "https://c.example/z"}],
        outlet_count=3,
        actors=["정부", "국회"],
        official_count=1,
        duplicate_matches=[{"slug": "coupang-data-leak-2026", "title": "쿠팡 개인정보", "similarity": 0.3}],
    )
    assert score >= 4
    assert rec == "기존 이슈 병합/업데이트"
    assert merge_target == "coupang-data-leak-2026"


def test_render_report_contains_approval_instructions():
    cand = issue_radar.Candidate(
        title="국회 특검법 논란",
        keyword="특검법",
        slug="special-counsel-2026-test",
        score=9,
        recommendation="독립 이슈",
        merge_target=None,
        signals={"news_count": 3, "outlet_count": 3, "stance_actor_terms": ["국민의힘", "민주당"], "breakdown": {}},
        articles=[{"title": "기사 제목", "url": "https://example.com"}],
        official_signals=[],
        duplicate_matches=[],
    )
    report = issue_radar.render_report([cand], window_days=1)
    assert "승인: 1,3" in report
    assert "독립 이슈 후보의 SSoT" in report
    assert "국회 특검법 논란" in report
