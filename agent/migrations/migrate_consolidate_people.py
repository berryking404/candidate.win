#!/usr/bin/env python3
"""동일 인물의 orphan wiki slug 를 data/people/ canonical slug 로 통합.

orphan: wiki/content/people/{slug}.md 는 있으나 data/people/{slug}.yaml 는 없는 페이지.
canonical: data/people/{slug}.yaml 가 존재하는 slug.

처리 순서:
1. frontmatter title → canonical slug 매칭으로 orphan 식별
2. orphan 의 agent:events / agent:stances 를 canonical 인물 페이지에 병합
3. wiki 전체에서 /people/{orphan} → /people/{canonical} 치환
4. agent:stances 섹션 slug+입장 키 기준 중복 제거
5. orphan .md 삭제
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from migrations._paths import AGENT_ROOT, REPO_ROOT

sys.path.insert(0, str(AGENT_ROOT))

from publishers.stance_merge import merge_stance_sections

ROOT = REPO_ROOT
DATA_PEOPLE = ROOT / "data" / "people"
WIKI = ROOT / "wiki" / "content"
WIKI_PEOPLE = WIKI / "people"

FM_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
SECTION_RE = re.compile(
    r"(<!--\s*agent:(?P<id>[\w\-]+)\s*-->)(?P<body>.*?)(?P<close><!--\s*/agent:(?P=id)\s*-->)",
    re.DOTALL,
)
PEOPLE_LINK_RE = re.compile(r"\(/people/([a-z0-9-]+)\)")
SOURCE_URL_RE = re.compile(r"\]\((https?://[^)]+)\)")


@dataclass
class OrphanPage:
    path: Path
    slug: str
    title: str
    text: str


def load_canonical_slugs() -> set[str]:
    return {p.stem for p in DATA_PEOPLE.glob("*.yaml")}


def build_title_to_canonical() -> dict[str, str]:
    """name_ko·aliases → canonical slug (yaml SSoT)."""
    mapping: dict[str, str] = {}
    for path in DATA_PEOPLE.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        slug = data.get("slug") or path.stem
        names = [data.get("name_ko"), data.get("hangul_name")]
        names.extend(data.get("aliases") or [])
        for name in names:
            if name and name not in mapping:
                mapping[name.strip()] = slug
    return mapping


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FM_RE.match(text)
    if not m:
        return {}, text
    fm = yaml.safe_load(m.group(1)) or {}
    return fm, text[m.end() :]


def extract_section(text: str, section_id: str) -> str:
    for m in SECTION_RE.finditer(text):
        if m.group("id") == section_id:
            return m.group("body").strip()
    return ""


def replace_section(text: str, section_id: str, body: str) -> str:
    new_block = f"<!-- agent:{section_id} -->\n{body}\n<!-- /agent:{section_id} -->"

    def repl(m: re.Match) -> str:
        if m.group("id") != section_id:
            return m.group(0)
        return new_block

    return SECTION_RE.sub(repl, text, count=0)


def _event_line_key(line: str) -> str:
    url = SOURCE_URL_RE.search(line)
    if url:
        return url.group(1)
    return line.strip()


def merge_event_sections(existing: str, incoming: str) -> str:
    """출처 URL 기준 중복 제거 후 병합."""
    seen: set[str] = set()
    out: list[str] = []
    for block in (existing, incoming):
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            key = _event_line_key(stripped)
            if key in seen:
                continue
            seen.add(key)
            out.append(stripped)
    if not out:
        return ""
    return "\n".join(out) + "\n"


def dedupe_stance_section(body: str) -> str:
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return ""
    return merge_stance_sections("", "\n".join(lines))


def replace_people_links(text: str, redirects: dict[str, str]) -> str:
    if not redirects:
        return text

    def repl(m: re.Match) -> str:
        slug = m.group(1)
        canonical = redirects.get(slug)
        if canonical and canonical != slug:
            return f"(/people/{canonical})"
        return m.group(0)

    return PEOPLE_LINK_RE.sub(repl, text)


def find_orphans(canonical_slugs: set[str], title_to_canonical: dict[str, str]) -> list[OrphanPage]:
    orphans: list[OrphanPage] = []
    for path in sorted(WIKI_PEOPLE.glob("*.md")):
        if path.name == "_index.md":
            continue
        text = path.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        slug = str(fm.get("slug") or path.stem)
        title = str(fm.get("title") or "").strip()
        if slug in canonical_slugs:
            continue
        if not title or title not in title_to_canonical:
            continue
        orphans.append(OrphanPage(path=path, slug=slug, title=title, text=text))
    return orphans


def build_redirect_map(
    orphans: list[OrphanPage],
    title_to_canonical: dict[str, str],
    canonical_slugs: set[str],
) -> dict[str, str]:
    redirects: dict[str, str] = {}
    for orphan in orphans:
        canonical = title_to_canonical[orphan.title]
        if canonical not in canonical_slugs:
            continue
        if orphan.slug == canonical:
            continue
        redirects[orphan.slug] = canonical
    return redirects


def merge_orphan_into_canonical(
    orphan: OrphanPage,
    canonical_slug: str,
    *,
    dry_run: bool,
) -> bool:
    canonical_path = WIKI_PEOPLE / f"{canonical_slug}.md"
    orphan_events = extract_section(orphan.text, "events")
    orphan_stances = extract_section(orphan.text, "stances")

    if not orphan_events and not orphan_stances:
        return False

    if not canonical_path.exists():
        yaml_path = DATA_PEOPLE / f"{canonical_slug}.yaml"
        yaml_data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        fm = {
            "title": yaml_data.get("name_ko") or orphan.title,
            "slug": canonical_slug,
            "status": yaml_data.get("status", "curated"),
        }
        for key in ("role", "party"):
            if yaml_data.get(key):
                fm[key] = yaml_data[key]
        fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
        body = (
            f"---\n{fm_str}---\n\n"
            "## 행적\n\n<!-- agent:events -->\n"
            f"{orphan_events}\n"
            "<!-- /agent:events -->\n\n"
            "## 이슈별 입장\n\n<!-- agent:stances -->\n"
            f"{orphan_stances}\n"
            "<!-- /agent:stances -->\n"
        )
        if not dry_run:
            canonical_path.write_text(body, encoding="utf-8")
        return True

    text = canonical_path.read_text(encoding="utf-8")
    changed = False

    if orphan_events:
        merged_events = merge_event_sections(extract_section(text, "events"), orphan_events)
        new_text = replace_section(text, "events", merged_events.rstrip("\n"))
        if new_text != text:
            text = new_text
            changed = True

    if orphan_stances:
        merged_stances = merge_stance_sections(
            extract_section(text, "stances"),
            orphan_stances,
        )
        merged_stances = dedupe_stance_section(merged_stances)
        new_text = replace_section(text, "stances", merged_stances.rstrip("\n"))
        if new_text != text:
            text = new_text
            changed = True

    if changed and not dry_run:
        canonical_path.write_text(text, encoding="utf-8")
    return changed


def rewrite_wiki_file(path: Path, redirects: dict[str, str], *, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    new_text = replace_people_links(text, redirects)
    if new_text == text:
        return False

    def repl_stances(m: re.Match) -> str:
        if m.group("id") != "stances":
            return m.group(0)
        body = m.group("body").strip()
        deduped = dedupe_stance_section(body)
        inner = f"\n{deduped.rstrip()}\n" if deduped else "\n"
        return f"{m.group(1)}{inner}{m.group('close')}"

    new_text = SECTION_RE.sub(repl_stances, new_text)
    if new_text == text:
        return False
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return True


def dedupe_all_stance_sections(path: Path, *, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False

    def repl(m: re.Match) -> str:
        nonlocal changed
        if m.group("id") != "stances":
            return m.group(0)
        body = m.group("body").strip()
        deduped = dedupe_stance_section(body)
        new_body = f"\n{deduped.rstrip()}\n" if deduped else "\n"
        old_body = f"\n{body}\n" if body else "\n"
        if new_body != old_body:
            changed = True
        return f"{m.group(1)}{new_body}{m.group('close')}"

    new_text = SECTION_RE.sub(repl, text)
    if changed and not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return changed


def run(*, dry_run: bool, verbose: bool) -> int:
    canonical_slugs = load_canonical_slugs()
    title_to_canonical = build_title_to_canonical()
    orphans = find_orphans(canonical_slugs, title_to_canonical)
    redirects = build_redirect_map(orphans, title_to_canonical, canonical_slugs)

    if verbose:
        print(f"canonical slugs: {len(canonical_slugs)}")
        print(f"orphan pages: {len(orphans)}")
        for slug, canonical in sorted(redirects.items()):
            print(f"  {slug} → {canonical}")

    merged = 0
    for orphan in orphans:
        canonical = redirects.get(orphan.slug)
        if not canonical:
            continue
        if merge_orphan_into_canonical(orphan, canonical, dry_run=dry_run):
            merged += 1
            if verbose:
                print(f"merged content: {orphan.slug} → {canonical}")

    rewritten = 0
    for kind in ("people", "issues"):
        for path in sorted((WIKI / kind).glob("*.md")):
            if path.name == "_index.md":
                continue
            if rewrite_wiki_file(path, redirects, dry_run=dry_run):
                rewritten += 1
                if verbose:
                    print(f"rewrote links: {path.relative_to(ROOT)}")

    deduped = 0
    for kind in ("people", "issues"):
        for path in sorted((WIKI / kind).glob("*.md")):
            if path.name == "_index.md":
                continue
            if dedupe_all_stance_sections(path, dry_run=dry_run):
                deduped += 1
                if verbose:
                    print(f"deduped stances: {path.relative_to(ROOT)}")

    deleted = 0
    for orphan in orphans:
        if orphan.slug not in redirects:
            continue
        if not dry_run:
            orphan.path.unlink(missing_ok=True)
        deleted += 1
        if verbose:
            print(f"deleted orphan: {orphan.path.name}")

    mode = "dry-run" if dry_run else "applied"
    print(
        f"[{mode}] redirects={len(redirects)}, merged={merged}, "
        f"rewritten={rewritten}, deduped={deduped}, deleted={deleted}"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="변경 내용만 출력하고 파일은 수정하지 않음",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(dry_run=args.dry_run, verbose=args.verbose))


if __name__ == "__main__":
    main()
