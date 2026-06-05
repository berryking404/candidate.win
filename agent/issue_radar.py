"""Candidate.win 신규 위키 이슈 후보 발굴 레이더.

흐름:
  1. Google Trends / Google News RSS / 공식 feed 에서 seed keyword 발굴
  2. Naver News API 로 기사 확장
  3. 기존 data/issues 와 중복 검사
  4. 점수화 및 Markdown/JSON 리포트 생성
  5. 선택적으로 Linear 이슈 생성
  6. Eric 댓글 승인("승인: 1,3" 또는 "approve: 1")을 SSoT YAML/wiki shell 로 반영

환경변수:
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET       Naver News API
  LINEAR_API_KEY                            Linear GraphQL API token
  ISSUE_RADAR_LINEAR_TEAM_ID                기본값: Berryking team id
  ISSUE_RADAR_LINEAR_PROJECT_ID             기본값: candidate.win project id
  ISSUE_RADAR_LINEAR_STATE_ID               선택: 생성될 승인대기 이슈 상태
  ISSUE_RADAR_OFFICIAL_FEEDS                JSON list 또는 newline/comma separated RSS URLs
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import html
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import feedparser
import httpx
import yaml
from dotenv import load_dotenv

try:
    from crawlers.naver_news import crawl as crawl_naver_news
except Exception:  # pragma: no cover - tests may import as package
    from agent.crawlers.naver_news import crawl as crawl_naver_news

load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
DATA_ISSUES = ROOT / "data" / "issues"
WIKI_ISSUES = ROOT / "wiki" / "content" / "issues"
CACHE_DIR = ROOT / "agent" / ".cache" / "issue_candidates"
REPORT_DIR = ROOT / "agent" / "reports" / "issue_candidates"
LINEAR_API = "https://api.linear.app/graphql"
DEFAULT_TEAM_ID = "8e27f9c8-aaa3-47f4-8d58-81dc753bd453"
DEFAULT_PROJECT_ID = "05950f61-d9b6-4ded-a0a5-65a9c104bc69"

BROAD_QUERIES = [
    "국회 논란", "정부 대응 논란", "정책 논쟁", "특검 의혹", "해임건의안", "탄핵소추안",
    "선거 공천 갈등", "후보 단일화", "선관위 논란", "투표소 논란",
    "개인정보 유출", "노사 분쟁", "부동산 대책", "전세사기", "지방소멸", "청년 일자리",
    "외교 갈등", "안보 논쟁", "전작권", "관세", "공급망", "한미", "중국", "북한",
]
POLITICAL_TERMS = [
    "국회", "대통령", "정부", "장관", "정당", "국민의힘", "민주당", "조국혁신당", "개혁신당",
    "선거", "공천", "후보", "선관위", "법안", "개정안", "특검", "탄핵", "청문회", "상임위",
    "검찰", "경찰", "감사원", "법원", "헌재", "외교", "안보", "예산", "규제", "노동", "부동산",
]
NEGATIVE_TERMS = ["연예", "아이돌", "드라마", "영화", "스포츠", "야구", "축구", "게임", "맛집"]
GENERIC_KEYWORDS = {"국회", "정부", "민주당", "국민의힘", "대통령", "국회의장", "정부의", "정책", "논란"}
ISSUE_CUES = [
    "논란", "의혹", "사태", "갈등", "반발", "비판", "공방", "쟁점", "국정조사", "특검", "탄핵",
    "법안", "개정", "청문회", "선관위", "공천", "파업", "유출", "사고", "대책", "대응", "조사",
]
STANCE_ACTOR_TERMS = ["국민의힘", "더불어민주당", "민주당", "조국혁신당", "개혁신당", "대통령실", "정부", "국회", "장관", "의원", "대표", "원내대표", "대변인"]


@dataclasses.dataclass
class Seed:
    keyword: str
    source: str
    title: str = ""
    url: str = ""
    published: str = ""


@dataclasses.dataclass
class Candidate:
    title: str
    keyword: str
    slug: str
    score: int
    recommendation: str
    merge_target: str | None
    signals: dict[str, Any]
    articles: list[dict[str, Any]]
    official_signals: list[dict[str, Any]]
    duplicate_matches: list[dict[str, Any]]


def normalize_text(s: str) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", "", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def significant_keyword(text: str) -> bool:
    if not text or any(t in text for t in NEGATIVE_TERMS):
        return False
    return any(t in text for t in POLITICAL_TERMS)


def issue_like(text: str) -> bool:
    """단순 정치 기사보다 위키 '이슈' 후보에 가까운 제목/키워드인지 판정."""
    return significant_keyword(text) and any(cue in text for cue in ISSUE_CUES)


def slugify_ko(text: str) -> str:
    # ASCII slug가 필요한 Hugo 경로용: 한국어 제목은 안정적 hash suffix와 함께 romanization 없이 topic-YYYY-hash 사용
    year = datetime.now(timezone.utc).year
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    base_terms = []
    mapping = {
        "국회": "assembly", "정부": "government", "선거": "election", "특검": "special-counsel",
        "탄핵": "impeachment", "개인정보": "privacy", "부동산": "housing", "노동": "labor",
        "외교": "diplomacy", "안보": "security", "청년": "youth", "공천": "nomination",
    }
    for ko, en in mapping.items():
        if ko in text:
            base_terms.append(en)
    base = "-".join(base_terms[:3]) or "issue"
    return f"{base}-{year}-{digest}"


def fetch_rss(url: str, *, timeout: int = 20) -> list[dict[str, Any]]:
    try:
        parsed = feedparser.parse(url, request_headers={"User-Agent": "candidate-win-issue-radar/1.0"})
        return list(parsed.entries or [])
    except Exception as exc:
        logger.warning("RSS 수집 실패: %s (%s)", url, exc)
        return []


def collect_google_trends(limit: int = 30) -> list[Seed]:
    url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KR"
    seeds: list[Seed] = []
    for e in fetch_rss(url)[:limit]:
        title = normalize_text(e.get("title", ""))
        if issue_like(title):
            seeds.append(Seed(keyword=title, source="google_trends", title=title, url=e.get("link", ""), published=e.get("published", "")))
    return seeds


def collect_google_news(window_days: int = 1, queries: list[str] | None = None, per_query: int = 10) -> list[Seed]:
    seeds: list[Seed] = []
    for q in queries or BROAD_QUERIES:
        url = f"https://news.google.com/rss/search?q={quote_plus(q + ' when:' + str(window_days) + 'd')}&hl=ko&gl=KR&ceid=KR:ko"
        for e in fetch_rss(url)[:per_query]:
            title = normalize_text(e.get("title", ""))
            if not issue_like(title):
                continue
            seeds.append(Seed(keyword=derive_keyword(title, q), source="google_news", title=title, url=e.get("link", ""), published=e.get("published", "")))
    return seeds


def official_feed_urls() -> list[str]:
    raw = os.getenv("ISSUE_RADAR_OFFICIAL_FEEDS", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if str(x).startswith("http")]
    except Exception:
        pass
    parts = re.split(r"[\n,]+", raw)
    return [p.strip() for p in parts if p.strip().startswith("http")]


def collect_official_feeds(window_days: int = 3) -> list[Seed]:
    seeds: list[Seed] = []
    for url in official_feed_urls():
        for e in fetch_rss(url)[:30]:
            title = normalize_text(e.get("title", ""))
            if issue_like(title):
                seeds.append(Seed(keyword=derive_keyword(title, title), source="official_feed", title=title, url=e.get("link", ""), published=e.get("published", "")))
    return seeds


def derive_keyword(title: str, fallback: str) -> str:
    # Google News 제목은 "제목 - 매체" 꼴이다. 너무 넓은 단어(국회/정부/민주당)만 검색하면
    # Naver 확장 단계가 잡음 기사로 오염되므로, 이슈 cue가 있는 제목 phrase를 그대로 seed로 쓴다.
    title = re.sub(r"\s+-\s+[^-]{2,20}$", "", title)
    quoted = re.findall(r"[‘'\"“”]([^‘'\"“”]{2,30})[’'\"“”]", title)
    if quoted and issue_like(quoted[0]) and re.sub(r"[^가-힣A-Za-z0-9]", "", quoted[0].lower()) not in GENERIC_KEYWORDS:
        return quoted[0]
    cleaned = normalize_text(title)
    if issue_like(cleaned):
        return cleaned[:70]
    return fallback[:50]


def dedupe_seeds(seeds: list[Seed], max_keywords: int = 40) -> list[Seed]:
    by_kw: dict[str, Seed] = {}
    for s in seeds:
        kw = normalize_text(s.keyword)
        compact = re.sub(r"[^가-힣A-Za-z0-9]", "", kw.lower())
        if len(kw) < 2 or compact in GENERIC_KEYWORDS or not issue_like(kw + " " + s.title):
            continue
        key = compact[:50]
        if key not in by_kw:
            by_kw[key] = dataclasses.replace(s, keyword=kw)
    return list(by_kw.values())[:max_keywords]


def collect_seeds(window_days: int, max_keywords: int) -> list[Seed]:
    seeds = []
    seeds.extend(collect_google_trends())
    seeds.extend(collect_google_news(window_days=window_days))
    seeds.extend(collect_official_feeds(window_days=window_days))
    if not seeds:
        seeds = [Seed(keyword=q, source="fallback_query") for q in BROAD_QUERIES]
    return dedupe_seeds(seeds, max_keywords=max_keywords)


def load_existing_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for path in sorted(DATA_ISSUES.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        issues.append({
            "slug": data.get("slug") or path.stem,
            "title": data.get("title_ko") or data.get("title") or path.stem,
            "summary": data.get("summary") or "",
            "keywords": data.get("keywords") or [],
            "status": data.get("status") or "",
        })
    return issues


def similarity(a: str, b: str) -> float:
    aset = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", (a or "").lower()))
    bset = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", (b or "").lower()))
    if not aset or not bset:
        return 0.0
    return len(aset & bset) / len(aset | bset)


def find_duplicates(keyword: str, title: str, existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    text = f"{keyword} {title}"
    for issue in existing:
        corpus = " ".join([issue["title"], issue["summary"], " ".join(map(str, issue["keywords"]))])
        sim = similarity(text, corpus)
        if sim >= 0.18 or any(str(k) and str(k) in text for k in issue.get("keywords", [])):
            matches.append({"slug": issue["slug"], "title": issue["title"], "similarity": round(sim, 3)})
    return sorted(matches, key=lambda x: x["similarity"], reverse=True)[:3]


def expand_with_naver(seeds: list[Seed], *, window_days: int, max_per_keyword: int) -> dict[str, list[dict[str, Any]]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).date().isoformat()
    result: dict[str, list[dict[str, Any]]] = {}
    for s in seeds:
        articles = crawl_naver_news([s.keyword], max_per_keyword=max_per_keyword, date_from=cutoff, fetch_full_text=False)
        result[s.keyword] = [dict(a) for a in articles]
    return result


def cluster_candidates(seeds: list[Seed], naver_by_keyword: dict[str, list[dict[str, Any]]], existing: list[dict[str, Any]]) -> list[Candidate]:
    official_by_kw = defaultdict(list)
    for s in seeds:
        if s.source == "official_feed":
            official_by_kw[s.keyword].append(dataclasses.asdict(s))

    candidates: list[Candidate] = []
    for s in seeds:
        articles = naver_by_keyword.get(s.keyword, [])
        source_counter = Counter(domain_from_url(a.get("url", "")) for a in articles)
        titles = [a.get("title", "") for a in articles]
        title = choose_candidate_title(s.keyword, titles, s.title)
        duplicate_matches = find_duplicates(s.keyword, title, existing)
        actors = sorted({term for term in STANCE_ACTOR_TERMS if term in " ".join(titles + [s.title, s.keyword])})
        official = official_by_kw.get(s.keyword, [])
        score, rec, merge_target, breakdown = score_candidate(
            keyword=s.keyword,
            title=title,
            articles=articles,
            outlet_count=len([d for d in source_counter if d]),
            actors=actors,
            official_count=len(official) + (1 if s.source == "official_feed" else 0),
            duplicate_matches=duplicate_matches,
        )
        if score <= 0 and not articles:
            continue
        candidates.append(Candidate(
            title=title,
            keyword=s.keyword,
            slug=slugify_ko(title),
            score=score,
            recommendation=rec,
            merge_target=merge_target,
            signals={
                "seed_source": s.source,
                "news_count": len(articles),
                "outlet_count": len([d for d in source_counter if d]),
                "top_outlets": source_counter.most_common(5),
                "stance_actor_terms": actors,
                "breakdown": breakdown,
            },
            articles=articles[:8],
            official_signals=official[:5],
            duplicate_matches=duplicate_matches,
        ))
    # 같은 slug/keyword 중복 정리
    by_key: dict[str, Candidate] = {}
    for c in sorted(candidates, key=lambda x: x.score, reverse=True):
        key = re.sub(r"[^가-힣A-Za-z0-9]", "", c.keyword.lower())[:30]
        if key not in by_key:
            by_key[key] = c
    return sorted(by_key.values(), key=lambda x: x.score, reverse=True)


def domain_from_url(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1) if m else ""


def choose_candidate_title(keyword: str, titles: list[str], seed_title: str) -> str:
    candidates = [normalize_text(t) for t in titles if t]
    if seed_title:
        candidates.append(normalize_text(re.sub(r"\s+-\s+[^-]{2,20}$", "", seed_title)))
    if candidates:
        ranked = sorted(candidates, key=lambda x: (-similarity(keyword, x), len(x), x))
        return ranked[0][:80]
    return seed_title or keyword


def score_candidate(*, keyword: str, title: str, articles: list[dict[str, Any]], outlet_count: int, actors: list[str], official_count: int, duplicate_matches: list[dict[str, Any]]) -> tuple[int, str, str | None, dict[str, int]]:
    news_volume = 2 if len(articles) >= 3 else (1 if articles else 0)
    outlet_diversity = 2 if outlet_count >= 3 else (1 if outlet_count >= 2 else 0)
    official_signal = 2 if official_count else 0
    stance_actors = 3 if len(actors) >= 2 else (1 if actors else 0)
    public_relevance = 2 if significant_keyword(keyword + " " + title) else 0
    duplicate_penalty = -2 if duplicate_matches else 0
    weak_penalty = -3 if any(t in keyword + title for t in NEGATIVE_TERMS) else 0
    score = news_volume + outlet_diversity + official_signal + stance_actors + public_relevance + duplicate_penalty + weak_penalty
    merge_target = duplicate_matches[0]["slug"] if duplicate_matches and score >= 4 else None
    if score >= 7 and not duplicate_matches:
        rec = "독립 이슈"
    elif score >= 4 and duplicate_matches:
        rec = "기존 이슈 병합/업데이트"
    elif score >= 4:
        rec = "보류 후 추가 확인"
    else:
        rec = "폐기/관찰"
    return score, rec, merge_target, {
        "news_volume": news_volume,
        "outlet_diversity": outlet_diversity,
        "official_signal": official_signal,
        "stance_actors": stance_actors,
        "public_relevance": public_relevance,
        "duplicate_penalty": duplicate_penalty,
        "weak_penalty": weak_penalty,
    }


def render_report(candidates: list[Candidate], *, window_days: int) -> str:
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = [
        "[이슈 후보 발굴 리포트]",
        "",
        f"수집 범위: 최근 {window_days}일",
        f"생성 시각: {now}",
        "",
        "Eric 승인 방법: 이 Linear 이슈에 댓글로 `승인: 1,3` / `반려: 2`처럼 남기면 다음 적용 작업에서 독립 이슈 후보의 SSoT를 생성합니다. 병합 권고 후보는 댓글 확인 후 수동 병합 대상으로 보고합니다.",
        "",
    ]
    if not candidates:
        lines.append("후보 없음")
        return "\n".join(lines) + "\n"
    for i, c in enumerate(candidates, 1):
        lines.extend([
            f"{i}. 후보: {c.title}",
            f"   점수: {c.score}",
            f"   권고: {c.recommendation}" + (f" → {c.merge_target}" if c.merge_target else ""),
            f"   키워드: {c.keyword}",
            "   근거:",
            f"   - 기사 {c.signals['news_count']}건 / 매체 {c.signals['outlet_count']}곳 / 발언 주체 신호 {', '.join(c.signals['stance_actor_terms']) or '없음'}",
        ])
        if c.duplicate_matches:
            lines.append("   - 기존 이슈 유사: " + ", ".join(f"{m['slug']}({m['similarity']})" for m in c.duplicate_matches))
        for a in c.articles[:3]:
            lines.append(f"   - {a.get('title','')[:90]} — {a.get('url','')}")
        lines.append("")
    return "\n".join(lines)


def save_outputs(candidates: list[Candidate], report: str, date_key: str | None = None) -> tuple[Path, Path]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    date_key = date_key or datetime.now(timezone.utc).date().isoformat()
    json_path = CACHE_DIR / f"{date_key}.json"
    md_path = REPORT_DIR / f"{date_key}.md"
    payload = {
        "date": date_key,
        "linear_issue_id": None,
        "linear_issue_identifier": None,
        "candidates": [dataclasses.asdict(c) for c in candidates],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(report, encoding="utf-8")
    return json_path, md_path


def linear_headers() -> dict[str, str]:
    key = os.getenv("LINEAR_API_KEY", "")
    if not key:
        raise RuntimeError("LINEAR_API_KEY 미설정")
    return {"Authorization": key, "Content-Type": "application/json"}


def linear_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=30) as client:
        r = client.post(LINEAR_API, headers=linear_headers(), json={"query": query, "variables": variables or {}})
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            raise RuntimeError(data["errors"])
        return data["data"]


def create_linear_report(report: str, json_path: Path) -> dict[str, Any]:
    team_id = os.getenv("ISSUE_RADAR_LINEAR_TEAM_ID", DEFAULT_TEAM_ID)
    project_id = os.getenv("ISSUE_RADAR_LINEAR_PROJECT_ID", DEFAULT_PROJECT_ID)
    state_id = os.getenv("ISSUE_RADAR_LINEAR_STATE_ID")
    title = f"[candidate.win] 이슈 후보 발굴 리포트 {datetime.now(timezone.utc).date().isoformat()}"
    mutation = """
    mutation CreateIssue($input: IssueCreateInput!) {
      issueCreate(input: $input) { success issue { id identifier url title } }
    }
    """
    input_obj: dict[str, Any] = {"teamId": team_id, "projectId": project_id, "title": title, "description": report}
    if state_id:
        input_obj["stateId"] = state_id
    data = linear_graphql(mutation, {"input": input_obj})["issueCreate"]
    issue = data["issue"]
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["linear_issue_id"] = issue["id"]
    payload["linear_issue_identifier"] = issue["identifier"]
    payload["linear_issue_url"] = issue["url"]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return issue


def run_radar(args: argparse.Namespace) -> int:
    seeds = collect_seeds(args.window_days, args.max_keywords)
    naver_by_keyword = expand_with_naver(seeds, window_days=args.window_days, max_per_keyword=args.max_per_keyword) if not args.no_naver else {s.keyword: [] for s in seeds}
    candidates = [c for c in cluster_candidates(seeds, naver_by_keyword, load_existing_issues()) if c.score >= 4][: args.max_candidates]
    report = render_report(candidates, window_days=args.window_days)
    json_path, md_path = save_outputs(candidates, report)
    issue = None
    if args.linear:
        issue = create_linear_report(report, json_path)
    print(report)
    print(f"\n저장: {json_path}\n리포트: {md_path}")
    if issue:
        print(f"Linear: {issue['identifier']} {issue['url']}")
    return 0


def parse_approvals(text: str) -> dict[int, str]:
    approvals: dict[int, str] = {}
    for m in re.finditer(r"(?:승인|approve)\s*[:：]?\s*([0-9,\s]+)", text, re.I):
        for n in re.findall(r"\d+", m.group(1)):
            approvals[int(n)] = "approve"
    for m in re.finditer(r"(?:반려|reject|폐기)\s*[:：]?\s*([0-9,\s]+)", text, re.I):
        for n in re.findall(r"\d+", m.group(1)):
            approvals[int(n)] = "reject"
    return approvals


def fetch_linear_comments(issue_id: str) -> list[dict[str, Any]]:
    query = """
    query IssueComments($id: String!) {
      issue(id: $id) { comments(first: 50) { nodes { id body createdAt user { name email } } } }
    }
    """
    data = linear_graphql(query, {"id": issue_id})
    issue = data.get("issue") or {}
    return issue.get("comments", {}).get("nodes", [])


def apply_approvals(args: argparse.Namespace) -> int:
    path = Path(args.cache_json) if args.cache_json else latest_cache_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    comments = fetch_linear_comments(payload["linear_issue_id"]) if payload.get("linear_issue_id") else []
    approvals: dict[int, str] = {}
    for c in comments:
        approvals.update(parse_approvals(c.get("body", "")))
    if not approvals:
        print("승인/반려 댓글 없음")
        return 0
    created = []
    rejected = []
    for idx, action in approvals.items():
        if idx < 1 or idx > len(payload.get("candidates", [])):
            continue
        cand = payload["candidates"][idx - 1]
        if action == "approve":
            if cand.get("recommendation") == "독립 이슈":
                created.append(create_issue_shell(cand))
            else:
                created.append(f"병합/보류 권고 후보 승인 확인: {idx} {cand['title']} (수동 병합 필요)")
        else:
            rejected.append(f"{idx} {cand['title']}")
    print("생성/처리:\n" + "\n".join(map(str, created)) if created else "생성 없음")
    if rejected:
        print("반려:\n" + "\n".join(rejected))
    return 0


def latest_cache_file() -> Path:
    files = sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("issue candidate cache 없음")
    return files[0]


def create_issue_shell(cand: dict[str, Any]) -> str:
    slug = cand["slug"]
    yaml_path = DATA_ISSUES / f"{slug}.yaml"
    md_path = WIKI_ISSUES / f"{slug}.md"
    if yaml_path.exists() or md_path.exists():
        return f"이미 존재: {slug}"
    today = datetime.now(timezone.utc).date().isoformat()
    source_items = []
    for a in cand.get("articles", [])[:5]:
        source_items.append({"url": a.get("url", ""), "title": a.get("title", ""), "date": (a.get("date") or today)[:10]})
    data = {
        "slug": slug,
        "title_ko": cand["title"],
        "title_en": "",
        "category": "politics",
        "status": "ongoing",
        "started_at": today,
        "summary": f"{cand['title']} 관련 정치·공공 쟁점. Eric 승인 후 issue-radar가 생성한 초안이므로 stance 기준과 요약 보강 필요.",
        "keywords": sorted({cand.get("keyword", cand["title"]), cand["title"]}),
        "stances": {
            "support": "이 쟁점의 추진·찬성·책임 추궁 등 주요 요구를 지지하는 입장",
            "oppose": "이 쟁점의 추진에 반대하거나 과도한 정치 공세·규제라고 보는 입장",
        },
        "seed_people": [],
        "sources": source_items,
    }
    yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    front_summary = data["summary"].replace("\n", " ")
    md = f"""---
title: {cand['title']}
slug: {slug}
category: politics
status: ongoing
summary: {front_summary}
---

## 인물별 입장

<!-- agent:stances -->
<!-- /agent:stances -->
"""
    md_path.write_text(md, encoding="utf-8")
    return f"생성: {slug}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Candidate.win 이슈 후보 발굴 레이더")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--window-days", type=int, default=1)
    r.add_argument("--max-keywords", type=int, default=30)
    r.add_argument("--max-per-keyword", type=int, default=20)
    r.add_argument("--max-candidates", type=int, default=12)
    r.add_argument("--no-naver", action="store_true")
    r.add_argument("--linear", action="store_true", help="Linear 승인 요청 이슈 생성")
    r.set_defaults(func=run_radar)
    a = sub.add_parser("apply-approvals")
    a.add_argument("--cache-json")
    a.set_defaults(func=apply_approvals)
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
