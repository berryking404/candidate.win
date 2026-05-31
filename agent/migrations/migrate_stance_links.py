"""기존 wiki stance 섹션에 인물·이슈 페이지 링크를 추가하는 마이그레이션 스크립트.

- issue 페이지: **인물 이름** → [인물 이름](/people/{slug})
- people 페이지: **이슈 제목** → [이슈 제목](/issues/{slug})

이미 링크가 있는 줄은 건드리지 않는다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from migrations._paths import REPO_ROOT

ROOT = REPO_ROOT
DATA_PEOPLE = ROOT / "data" / "people"
DATA_ISSUES = ROOT / "data" / "issues"
WIKI_PEOPLE = ROOT / "wiki" / "content" / "people"
WIKI_ISSUES = ROOT / "wiki" / "content" / "issues"

SECTION_RE = re.compile(
    r"(<!--\s*agent:stances\s*-->)(.*?)(<!--\s*/agent:stances\s*-->)",
    re.DOTALL,
)
# 볼드 이름 (링크 아님): - **이름** — 또는 - **이름** —
BOLD_NAME_RE = re.compile(r"^(- )\*\*(.+?)\*\*( — )", re.MULTILINE)


def _build_people_map() -> dict[str, str]:
    """name_ko → slug 매핑 구축."""
    mapping: dict[str, str] = {}
    for path in DATA_PEOPLE.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        slug = data.get("slug") or path.stem
        name_ko = data.get("name_ko")
        if name_ko:
            mapping[name_ko] = slug
        for alias in data.get("aliases", []) or []:
            if alias and alias not in mapping:
                mapping[alias] = slug
    return mapping


def _build_issues_map() -> dict[str, str]:
    """title_ko → slug 매핑 구축."""
    mapping: dict[str, str] = {}
    for path in DATA_ISSUES.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        slug = data.get("slug") or path.stem
        title_ko = data.get("title_ko")
        if title_ko:
            mapping[title_ko.strip()] = slug
    return mapping


def _migrate_section(content: str, name_to_slug: dict[str, str], url_prefix: str) -> tuple[str, int]:
    """stance 섹션 내 볼드 이름을 링크로 교체. 변경 수 반환."""
    changes = 0

    def replace_bold(m: re.Match) -> str:
        nonlocal changes
        prefix, name, suffix = m.group(1), m.group(2), m.group(3)
        slug = name_to_slug.get(name.strip())
        if slug:
            changes += 1
            return f"{prefix}[{name}]({url_prefix}{slug}){suffix}"
        return m.group(0)

    return BOLD_NAME_RE.sub(replace_bold, content), changes


def migrate_issue_pages(people_map: dict[str, str]) -> int:
    """이슈 페이지의 인물 이름에 /people/{slug} 링크 추가."""
    total = 0
    for path in WIKI_ISSUES.glob("*.md"):
        if path.name == "_index.md":
            continue
        text = path.read_text(encoding="utf-8")

        def replace_section(m: re.Match) -> str:
            open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)
            new_body, n = _migrate_section(body, people_map, "/people/")
            nonlocal total
            total += n
            return f"{open_tag}{new_body}{close_tag}"

        new_text = SECTION_RE.sub(replace_section, text)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            print(f"  [issue] {path.name}")

    return total


def migrate_people_pages(issues_map: dict[str, str]) -> int:
    """인물 페이지의 이슈 제목에 /issues/{slug} 링크 추가."""
    total = 0
    for path in WIKI_PEOPLE.glob("*.md"):
        if path.name == "_index.md":
            continue
        text = path.read_text(encoding="utf-8")

        def replace_section(m: re.Match) -> str:
            open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)
            new_body, n = _migrate_section(body, issues_map, "/issues/")
            nonlocal total
            total += n
            return f"{open_tag}{new_body}{close_tag}"

        new_text = SECTION_RE.sub(replace_section, text)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            print(f"  [people] {path.name}")

    return total


def main() -> None:
    print("매핑 구축 중...")
    people_map = _build_people_map()
    issues_map = _build_issues_map()
    print(f"  인물: {len(people_map)}건, 이슈: {len(issues_map)}건")

    print("\n이슈 페이지 마이그레이션...")
    n1 = migrate_issue_pages(people_map)

    print("\n인물 페이지 마이그레이션...")
    n2 = migrate_people_pages(issues_map)

    print(f"\n완료: 이슈 페이지 {n1}건, 인물 페이지 {n2}건 링크 추가")


if __name__ == "__main__":
    main()
