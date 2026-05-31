"""migrate_consolidate_people 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))

from migrations.migrate_consolidate_people import (
    build_redirect_map,
    dedupe_stance_section,
    find_orphans,
    load_canonical_slugs,
    merge_event_sections,
    merge_orphan_into_canonical,
    OrphanPage,
    replace_people_links,
    rewrite_wiki_file,
)


def test_replace_people_links():
    redirects = {"ahn-gyubaek": "an-gyu-baek", "an": "an-gyu-baek"}
    text = (
        "- [안규백](/people/ahn-gyubaek) — **지지**: a.\n"
        "- [안규백](/people/an-gyu-baek) — **지지**: b.\n"
    )
    out = replace_people_links(text, redirects)
    assert "/people/an-gyu-baek" in out
    assert "/people/ahn-gyubaek" not in out
    assert "/people/an)" not in out


def test_dedupe_stance_section_same_person_different_slug():
    body = "\n".join(
        [
            "- [안규백](/people/ahn-gyubaek) — **지지**: a. [출처](https://a)",
            "- [안규백](/people/an-gyu-baek) — **지지**: b. [출처](https://b)",
            "- [안규백](/people/an) — **지지**: c. [출처](https://c)",
        ]
    )
    out = dedupe_stance_section(body)
    assert out.count("an-gyu-baek") == 1
    assert "https://a" in out


def test_merge_event_sections_dedupes_by_url():
    existing = "- 2026-05-09: 방문. [출처](https://news.example/1)"
    incoming = "- 2026-05-09: 같은 기사. [출처](https://news.example/1)"
    out = merge_event_sections(existing, incoming)
    assert out.count("https://news.example/1") == 1


def test_merge_event_sections_keeps_different_urls():
    existing = "- 2026-05-09: a. [출처](https://news.example/1)"
    incoming = "- 2026-05-10: b. [출처](https://news.example/2)"
    out = merge_event_sections(existing, incoming)
    assert "https://news.example/1" in out
    assert "https://news.example/2" in out


def test_build_redirect_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_people = tmp_path / "data" / "people"
    wiki_people = tmp_path / "wiki" / "content" / "people"
    data_people.mkdir(parents=True)
    wiki_people.mkdir(parents=True)

    (data_people / "an-gyu-baek.yaml").write_text(
        yaml.dump(
            {"slug": "an-gyu-baek", "name_ko": "안규백", "status": "curated"},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (wiki_people / "ahn-gyubaek.md").write_text(
        "---\ntitle: 안규백\nslug: ahn-gyubaek\nstatus: stub\n---\n\n",
        encoding="utf-8",
    )

    import migrations.migrate_consolidate_people as mod

    monkeypatch.setattr(mod, "DATA_PEOPLE", data_people)
    monkeypatch.setattr(mod, "WIKI_PEOPLE", wiki_people)

    canonical = load_canonical_slugs()
    title_map = mod.build_title_to_canonical()
    orphans = find_orphans(canonical, title_map)
    redirects = build_redirect_map(orphans, title_map, canonical)

    assert redirects == {"ahn-gyubaek": "an-gyu-baek"}


def test_end_to_end_merge_and_rewrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_people = tmp_path / "data" / "people"
    wiki = tmp_path / "wiki" / "content"
    wiki_people = wiki / "people"
    wiki_issues = wiki / "issues"
    for d in (data_people, wiki_people, wiki_issues):
        d.mkdir(parents=True)

    (data_people / "an-gyu-baek.yaml").write_text(
        yaml.dump(
            {
                "slug": "an-gyu-baek",
                "name_ko": "안규백",
                "status": "curated",
                "role": "국방부 장관",
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (wiki_people / "an-gyu-baek.md").write_text(
        "---\ntitle: 안규백\nslug: an-gyu-baek\nstatus: curated\n---\n\n"
        "## 행적\n\n<!-- agent:events -->\n<!-- /agent:events -->\n\n"
        "## 이슈별 입장\n\n<!-- agent:stances -->\n"
        "- [전작권](/issues/opcon-transfer-2026) — **지지**: canonical. [출처](https://c)\n"
        "<!-- /agent:stances -->\n",
        encoding="utf-8",
    )
    (wiki_people / "ahn-gyubaek.md").write_text(
        "---\ntitle: 안규백\nslug: ahn-gyubaek\nstatus: stub\n---\n\n"
        "## 행적\n\n<!-- agent:events -->\n"
        "- 2026-05-09: 미국 방문. [출처](https://orphan-event)\n"
        "<!-- /agent:events -->\n\n"
        "## 이슈별 입장\n\n<!-- agent:stances -->\n"
        "- [전작권](/issues/opcon-transfer-2026) — **지지**: orphan. [출처](https://orphan-stance)\n"
        "<!-- /agent:stances -->\n",
        encoding="utf-8",
    )
    (wiki_issues / "opcon-transfer-2026.md").write_text(
        "---\ntitle: 전작권\nslug: opcon-transfer-2026\n---\n\n"
        "## 인물별 입장\n\n<!-- agent:stances -->\n"
        "- [안규백](/people/ahn-gyubaek) — **지지**: a. [출처](https://a)\n"
        "- [안규백](/people/an-gyu-baek) — **지지**: b. [출처](https://b)\n"
        "<!-- /agent:stances -->\n",
        encoding="utf-8",
    )

    import migrations.migrate_consolidate_people as mod

    monkeypatch.setattr(mod, "DATA_PEOPLE", data_people)
    monkeypatch.setattr(mod, "WIKI", wiki)
    monkeypatch.setattr(mod, "WIKI_PEOPLE", wiki_people)
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    canonical = load_canonical_slugs()
    title_map = mod.build_title_to_canonical()
    orphans = find_orphans(canonical, title_map)
    redirects = mod.build_redirect_map(orphans, title_map, canonical)

    orphan = orphans[0]
    assert merge_orphan_into_canonical(orphan, "an-gyu-baek", dry_run=False)

    canonical_text = (wiki_people / "an-gyu-baek.md").read_text(encoding="utf-8")
    assert "https://orphan-event" in canonical_text
    assert "https://c" in canonical_text
    assert "https://orphan-stance" not in canonical_text

    rewrite_wiki_file(wiki_issues / "opcon-transfer-2026.md", redirects, dry_run=False)
    issue_text = (wiki_issues / "opcon-transfer-2026.md").read_text(encoding="utf-8")
    assert issue_text.count("/people/an-gyu-baek") == 1
    assert "/people/ahn-gyubaek" not in issue_text
