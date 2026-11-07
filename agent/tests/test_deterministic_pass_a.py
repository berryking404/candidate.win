"""deterministic Pass A — DeepAgents 없이 tools 고정 순서 호출."""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))

import deep_agent


@pytest.fixture
def issue_repo(tmp_path, monkeypatch):
    issues = tmp_path / "issues"
    people = tmp_path / "people"
    issues.mkdir()
    people.mkdir()
    (issues / "demo-issue-2026.yaml").write_text(
        yaml.dump(
            {
                "slug": "demo-issue-2026",
                "title_ko": "데모 이슈",
                "keywords": ["데모"],
                "seed_people": ["kim-demo"],
                "status": "ongoing",
                "stances": {"support": "찬성", "oppose": "반대"},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (people / "kim-demo.yaml").write_text(
        yaml.dump(
            {
                "slug": "kim-demo",
                "name_ko": "김데모",
                "aliases": ["김데모"],
                "sources": {"news_keywords": ["김데모"], "youtube_channels": []},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(deep_agent, "DATA_ISSUES", issues)
    monkeypatch.setattr(deep_agent, "DATA_PEOPLE", people)
    return tmp_path


def test_run_issue_calls_tools_in_fixed_order(issue_repo, monkeypatch):
    calls: list[str] = []

    def crawl_news(keywords, date_from=None):
        calls.append("crawl_news")
        return [{"url": "https://n.example/1", "title": "t", "text": "김데모 찬성", "date": "2026-01-01"}]

    def crawl_youtube(channel_ids, keywords=None, no_youtube=False):
        calls.append("crawl_youtube")
        return []

    def find_participants(texts, issue_slug):
        calls.append("find_participants")
        return [
            {
                "name_ko": "김데모",
                "matched_slug": "kim-demo",
                "role_hint": "",
                "mention_count": 2,
            }
        ]

    def register_person(*args, **kwargs):
        calls.append("register_person")
        return {"slug": "new-person", "created": True, "pending": False}

    def extract_stance(texts, person_slug, person_name, issue_slug, **kwargs):
        calls.append("extract_stance")
        return {
            "position": "support",
            "summary": "찬성한다",
            "quotes": [{"text": "찬성", "source_url": "https://n.example/1"}],
            "confidence": 0.9,
            "escalated": False,
        }

    def create_wiki_page(kind, slug, title, summary=""):
        calls.append(f"create_wiki_page:{kind}")
        return {"created": True, "path": f"{kind}/{slug}.md"}

    def append_agent_stances(kind, slug, new_content):
        calls.append(f"append_agent_stances:{kind}")
        assert "지지" in new_content
        return {"written": True, "diff_lines": 1}

    def commit_changes(summary, dry_run=False):
        calls.append("commit_changes")
        assert dry_run is False
        return "abc123"

    monkeypatch.setattr(deep_agent, "crawl_news", crawl_news)
    monkeypatch.setattr(deep_agent, "crawl_youtube", crawl_youtube)
    monkeypatch.setattr(deep_agent, "find_participants", find_participants)
    monkeypatch.setattr(deep_agent, "register_person", register_person)
    monkeypatch.setattr(deep_agent, "extract_stance", extract_stance)
    monkeypatch.setattr(deep_agent, "create_wiki_page", create_wiki_page)
    monkeypatch.setattr(deep_agent, "append_agent_stances", append_agent_stances)
    monkeypatch.setattr(deep_agent, "commit_changes", commit_changes)

    opts = Namespace(dry_run=False, no_youtube=False, no_escalate=False, max_stubs=5)
    deep_agent.run_issue("demo-issue-2026", opts)

    assert calls[0] == "crawl_news"
    assert "find_participants" in calls
    assert "extract_stance" in calls
    assert "create_wiki_page:issues" in calls
    assert "append_agent_stances:issues" in calls
    assert "append_agent_stances:people" in calls
    assert calls[-1] == "commit_changes"
    assert "register_person" not in calls  # already matched


def test_run_issue_dry_run_skips_commit(issue_repo, monkeypatch):
    commits = []

    monkeypatch.setattr(
        deep_agent,
        "crawl_news",
        lambda *a, **k: [{"url": "https://x", "title": "t", "text": "본문", "date": None}],
    )
    monkeypatch.setattr(deep_agent, "crawl_youtube", lambda *a, **k: [])
    monkeypatch.setattr(
        deep_agent,
        "find_participants",
        lambda *a, **k: [{"name_ko": "김데모", "matched_slug": "kim-demo", "mention_count": 1}],
    )
    monkeypatch.setattr(
        deep_agent,
        "extract_stance",
        lambda *a, **k: {
            "position": "oppose",
            "summary": "반대",
            "quotes": [{"text": "반대", "source_url": "https://x"}],
            "confidence": 0.8,
            "escalated": False,
        },
    )
    monkeypatch.setattr(deep_agent, "create_wiki_page", lambda *a, **k: {"created": False})
    monkeypatch.setattr(deep_agent, "append_agent_stances", lambda *a, **k: {"written": True})
    monkeypatch.setattr(
        deep_agent, "commit_changes", lambda *a, **k: commits.append(True) or None
    )

    opts = Namespace(dry_run=True, no_youtube=True, no_escalate=False, max_stubs=5)
    deep_agent.run_issue("demo-issue-2026", opts)
    assert commits == []


def test_no_deepagents_or_openai_orchestrator_import():
    src = Path(deep_agent.__file__).read_text(encoding="utf-8")
    assert "create_deep_agent" not in src
    assert "openai:gpt" not in src
    assert "from deepagents" not in src


def test_run_person_writes_events(tmp_path, monkeypatch):
    people = tmp_path / "people"
    people.mkdir()
    (people / "kim-demo.yaml").write_text(
        yaml.dump(
            {
                "slug": "kim-demo",
                "name_ko": "김데모",
                "aliases": ["김데모"],
                "sources": {"news_keywords": ["김데모"], "youtube_channels": []},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(deep_agent, "DATA_PEOPLE", people)
    calls = []

    monkeypatch.setattr(
        deep_agent,
        "crawl_news",
        lambda *a, **k: [{"url": "https://x", "title": "t", "text": "김데모 발언", "date": "2026-01-02"}],
    )
    monkeypatch.setattr(deep_agent, "crawl_youtube", lambda *a, **k: [])
    monkeypatch.setattr(
        deep_agent,
        "extract_events",
        lambda *a, **k: (calls.append("extract_events") or [{"date": "2026-01-02", "event": "발언", "source_url": "https://x"}]),
    )
    monkeypatch.setattr(
        deep_agent,
        "create_wiki_page",
        lambda *a, **k: (calls.append("create_wiki_page") or {"created": True}),
    )
    monkeypatch.setattr(
        deep_agent,
        "write_agent_section",
        lambda *a, **k: (calls.append("write_agent_section") or {"written": True}),
    )
    monkeypatch.setattr(
        deep_agent,
        "commit_changes",
        lambda *a, **k: (calls.append("commit_changes") or "sha"),
    )

    opts = Namespace(dry_run=False, no_youtube=True)
    deep_agent.run_person("kim-demo", opts)
    assert calls == [
        "extract_events",
        "create_wiki_page",
        "write_agent_section",
        "commit_changes",
    ]
