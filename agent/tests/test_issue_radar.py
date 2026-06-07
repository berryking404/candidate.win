from __future__ import annotations

import json
from pathlib import Path

import issue_radar


def test_parse_approvals_korean_and_english():
    assert issue_radar.parse_approvals("승인: 1, 3\n반려: 2") == {1: "approve", 3: "approve", 2: "reject"}
    assert issue_radar.parse_approvals("approve: 4 reject: 5") == {4: "approve", 5: "reject"}
    assert issue_radar.parse_approvals("종료 승인: 1\n신규 승인: 2") == {2: "approve"}
    assert issue_radar.parse_closure_approvals("종료 승인: 1,3\n종료 반려: 2") == {1: "close", 3: "close", 2: "reject"}
    assert issue_radar.parse_approvals("a. 1,2 반려") == {1: "reject", 2: "reject"}
    assert issue_radar.parse_approvals("모두 반려", candidate_count=3) == {1: "reject", 2: "reject", 3: "reject"}
    assert issue_radar.parse_closure_approvals("b. 2,3 종료") == {2: "close", 3: "close"}


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
    closure = issue_radar.ClosureCandidate(
        slug="old-event-2026",
        title="오래된 사건형 이슈",
        score=8,
        recommendation="closed 후보",
        reasons=["최근 수집 기사 없음", "사건형 이슈"],
        signals={"window_days": 30, "recent_news_count": 0, "stance_count": 3, "issue_type": "event", "latest_source_date": "2026-01-01"},
    )
    report = issue_radar.render_report([cand], [closure], window_days=1)
    assert "승인: 1,3" in report
    assert "종료 승인: 1" in report
    assert "## B. 종료/전환 후보" in report
    assert "국회 특검법 논란" in report
    assert "오래된 사건형 이슈" in report


def test_score_closure_candidate_event_vs_policy():
    score, rec, reasons = issue_radar.score_closure_candidate(recent_news_count=0, latest_source_days=90, stance_count=0, issue_type="event")
    assert score >= 7
    assert rec == "closed 후보"
    assert "사건형 이슈" in reasons

    policy_score, policy_rec, _ = issue_radar.score_closure_candidate(recent_news_count=0, latest_source_days=90, stance_count=0, issue_type="policy")
    assert policy_score < score
    assert policy_rec == "monitoring/mature 전환 후보"
