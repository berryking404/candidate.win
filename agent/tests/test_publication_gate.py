from __future__ import annotations

from pathlib import Path

import yaml

import publication_gate


def test_count_issue_stances_only_counts_people_links():
    md = """## 인물별 입장

<!-- agent:stances -->
- [홍길동](/people/hong-gil-dong) — **지지**: 요약. [출처](https://example.com)
- [기관](/orgs/agency) — **반대**: 요약.
<!-- /agent:stances -->
"""
    assert publication_gate.count_issue_stances(md) == 1


def test_find_zero_stance_blockers_for_changed_ongoing_issue(tmp_path: Path):
    data_dir = tmp_path / "data" / "issues"
    wiki_dir = tmp_path / "wiki" / "content" / "issues"
    data_dir.mkdir(parents=True)
    wiki_dir.mkdir(parents=True)
    (data_dir / "new-topic.yaml").write_text(
        yaml.safe_dump({"slug": "new-topic", "status": "ongoing"}, allow_unicode=True),
        encoding="utf-8",
    )
    (wiki_dir / "new-topic.md").write_text(
        "---\ntitle: 새 이슈\nstatus: ongoing\n---\n\n## 인물별 입장\n\n<!-- agent:stances -->\n<!-- /agent:stances -->\n",
        encoding="utf-8",
    )

    blockers = publication_gate.find_zero_stance_blockers(
        changed_paths=["data/issues/new-topic.yaml", "wiki/content/issues/new-topic.md"],
        data_dir=data_dir,
        wiki_dir=wiki_dir,
    )
    assert [b.slug for b in blockers] == ["new-topic"]


def test_find_zero_stance_blockers_ignores_closed_or_unchanged(tmp_path: Path):
    data_dir = tmp_path / "data" / "issues"
    wiki_dir = tmp_path / "wiki" / "content" / "issues"
    data_dir.mkdir(parents=True)
    wiki_dir.mkdir(parents=True)
    (data_dir / "closed-topic.yaml").write_text(
        yaml.safe_dump({"slug": "closed-topic", "status": "closed"}, allow_unicode=True),
        encoding="utf-8",
    )
    (wiki_dir / "closed-topic.md").write_text(
        "---\ntitle: 종료 이슈\nstatus: closed\n---\n\n<!-- agent:stances -->\n<!-- /agent:stances -->\n",
        encoding="utf-8",
    )

    assert publication_gate.find_zero_stance_blockers(
        changed_paths=["wiki/content/issues/closed-topic.md"],
        data_dir=data_dir,
        wiki_dir=wiki_dir,
    ) == []
    assert publication_gate.find_zero_stance_blockers(
        changed_paths=[],
        data_dir=data_dir,
        wiki_dir=wiki_dir,
    ) == []
