"""Correction regression: yun-jeon stub must fold into canonical yun-seok-yeol."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PEOPLE_DATA = ROOT / "data" / "people"
PEOPLE_WIKI = ROOT / "wiki" / "content" / "people"
WIKI_CONTENT = ROOT / "wiki" / "content"

# GH #29 / factory 91d3e50e — "윤전" was a mangled stub for 윤석열.
ORPHAN_SLUG = "yun-jeon"
CANONICAL_SLUG = "yun-seok-yeol"
ORPHAN_ALIAS = "윤전"


def test_yun_jeon_ssot_and_wiki_absent() -> None:
    assert not (PEOPLE_DATA / f"{ORPHAN_SLUG}.yaml").exists()
    assert not (PEOPLE_WIKI / f"{ORPHAN_SLUG}.md").exists()


def test_yun_seok_yeol_carries_yun_jeon_alias_and_hugo_redirect() -> None:
    data = yaml.safe_load((PEOPLE_DATA / f"{CANONICAL_SLUG}.yaml").read_text(encoding="utf-8"))
    assert ORPHAN_ALIAS in (data.get("aliases") or [])

    text = (PEOPLE_WIKI / f"{CANONICAL_SLUG}.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---", 2)[1])
    aliases = fm.get("aliases") or []
    assert "/people/yun-jeon/" in aliases or "/people/yun-jeon" in aliases


def test_no_wiki_people_links_point_at_yun_jeon() -> None:
    needle = f"](/people/{ORPHAN_SLUG})"
    hits: list[str] = []
    for path in WIKI_CONTENT.rglob("*.md"):
        body = path.read_text(encoding="utf-8")
        if needle in body:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []
