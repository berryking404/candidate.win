"""Candydate Agent 진입점 — deterministic Pass A (DeepAgents/OpenAI 오케스트레이터 없음).

사용법:
    python deep_agent.py --person lee-jae-myung
    python deep_agent.py --issue real-estate-tax-2026   # status 무관
    python deep_agent.py --all   # data/issues/*.yaml 중 status: ongoing 만

플래그:
    --dry-run        커밋 없이 파이프라인만 실행
    --no-escalate    escalation 큐 enqueue 차단
    --no-youtube     YouTube 호출 전체 차단
    --max-stubs N    1회 실행당 stub 생성 상한
    --time-cap N     실행 시간 상한 분 (기본 30)
    --invalidate-cache [tool]  LLM 캐시 삭제
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATA_PEOPLE = Path(__file__).parent.parent / "data" / "people"
DATA_ISSUES = Path(__file__).parent.parent / "data" / "issues"

# tools — 테스트에서 monkeypatch 가능하도록 모듈 속성으로 노출
from tools import (  # noqa: E402
    append_agent_stances,
    commit_changes,
    crawl_news,
    crawl_youtube,
    create_wiki_page,
    extract_events,
    extract_stance,
    find_participants,
    register_person,
    write_agent_section,
)

POSITION_KO = {
    "support": "지지",
    "oppose": "반대",
    "neutral": "중립",
    "mixed": "혼합",
}


def _load_issue_yaml(slug: str) -> dict | None:
    path = DATA_ISSUES / f"{slug}.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


def _load_person_yaml(slug: str) -> dict | None:
    path = DATA_PEOPLE / f"{slug}.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


def _ongoing_issue_slugs() -> list[str]:
    slugs: list[str] = []
    for f in sorted(DATA_ISSUES.glob("*.yaml")):
        data = _load_issue_yaml(f.stem) or {}
        if data.get("status", "ongoing") == "ongoing":
            slugs.append(f.stem)
    return slugs


def _source_url_from_stance(stance: dict, fallback_urls: list[str]) -> str | None:
    from publishers.quality_gate import is_valid_source_url

    for q in stance.get("quotes") or []:
        if isinstance(q, dict):
            url = q.get("source_url")
            if is_valid_source_url(url):
                return str(url).strip()
    for url in fallback_urls:
        if is_valid_source_url(url):
            return str(url).strip()
    return None


def _format_issue_stance_line(
    person_slug: str,
    person_name: str,
    stance: dict,
    fallback_urls: list[str],
) -> str | None:
    label = POSITION_KO.get(stance.get("position", ""))
    if not label:
        return None
    summary = (stance.get("summary") or "").strip() or label
    url = _source_url_from_stance(stance, fallback_urls)
    if not url:
        return None
    return f"- [{person_name}](/people/{person_slug}) — **{label}**: {summary}. [출처]({url})"


def _format_person_stance_line(
    issue_slug: str,
    issue_title: str,
    stance: dict,
    fallback_urls: list[str],
) -> str | None:
    label = POSITION_KO.get(stance.get("position", ""))
    if not label:
        return None
    summary = (stance.get("summary") or "").strip() or label
    url = _source_url_from_stance(stance, fallback_urls)
    if not url:
        return None
    return f"- [{issue_title}](/issues/{issue_slug}) — **{label}**: {summary}. [출처]({url})"


def _format_events_section(events: list[dict]) -> str:
    lines: list[str] = []
    for ev in events:
        date = ev.get("date") or "날짜미상"
        text = (ev.get("event") or "").strip()
        url = ev.get("source_url")
        if not text or not url:
            continue
        lines.append(f"- {date}: {text}. [출처]({url})")
    return "\n".join(lines)


def _collect_youtube_channels(person_slugs: list[str]) -> list[str]:
    channels: list[str] = []
    seen: set[str] = set()
    for slug in person_slugs:
        data = _load_person_yaml(slug) or {}
        for ch in (data.get("sources") or {}).get("youtube_channels") or []:
            if isinstance(ch, str) and ch and ch not in seen:
                seen.add(ch)
                channels.append(ch)
    return channels


def _merge_people(
    discovered: list[dict],
    seed_people: list[str],
) -> list[dict]:
    """seed_people 우선, find_participants 결과 병합. matched_slug 기준 중복 제거."""
    by_slug: dict[str, dict] = {}
    order: list[str] = []

    for slug in seed_people:
        data = _load_person_yaml(slug) or {}
        name = data.get("name_ko", slug)
        by_slug[slug] = {
            "name_ko": name,
            "matched_slug": slug,
            "role_hint": data.get("role") or "",
            "mention_count": 1,
        }
        order.append(slug)

    for p in discovered:
        slug = p.get("matched_slug")
        if slug:
            if slug not in by_slug:
                by_slug[slug] = p
                order.append(slug)
        else:
            key = f"__name__:{p.get('name_ko', '')}"
            if key not in by_slug:
                by_slug[key] = p
                order.append(key)

    return [by_slug[k] for k in order]


# ---------------------------------------------------------------------------
# Pass A — research (deterministic)
# ---------------------------------------------------------------------------

def run_issue(slug: str, opts: argparse.Namespace) -> None:
    from limits import _get_counter

    meta = _load_issue_yaml(slug)
    if meta is None:
        logger.error("이슈 YAML 없음: %s", slug)
        return

    title = meta.get("title_ko", slug)
    keywords = meta.get("keywords") or [slug]
    seed_people = [s for s in (meta.get("seed_people") or []) if isinstance(s, str)]
    counter = _get_counter()
    counter.check_time()

    logger.info("Pass A: issue=%s", slug)

    articles = crawl_news(keywords)
    channels = _collect_youtube_channels(seed_people)
    videos: list[dict] = []
    if not getattr(opts, "no_youtube", False) and channels:
        videos = crawl_youtube(channels, keywords=keywords, no_youtube=False)

    texts: list[str] = []
    fallback_urls: list[str] = []
    for a in articles:
        if a.get("text"):
            texts.append(a["text"])
        if a.get("url"):
            fallback_urls.append(a["url"])
    for v in videos:
        if v.get("transcript"):
            texts.append(v["transcript"])
        vid = v.get("video_id")
        if vid:
            fallback_urls.append(f"https://www.youtube.com/watch?v={vid}")

    discovered = find_participants(texts, slug) if texts else []
    people = _merge_people(discovered, seed_people)

    max_stubs = getattr(opts, "max_stubs", None)
    stubs_made = 0
    resolved: list[dict] = []
    for p in people:
        counter.check_time()
        if p.get("matched_slug"):
            resolved.append(p)
            continue
        if max_stubs is not None and stubs_made >= max_stubs:
            logger.info("max_stubs 도달 — stub 생략: %s", p.get("name_ko"))
            continue
        result = register_person(
            p.get("name_ko", ""),
            role_hint=p.get("role_hint") or "",
            discovered_via_issue=slug,
        )
        if result.get("pending"):
            continue
        if result.get("slug"):
            p = {**p, "matched_slug": result["slug"]}
            if result.get("created"):
                stubs_made += 1
            resolved.append(p)

    issue_bullets: list[str] = []
    person_bullets: dict[str, list[str]] = {}

    for p in resolved:
        person_slug = p["matched_slug"]
        person_name = p.get("name_ko") or person_slug
        stance = extract_stance(
            texts,
            person_slug,
            person_name,
            slug,
            no_escalate=bool(getattr(opts, "no_escalate", False)),
        )
        issue_line = _format_issue_stance_line(person_slug, person_name, stance, fallback_urls)
        person_line = _format_person_stance_line(slug, title, stance, fallback_urls)
        if issue_line:
            issue_bullets.append(issue_line)
        if person_line:
            person_bullets.setdefault(person_slug, []).append(person_line)

    create_wiki_page("issues", slug, title, summary=meta.get("summary") or "")
    for p in resolved:
        person_slug = p["matched_slug"]
        pdata = _load_person_yaml(person_slug) or {}
        create_wiki_page(
            "people",
            person_slug,
            pdata.get("name_ko") or p.get("name_ko") or person_slug,
        )

    if issue_bullets:
        append_agent_stances("issues", slug, "\n".join(issue_bullets))
    for person_slug, bullets in person_bullets.items():
        append_agent_stances("people", person_slug, "\n".join(bullets))

    if not getattr(opts, "dry_run", False):
        commit_changes(f"update issue {slug}", dry_run=False)
    else:
        logger.info("dry-run: commit skipped issue=%s", slug)

    logger.info("완료: issue=%s", slug)


def run_person(slug: str, opts: argparse.Namespace) -> None:
    from limits import _get_counter

    meta = _load_person_yaml(slug)
    if meta is None:
        logger.error("인물 YAML 없음: %s", slug)
        return

    name = meta.get("name_ko", slug)
    sources = meta.get("sources") or {}
    keywords = sources.get("news_keywords") or [name]
    channels = [c for c in (sources.get("youtube_channels") or []) if isinstance(c, str)]
    counter = _get_counter()
    counter.check_time()

    logger.info("Pass A: person=%s", slug)

    articles = crawl_news(keywords)
    videos: list[dict] = []
    if not getattr(opts, "no_youtube", False) and channels:
        videos = crawl_youtube(channels, keywords=keywords, no_youtube=False)

    texts: list[str] = []
    for a in articles:
        if a.get("text"):
            texts.append(a["text"])
    for v in videos:
        if v.get("transcript"):
            texts.append(v["transcript"])

    events = extract_events(texts, slug, name) if texts else []
    create_wiki_page("people", slug, name)
    body = _format_events_section(events)
    if body:
        write_agent_section("people", slug, "events", body)

    if not getattr(opts, "dry_run", False):
        commit_changes(f"update person {slug}", dry_run=False)
    else:
        logger.info("dry-run: commit skipped person=%s", slug)

    logger.info("완료: person=%s", slug)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Candydate Agent")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--person", metavar="SLUG")
    group.add_argument("--issue", metavar="SLUG")
    group.add_argument("--all", action="store_true")

    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-escalate", action="store_true")
    parser.add_argument("--no-youtube", action="store_true")
    parser.add_argument("--max-stubs", type=int)
    parser.add_argument("--time-cap", type=int)
    parser.add_argument("--invalidate-cache", nargs="?", const="ALL", metavar="TOOL")

    opts = parser.parse_args()

    if opts.invalidate_cache:
        import cache

        tool = None if opts.invalidate_cache == "ALL" else opts.invalidate_cache
        n = cache.invalidate(tool)
        print(f"캐시 삭제: {n} 파일 [tool={tool or 'ALL'}]")
        return

    from limits import LimitExceeded, exit_with_partial, reset_counter
    import os

    if opts.max_stubs:
        os.environ["CANDYDATE_MAX_STUBS"] = str(opts.max_stubs)
    if opts.time_cap:
        os.environ["CANDYDATE_TIME_CAP"] = str(opts.time_cap)
    counter = reset_counter()

    try:
        if opts.person:
            run_person(opts.person, opts)
        elif opts.issue:
            run_issue(opts.issue, opts)
        elif opts.all:
            ongoing = set(_ongoing_issue_slugs())
            for f in sorted(DATA_ISSUES.glob("*.yaml")):
                if f.stem not in ongoing:
                    data = _load_issue_yaml(f.stem) or {}
                    logger.info(
                        "--all: 건너뜀 issue=%s (status=%s, ongoing 만 실행)",
                        f.stem,
                        data.get("status", "ongoing"),
                    )
                    continue
                try:
                    reset_counter()
                    run_issue(f.stem, opts)
                except LimitExceeded as e:
                    logger.warning("이슈 한도 초과, 다음으로 넘어감 [%s]: %s", f.stem, e)
        else:
            parser.print_help()
    except LimitExceeded as e:
        logger.error("한도 초과: %s", e)
        exit_with_partial(counter, str(e))


if __name__ == "__main__":
    main()
