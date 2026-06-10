"""Candydate Agent 진입점.

사용법:
    python deep_agent.py --person lee-jae-myung
    python deep_agent.py --issue real-estate-tax-2026   # status 무관
    python deep_agent.py --all   # data/issues/*.yaml 중 status: ongoing 만
    python deep_agent.py --pass-d --issue real-estate-tax-2026
    python deep_agent.py --batch-submit
    python deep_agent.py --batch-apply

플래그:
    --dry-run        LLM 호출 결과를 stdout 에만 출력, 커밋 없음
    --no-escalate    Tier 2 에스컬레이션 차단
    --no-batch       escalation 을 동기 Tier 2 로 처리 (Batch -50% 포기)
    --no-youtube     YouTube 호출 전체 차단
    --max-stubs N    1회 실행당 stub 생성 상한 (기본 5)
    --cost-cap N     Tier 2 비용 상한 USD (기본 1.0)
    --max-calls N    Tier 2 호출 횟수 상한 (기본 50)
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


def _active_batch_file() -> Path:
    """현재 agent 디렉터리 기준 active batch sidecar 경로."""
    return Path(__file__).parent / ".cache" / "batch" / "active.json"


def build_agent(no_batch: bool = False, no_escalate: bool = False, no_youtube: bool = False):
    from deepagents import create_deep_agent
    from prompts import SYSTEM_PROMPT
    from tools import (
        crawl_news, crawl_youtube,
        find_participants, register_person,
        extract_events, extract_stance,
        create_wiki_page,
        read_agent_section, write_agent_section, append_agent_stances,
        commit_changes,
    )

    # 플래그를 도구에 바인딩하는 클로저 래퍼
    def _crawl_youtube(channel_ids: list[str], keywords: list[str] | None = None) -> list[dict]:
        """YouTube 채널 RSS 에서 자막을 수집한다."""
        return crawl_youtube(channel_ids, keywords=keywords, no_youtube=no_youtube)

    def _extract_stance(texts: list[str], person_slug: str, person_name: str, issue_slug: str) -> dict:
        """텍스트에서 인물의 이슈 입장을 추출한다."""
        return extract_stance(texts, person_slug, person_name, issue_slug,
                              no_batch=no_batch, no_escalate=no_escalate)

    return create_deep_agent(
        model="openai:gpt-5.4-mini",
        tools=[
            crawl_news,
            _crawl_youtube,
            find_participants,
            register_person,
            extract_events,
            _extract_stance,
            create_wiki_page,
            read_agent_section,
            write_agent_section,
            append_agent_stances,
            commit_changes,
        ],
        system_prompt=SYSTEM_PROMPT,
    )


# ---------------------------------------------------------------------------
# Pass A — research
# ---------------------------------------------------------------------------

def _person_context(slug: str) -> str:
    """data/people/{slug}.yaml 에서 이름·키워드를 읽어 쿼리 컨텍스트 문자열로 변환."""
    path = DATA_PEOPLE / f"{slug}.yaml"
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return ""
    name = data.get("name_ko", slug)
    keywords = (data.get("sources") or {}).get("news_keywords", [name])
    return f"한국어 이름: {name}, 검색 키워드: {keywords}"


def _load_issue_yaml(slug: str) -> dict | None:
    """data/issues/{slug}.yaml 을 읽는다. 파일 없음·읽기·YAML 파싱 실패 시 None."""
    path = DATA_ISSUES / f"{slug}.yaml"
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return None


def _issue_context(slug: str) -> str:
    """data/issues/{slug}.yaml 에서 제목·키워드·seed_people을 쿼리 컨텍스트로 변환."""
    data = _load_issue_yaml(slug)
    if data is None:
        return ""
    title = data.get("title_ko", slug)
    keywords = data.get("keywords", [slug])
    seed_people = data.get("seed_people") or []
    seed_hint = ""
    if seed_people:
        seed_hint = f", 우선 확인할 seed_people: {seed_people}"
    return f"이슈 제목: {title}, 검색 키워드(한국어): {keywords}{seed_hint}"


def _ongoing_issue_slugs() -> list[str]:
    """--all 과 동일한 기준으로 status: ongoing 이슈 slug 목록을 반환한다."""
    slugs: list[str] = []
    for f in sorted(DATA_ISSUES.glob("*.yaml")):
        data = _load_issue_yaml(f.stem) or {}
        if data.get("status", "ongoing") == "ongoing":
            slugs.append(f.stem)
    return slugs


def _active_batch_issue_slugs() -> list[str]:
    """active batch sidecar에서 apply 대상 issue slug 목록을 읽는다."""
    import json

    active = _active_batch_file()
    try:
        data = json.loads(active.read_text(encoding="utf-8"))
    except Exception:
        return []
    issue_slugs = data.get("issue_slugs", [])
    if not isinstance(issue_slugs, list):
        return []
    return sorted({slug for slug in issue_slugs if isinstance(slug, str) and slug})


def run_person(slug: str, opts: argparse.Namespace) -> None:
    agent = build_agent(no_batch=opts.no_batch, no_escalate=opts.no_escalate, no_youtube=opts.no_youtube)
    ctx = _person_context(slug)
    query = f"research person {slug}. {ctx} extract events and update wiki page. dry_run={opts.dry_run}"
    logger.info("Pass A: person=%s", slug)
    agent.invoke({"messages": [{"role": "user", "content": query}]})
    logger.info("완료: person=%s", slug)


def run_issue(slug: str, opts: argparse.Namespace) -> None:
    agent = build_agent(no_batch=opts.no_batch, no_escalate=opts.no_escalate, no_youtube=opts.no_youtube)
    ctx = _issue_context(slug)
    query = (
        f"research issue {slug}. {ctx} "
        f"crawl_news 에는 위 한국어 키워드를 사용하라. "
        f"find all participants, extract stances, update wiki pages. dry_run={opts.dry_run}"
    )
    logger.info("Pass A: issue=%s", slug)
    agent.invoke({"messages": [{"role": "user", "content": query}]})
    logger.info("완료: issue=%s", slug)


# ---------------------------------------------------------------------------
# Pass D — apply (batch 결과 적재 후)
# ---------------------------------------------------------------------------

def run_apply(slug: str, opts: argparse.Namespace) -> None:
    agent = build_agent(no_batch=True, no_escalate=opts.no_escalate)  # batch 결과는 이미 캐시에
    ctx = _issue_context(slug)
    query = f"apply cached stances for issue {slug}. {ctx} update wiki pages. dry_run={opts.dry_run}"
    logger.info("Pass D: issue=%s", slug)
    agent.invoke({"messages": [{"role": "user", "content": query}]})
    logger.info("Pass D 완료: issue=%s", slug)


def run_batch_apply_status(opts: argparse.Namespace) -> str:
    """Pass C 결과를 캐시에 적재한 뒤 Pass D를 실제 wiki에 적용한다.

    Returns:
        "applied": batch 완료 및 apply 실행.
        "pending": active batch가 아직 완료되지 않았거나 실패함.
        "no_active": 적용할 active batch가 없음.
    """
    from publishers.batch_submitter import poll_and_ingest
    from limits import reset_counter, LimitExceeded

    if not _active_batch_file().exists():
        logger.info("Batch active 파일 없음 — 적용할 항목 없음")
        return "no_active"

    issue_slugs = _active_batch_issue_slugs()
    done = poll_and_ingest()
    if not done:
        return "pending"

    if not issue_slugs:
        issue_slugs = _ongoing_issue_slugs()
        logger.warning("Batch active.json에 issue_slugs 없음 — ongoing 전체 Pass D fallback: %d개", len(issue_slugs))

    for slug in issue_slugs:
        try:
            reset_counter()
            run_apply(slug, opts)
        except LimitExceeded as e:
            logger.warning("Pass D 한도 초과, 다음 이슈로 넘어감 [%s]: %s", slug, e)
    return "applied"


def run_batch_apply(opts: argparse.Namespace) -> bool:
    """Backward-compatible boolean wrapper for tests/callers."""
    return run_batch_apply_status(opts) == "applied"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Candydate Agent")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--person", metavar="SLUG")
    group.add_argument("--issue", metavar="SLUG")
    group.add_argument("--all", action="store_true")
    group.add_argument("--batch-submit", action="store_true", help="Pass B: Batch 제출")
    group.add_argument("--batch-apply", action="store_true", help="Pass C+D: Batch 결과 적재 후 적용")
    parser.add_argument("--pass-d", action="store_true", help="Pass D 실행 (--issue 와 함께)")

    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-escalate", action="store_true")
    parser.add_argument("--no-batch", action="store_true")
    parser.add_argument("--no-youtube", action="store_true")
    parser.add_argument("--max-stubs", type=int)
    parser.add_argument("--cost-cap", type=float)
    parser.add_argument("--max-calls", type=int)
    parser.add_argument("--time-cap", type=int)
    parser.add_argument("--invalidate-cache", nargs="?", const="ALL", metavar="TOOL")

    opts = parser.parse_args()

    # 캐시 삭제
    if opts.invalidate_cache:
        import cache
        tool = None if opts.invalidate_cache == "ALL" else opts.invalidate_cache
        n = cache.invalidate(tool)
        print(f"캐시 삭제: {n} 파일 [tool={tool or 'ALL'}]")
        return

    # Circuit breaker 초기화
    from limits import reset_counter, RunLimits, LimitExceeded, exit_with_partial
    import os
    if opts.max_stubs:
        os.environ["CANDYDATE_MAX_STUBS"] = str(opts.max_stubs)
    if opts.cost_cap:
        os.environ["CANDYDATE_COST_CAP"] = str(opts.cost_cap)
    if opts.max_calls:
        os.environ["CANDYDATE_MAX_CALLS"] = str(opts.max_calls)
    if opts.time_cap:
        os.environ["CANDYDATE_TIME_CAP"] = str(opts.time_cap)
    counter = reset_counter()

    try:
        if opts.batch_submit:
            from publishers.batch_submitter import submit
            batch_id = submit()
            print(f"Batch 제출: {batch_id}")

        elif opts.batch_apply:
            status = run_batch_apply_status(opts)
            if status == "no_active":
                logger.info("Batch active 없음 — Pass C+D 할 일 없음")
                sys.exit(10)
            if status != "applied":
                logger.warning("Batch 아직 완료되지 않음")
                sys.exit(1)

        elif opts.person:
            run_person(opts.person, opts)

        elif opts.issue:
            if opts.pass_d:
                run_apply(opts.issue, opts)
            else:
                run_issue(opts.issue, opts)

        elif opts.all:
            ongoing = set(_ongoing_issue_slugs())
            for f in sorted(DATA_ISSUES.glob("*.yaml")):
                if f.stem not in ongoing:
                    data = _load_issue_yaml(f.stem) or {}
                    logger.info("--all: 건너뜀 issue=%s (status=%s, ongoing 만 실행)", f.stem, data.get("status", "ongoing"))
                    continue
                try:
                    reset_counter()   # 이슈마다 stub·시간 카운터 초기화
                    run_issue(f.stem, opts)
                except LimitExceeded as e:
                    logger.warning("이슈 한도 초과, 다음으로 넘어감 [%s]: %s", f.stem, e)

        else:
            parser.print_help()

    except LimitExceeded as e:
        logger.error("한도 초과: %s", e)
        exit_with_partial(counter, str(e))

    finally:
        from models import dump_cost_log
        dump_cost_log()


if __name__ == "__main__":
    main()
