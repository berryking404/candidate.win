from __future__ import annotations

import json
from pathlib import Path

import yaml

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


def test_suppresses_directed_merge_topics_from_candidate_reports():
    special = issue_radar.Candidate(
        title="종합특검, 김건희 수사 무마 의혹 조사",
        keyword="종합특검",
        slug="special-counsel-test",
        score=6,
        recommendation="기존 이슈 병합/업데이트",
        merge_target="comprehensive-special-counsel-probes-2026",
        signals={},
        articles=[],
        official_signals=[],
        duplicate_matches=[],
    )
    nec = issue_radar.Candidate(
        title="선관위 성과급 논란",
        keyword="선관위 개혁",
        slug="nec-test",
        score=6,
        recommendation="기존 이슈 병합/업데이트",
        merge_target="election-commission-management-controversy-2026",
        signals={},
        articles=[],
        official_signals=[],
        duplicate_matches=[],
    )
    other = issue_radar.Candidate(
        title="홈플러스 국회 청문회 재점화",
        keyword="홈플러스 국회 청문회",
        slug="homeplus-hearing-test",
        score=4,
        recommendation="보류 후 추가 확인",
        merge_target=None,
        signals={},
        articles=[],
        official_signals=[],
        duplicate_matches=[],
    )
    assert issue_radar.is_suppressed_candidate_topic(special)
    assert issue_radar.is_suppressed_candidate_topic(nec)
    assert not issue_radar.is_suppressed_candidate_topic(other)


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


def test_infer_seed_people_from_existing_people_names(tmp_path: Path):
    people_dir = tmp_path / "people"
    people_dir.mkdir()
    (people_dir / "han-dong-hun.yaml").write_text(
        yaml.safe_dump({"name_ko": "한동훈", "aliases": ["한동훈 의원", "한 의원"]}, allow_unicode=True),
        encoding="utf-8",
    )
    (people_dir / "o-se-hun.yaml").write_text(
        yaml.safe_dump({"name_ko": "오세훈", "aliases": ["오세훈 시장"]}, allow_unicode=True),
        encoding="utf-8",
    )
    cand = issue_radar.Candidate(
        title="선관위 논란에 한동훈·오세훈 비판",
        keyword="선관위 논란",
        slug="nec-test",
        score=9,
        recommendation="독립 이슈",
        merge_target=None,
        signals={},
        articles=[{"title": "한동훈 의원과 오세훈 시장, 선관위 관리 부실 비판"}],
        official_signals=[],
        duplicate_matches=[],
    )
    assert issue_radar.infer_seed_people(cand, people_dir=people_dir) == ["han-dong-hun", "o-se-hun"]


def test_create_issue_shell_writes_inferred_seed_people(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data" / "issues"
    wiki_dir = tmp_path / "wiki" / "content" / "issues"
    people_dir = tmp_path / "data" / "people"
    data_dir.mkdir(parents=True)
    wiki_dir.mkdir(parents=True)
    people_dir.mkdir(parents=True)
    (people_dir / "jeon-jin-suk.yaml").write_text(
        yaml.safe_dump({"name_ko": "전진숙"}, allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setattr(issue_radar, "DATA_ISSUES", data_dir)
    monkeypatch.setattr(issue_radar, "WIKI_ISSUES", wiki_dir)
    monkeypatch.setattr(issue_radar, "DATA_PEOPLE", people_dir)

    result = issue_radar.create_issue_shell({
        "slug": "nec-test",
        "title": "선관위 홍보영상 논란",
        "keyword": "선관위 홍보영상",
        "articles": [{"title": "전진숙, 선관위 홍보영상 경위 밝혀야", "url": "https://example.com/a", "date": "2026-06-06"}],
    })

    assert result == "생성: nec-test"
    data = yaml.safe_load((data_dir / "nec-test.yaml").read_text(encoding="utf-8"))
    assert data["seed_people"] == ["jeon-jin-suk"]
    assert (wiki_dir / "nec-test.md").exists()
