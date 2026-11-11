"""Takedown regression: non-person org stubs must not remain under /people."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PEOPLE_DATA = ROOT / "data" / "people"
PEOPLE_WIKI = ROOT / "wiki" / "content" / "people"

# GH #27 / factory ee9febc4 — slug was "정부" (government), not a person.
# GH #28 / factory d7107d79 — slug was "배재고" (high school), not a person.
# GH #30 / factory 70a4029b — slug was "노동부" (ministry), not a person.
TAKEN_DOWN_NON_PERSON_SLUGS = ("jeong-bu", "bae-jae-go", "no-dong-bu")


def test_taken_down_non_person_people_files_absent() -> None:
    for slug in TAKEN_DOWN_NON_PERSON_SLUGS:
        assert not (PEOPLE_DATA / f"{slug}.yaml").exists(), slug
        assert not (PEOPLE_WIKI / f"{slug}.md").exists(), slug
