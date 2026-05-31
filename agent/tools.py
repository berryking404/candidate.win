"""DeepAgents 커스텀 도구 함수 모음.

각 함수는 docstring + 타입 힌트를 갖추고 create_deep_agent(tools=[...]) 에 전달된다.
빌트인(read_file / edit_file)은 wiki 경로에 사용하지 않는다.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

WIKI_ROOT = Path(__file__).parent.parent / "wiki" / "content"
DATA_PEOPLE = Path(__file__).parent.parent / "data" / "people"
DATA_ISSUES = Path(__file__).parent.parent / "data" / "issues"

SECTION_RE = re.compile(
    r"<!--\s*agent:(?P<id>[\w\-]+)\s*-->(?P<body>.*?)<!--\s*/agent:(?P=id)\s*-->",
    re.DOTALL,
)


def _read_wiki_text(path: Path) -> str:
    """wiki 마크다운을 UTF-8로 읽는다. 손상 시 경로·위치를 포함한 오류를 낸다."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise UnicodeDecodeError(
            e.encoding,
            e.object,
            e.start,
            e.end,
            f"{path}: position {e.start} — UTF-8이 아닌 바이트. "
            "파일을 수동 복구한 뒤 에이전트를 재실행하세요.",
        ) from e


def _write_wiki_text(path: Path, text: str) -> None:
    """wiki 마크다운을 원자적으로 저장한다 (부분 쓰기로 인한 손상 방지)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text.encode("utf-8")
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    ) as f:
        f.write(text)
        tmp = Path(f.name)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 크롤링
# ---------------------------------------------------------------------------

def crawl_news(keywords: list[str], date_from: str | None = None) -> list[dict]:
    """Naver News 에서 키워드로 기사 목록을 수집한다.

    Args:
        keywords: 검색어 목록.
        date_from: 수집 시작 날짜 (YYYY-MM-DD). 없으면 최신 30건.

    Returns:
        [{url, title, text, date, source}] 목록.
    """
    from crawlers.naver_news import crawl
    from processors.dedup import dedup

    articles = crawl(keywords, date_from=date_from)
    result = dedup(articles, source="naver")
    return result["new"]


def crawl_youtube(
    channel_ids: list[str],
    keywords: list[str] | None = None,
    no_youtube: bool = False,
) -> list[dict]:
    """YouTube 채널 RSS 에서 자막을 수집한다.

    Args:
        channel_ids: YouTube 채널 ID 목록 (UC...).
        keywords: 제목/자막 필터 키워드. 없으면 전체.
        no_youtube: True 면 YouTube 호출 차단.

    Returns:
        [{video_id, title, transcript, channel_id, published}] 목록.
    """
    from crawlers.youtube_transcript import crawl_channels
    from processors.dedup import dedup

    videos = crawl_channels(channel_ids, keywords=keywords, no_youtube=no_youtube)
    result = dedup(videos, source="youtube")
    return result["new"]


# ---------------------------------------------------------------------------
# 인물 발견·등록
# ---------------------------------------------------------------------------

def find_participants(texts: list[str], issue_slug: str) -> list[dict]:
    """텍스트 목록에서 이슈 관련 발언자 후보를 추출한다.

    Args:
        texts: 기사 본문 또는 자막 텍스트 목록.
        issue_slug: 이슈 식별자 (캐시 키용).

    Returns:
        [{name_ko, role_hint, mention_count, sample_quote, matched_slug}]
    """
    from processors.chunker import chunk_many
    from processors.participant_finder import find_participants as _find

    chunks = chunk_many(texts, keywords=_load_issue_keywords(issue_slug))
    if not chunks:
        return []
    return _find(chunks, issue_slug)


def register_person(
    name_ko: str,
    role_hint: str = "",
    discovered_via_issue: str | None = None,
    aliases: list[str] | None = None,
) -> dict:
    """신규 인물 stub 을 data/people/ 에 등록한다.

    Args:
        name_ko: 한국어 이름.
        role_hint: 직함 힌트 (find_participants 결과).
        discovered_via_issue: 발견된 이슈 slug.
        aliases: 별칭 목록.

    Returns:
        {slug, created: bool, pending: bool}
    """
    from limits import _get_counter
    from processors.person_registry import register_person as _register

    counter = _get_counter()
    counter.check_stubs()
    result = _register(name_ko, role_hint, discovered_via_issue, aliases)
    if result["created"]:
        counter.record_stub()
    return result


# ---------------------------------------------------------------------------
# 텍스트 추출
# ---------------------------------------------------------------------------

def extract_events(texts: list[str], person_slug: str, person_name: str) -> list[dict]:
    """텍스트에서 인물의 행적·발언을 추출한다.

    Args:
        texts: 기사 본문 또는 자막 텍스트 목록.
        person_slug: 인물 slug.
        person_name: 인물 한국어 이름.

    Returns:
        [{date, event, source_url}] (날짜 내림차순).
    """
    from processors.chunker import chunk_many
    from processors.extractor import extract_events as _extract
    import yaml

    person_data = _load_person(person_slug)
    keywords = person_data.get("aliases", [person_name])
    chunks = chunk_many(texts, keywords=keywords)
    if not chunks:
        return []
    return _extract(chunks, person_slug, person_name)


def extract_stance(
    texts: list[str],
    person_slug: str,
    person_name: str,
    issue_slug: str,
    no_batch: bool = False,
    no_escalate: bool = False,
) -> dict:
    """텍스트에서 인물의 이슈 입장을 추출한다.

    Args:
        texts: 기사 본문 또는 자막 텍스트 목록.
        person_slug: 인물 slug.
        person_name: 인물 한국어 이름.
        issue_slug: 이슈 slug.
        no_batch: True 면 Batch 대신 동기 Tier 2 사용.
        no_escalate: True 면 Tier 2 에스컬레이션 차단.

    Returns:
        {position, summary, quotes, confidence, escalated}
    """
    from processors.chunker import chunk_many
    from processors.stance_extractor import extract_stance as _extract

    issue_data = _load_issue(issue_slug)
    keywords = issue_data.get("keywords", [issue_slug])
    
    # 지지/반대 판정 기준 로드
    stances_criteria = issue_data.get("stances", {})
    support_crit = stances_criteria.get("support", "")
    oppose_crit = stances_criteria.get("oppose", "")
    criteria = ""
    if support_crit:
        criteria += f"- 지지: {support_crit}\n"
    if oppose_crit:
        criteria += f"- 반대: {oppose_crit}"
    if not criteria:
        criteria = "지지/반대 판정 기준이 명시되지 않았습니다. 일반적인 맥락에서 판단하십시오."

    person_data = _load_person(person_slug)
    person_keywords = person_data.get("aliases", [person_name])

    chunks = chunk_many(texts, keywords=keywords + person_keywords)
    if not chunks:
        return {"position": "unknown", "summary": "", "quotes": [], "confidence": 0.0, "escalated": False}

    return _extract(
        chunks, person_slug, person_name, issue_slug,
        criteria=criteria,
        no_batch=no_batch, no_escalate=no_escalate,
    )


# ---------------------------------------------------------------------------
# Wiki 페이지 생성
# ---------------------------------------------------------------------------

def create_wiki_page(kind: str, slug: str, title: str, summary: str = "") -> dict:
    """wiki 페이지가 없으면 agent 섹션 마커를 포함한 초안을 생성한다.

    이미 존재하면 생성하지 않는다 (인간 편집 페이지 보호).

    Args:
        kind: "people" 또는 "issues".
        slug: 페이지 slug (data/people 또는 data/issues 의 키와 동일).
        title: 페이지 제목 (한국어).
        summary: 한 줄 요약 (선택).

    Returns:
        {created: bool, path: str}
    """
    import yaml as _yaml

    import re as _re
    if _re.search(r"[^a-z0-9\-]", slug):
        logger.error("create_wiki_page: slug 에 비ASCII 문자 포함 — '%s'. register_person 반환값의 slug 를 사용하세요.", slug)
        return {"created": False, "path": "", "error": f"invalid slug '{slug}': must be lowercase ASCII + hyphens only"}

    data_error = _missing_ssot_error(kind, slug, op="create_wiki_page")
    if data_error:
        return {"created": False, "path": "", "error": data_error}

    path = WIKI_ROOT / kind / f"{slug}.md"
    if path.exists():
        return {"created": False, "path": str(path)}

    if kind == "people":
        data = _load_person(slug)
        frontmatter = {
            "title": title,
            "slug": slug,
            "role": data.get("role"),
            "status": data.get("status", "stub"),
        }
        sections = "## 행적\n\n<!-- agent:events -->\n<!-- /agent:events -->\n\n## 이슈별 입장\n\n<!-- agent:stances -->\n<!-- /agent:stances -->\n"

    elif kind == "issues":
        data = _load_issue(slug)
        frontmatter = {
            "title": title,
            "slug": slug,
            "category": data.get("category", "policy"),
            "status": data.get("status", "ongoing"),
            "summary": summary or data.get("summary", ""),
        }
        sections = "## 인물별 입장\n\n<!-- agent:stances -->\n<!-- /agent:stances -->\n"

    else:
        logger.warning("create_wiki_page: 알 수 없는 kind=%s", kind)
        return {"created": False, "path": ""}

    # None 값 제거
    frontmatter = {k: v for k, v in frontmatter.items() if v is not None}
    fm_str = _yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
    content = f"---\n{fm_str}---\n\n{sections}"

    _write_wiki_text(path, content)
    logger.info("wiki 페이지 생성: %s/%s", kind, slug)
    return {"created": True, "path": str(path)}


# ---------------------------------------------------------------------------
# Wiki 섹션 I/O (컨텍스트 격리)
# ---------------------------------------------------------------------------

def _missing_ssot_error(kind: str, slug: str, *, op: str) -> str | None:
    """wiki 쓰기 전 SSoT YAML 존재 여부를 확인한다."""
    if kind == "people":
        data_path = DATA_PEOPLE / f"{slug}.yaml"
        if not data_path.exists():
            logger.error(
                "%s: people/%s 쓰기 거부 — data/people/%s.yaml 없음. register_person 반환 slug 를 사용하세요.",
                op,
                slug,
                slug,
            )
            return f"missing person data for slug '{slug}'"
    elif kind == "issues":
        data_path = DATA_ISSUES / f"{slug}.yaml"
        if not data_path.exists():
            logger.error("%s: issues/%s 쓰기 거부 — data/issues/%s.yaml 없음", op, slug, slug)
            return f"missing issue data for slug '{slug}'"
    return None


def read_agent_section(kind: str, slug: str, section_id: str) -> dict:
    """wiki 페이지의 agent 관리 섹션 본문만 추출한다.

    Args:
        kind: "people" 또는 "issues".
        slug: 페이지 slug.
        section_id: 마커 ID (예: "events", "stances").

    Returns:
        {content: str, exists: bool}
    """
    path = WIKI_ROOT / kind / f"{slug}.md"
    if not path.exists():
        return {"content": "", "exists": False}
    text = _read_wiki_text(path)
    for m in SECTION_RE.finditer(text):
        if m.group("id") == section_id:
            return {"content": m.group("body").strip(), "exists": True}
    return {"content": "", "exists": False}


def _apply_agent_section(kind: str, slug: str, section_id: str, content: str) -> dict:
    """마커 블록을 content 로 치환한다 (검증은 호출 측에서 끝낸다)."""
    from limits import _get_counter

    path = WIKI_ROOT / kind / f"{slug}.md"
    data_error = _missing_ssot_error(kind, slug, op="_apply_agent_section")
    if data_error:
        return {"written": False, "diff_lines": 0, "error": data_error}

    if not path.exists():
        logger.warning("_apply_agent_section: 파일 없음 %s/%s", kind, slug)
        return {"written": False, "diff_lines": 0}

    text = _read_wiki_text(path)
    new_block = f"<!-- agent:{section_id} -->\n{content}\n<!-- /agent:{section_id} -->"
    new_text, n = re.subn(
        rf"<!--\s*agent:{section_id}\s*-->.*?<!--\s*/agent:{section_id}\s*-->",
        new_block, text, count=1, flags=re.DOTALL,
    )
    if n == 0:
        logger.warning("_apply_agent_section: 마커 없음 [%s/%s#%s]", kind, slug, section_id)
        return {"written": False, "diff_lines": 0}

    diff_lines = new_text.count("\n") - text.count("\n")
    _write_wiki_text(path, new_text)

    counter = _get_counter()
    counter.check_pages()
    counter.record_page_modified()

    logger.info("섹션 갱신: %s/%s#%s (%+d lines)", kind, slug, section_id, diff_lines)
    return {"written": True, "diff_lines": diff_lines}


def append_agent_stances(kind: str, slug: str, new_content: str) -> dict:
    """기존 `agent:stances` 블록을 읽어, 이번 차수 bullet 만 병합한 뒤 저장한다.

    중복 판정: 이슈 페이지는 ``(/people/{slug})`` + ``**입장**``,
    인물 페이지는 ``(/issues/{issue_slug})`` + ``**입장**`` 조합이 기존에 있으면
    incoming 해당 줄은 생략한다. 키를 만들 수 없는 줄은 항상 추가된다.

    Args:
        kind: "people" 또는 "issues".
        slug: 위키 페이지 slug.
        new_content: 이번에 추가할 마크다운 (보통 bullet 줄들).

    Returns:
        {written: bool, diff_lines: int}
    """
    path = WIKI_ROOT / kind / f"{slug}.md"
    if not path.exists():
        logger.warning("append_agent_stances: 파일 없음 %s/%s", kind, slug)
        return {"written": False, "diff_lines": 0}

    prev = read_agent_section(kind, slug, "stances")
    existing = prev["content"] if prev["exists"] else ""

    from publishers.stance_merge import merge_stance_sections
    from publishers.quality_gate import append_log, validate_stances

    from publishers.stance_filter import filter_stance_section

    merged = merge_stance_sections(existing, new_content)
    merged = filter_stance_section(merged)
    merged, report = validate_stances(merged, slug=slug)
    append_log(report)
    return _apply_agent_section(kind, slug, "stances", merged)


def write_agent_section(kind: str, slug: str, section_id: str, content: str) -> dict:
    """wiki 페이지의 agent 관리 섹션을 갱신한다.

    ``section_id == "stances"`` 인 경우 전체 교체가 아니라
    :func:`append_agent_stances` 와 동일하게 기존 블록과 병합한다.

    마커가 없는 페이지는 거부한다 (인간 편집 영역 보호).

    Args:
        kind: "people" 또는 "issues".
        slug: 페이지 slug.
        section_id: 마커 ID.
        content: 마크다운 본문 (stances 는 이번에 더할 bullet 위주).

    Returns:
        {written: bool, diff_lines: int}
    """
    if section_id == "stances":
        return append_agent_stances(kind, slug, content)

    path = WIKI_ROOT / kind / f"{slug}.md"
    if not path.exists():
        logger.warning("write_agent_section: 파일 없음 %s/%s", kind, slug)
        return {"written": False, "diff_lines": 0}

    return _apply_agent_section(kind, slug, section_id, content)


# ---------------------------------------------------------------------------
# 커밋
# ---------------------------------------------------------------------------

def commit_changes(summary: str, dry_run: bool = False) -> str | None:
    """변경된 wiki/content/ 와 data/people/ 파일을 [agent] 커밋한다.

    Args:
        summary: 커밋 메시지 본문.
        dry_run: True 면 커밋 없이 대상 파일 목록만 반환.

    Returns:
        커밋 SHA 또는 None.
    """
    from publishers.git_committer import commit_changes as _commit
    return _commit(summary, dry_run=dry_run)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _load_issue(issue_slug: str) -> dict:
    import yaml
    path = DATA_ISSUES / f"{issue_slug}.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_person(person_slug: str) -> dict:
    import yaml
    path = DATA_PEOPLE / f"{person_slug}.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_issue_keywords(issue_slug: str) -> list[str]:
    data = _load_issue(issue_slug)
    return data.get("keywords", [issue_slug])
