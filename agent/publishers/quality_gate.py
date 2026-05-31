"""Pass E — write_agent_section 직전 stance 품질 검증.

검증 규칙:
  Rule 1 — 비-미확인 stance에 출처 URL 없으면 미확인으로 강등.
  Rule 2 — 출처 URL이 소스 캐시에 있으면 요약문 핵심 구절이 원문에 존재하는지 확인.
           일치 없으면 미확인으로 강등.
  Rule 3 — 출처 URL이 있으나 소스 캐시 미스이면 경고만, 강등하지 않음.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

AGENT_DIR = Path(__file__).parent.parent
NAVER_CACHE = AGENT_DIR / ".cache" / "sources" / "naver"
YOUTUBE_CACHE = AGENT_DIR / ".cache" / "sources" / "youtube"
LOGS_DIR = AGENT_DIR / ".logs"

# stance 줄 파싱: - **이름** 또는 - [이름](/path) — **입장**: 설명 [출처](URL)
_STANCE_LINE_RE = re.compile(
    r"^(?P<prefix>- (?:\*\*(?P<name_bold>[^*]+?)\*\*|\[(?P<name_link>[^\]]+?)\]\([^)]*\)) — \*\*(?P<pos>.+?)\*\*: (?P<summary>.+?))"
    r"(?:\s*\[출처\]\((?P<url>[^)]+)\))?$"
)
_UNKNOWN_KO = "미확인"
_MIN_CHUNK = 10  # 원문 매칭에 쓸 최소 구절 길이


def _naver_cache_path(url: str) -> Path:
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    return NAVER_CACHE / f"{key}.txt"


def _youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    if "youtu.be" in parsed.netloc:
        return parsed.path.lstrip("/")
    qs = parse_qs(parsed.query)
    ids = qs.get("v", [])
    return ids[0] if ids else None


def _source_text(url: str) -> str | None:
    """URL에 해당하는 캐시된 원문을 반환. 캐시 미스이면 None."""
    vid = _youtube_video_id(url)
    if vid:
        p = YOUTUBE_CACHE / f"{vid}.txt"
    else:
        p = _naver_cache_path(url)
    return p.read_text(encoding="utf-8") if p.exists() else None


def _has_overlap(summary: str, source: str) -> bool:
    """요약문에서 _MIN_CHUNK자 이상 구절이 원문에 존재하면 True."""
    # 구두점·공백 제거 후 슬라이딩 윈도우
    clean = re.sub(r"[\s.,·…·\"\'""'']", "", summary)
    clean_src = re.sub(r"\s+", "", source)
    step = _MIN_CHUNK
    for i in range(0, max(1, len(clean) - step + 1), step // 2):
        chunk = clean[i : i + step]
        if len(chunk) < step:
            break
        if chunk in clean_src:
            return True
    return False


def validate_stances(content: str, slug: str = "") -> tuple[str, list[dict]]:
    """stance 섹션 마크다운을 검증하고 (정제된 content, 보고서 목록)을 반환.

    실패한 stance는 미확인으로 강등한다.
    """
    lines = content.splitlines()
    out_lines: list[str] = []
    report: list[dict] = []

    for line in lines:
        m = _STANCE_LINE_RE.match(line.strip())
        if not m:
            out_lines.append(line)
            continue

        name = m.group("name_bold") or m.group("name_link")
        pos = m.group("pos")
        summary = m.group("summary").strip()
        url = m.group("url")

        # 이미 미확인이면 통과
        if pos == _UNKNOWN_KO:
            out_lines.append(line)
            continue

        # Rule 1 — URL 없음
        if not url:
            reason = "출처 URL 없음"
            out_lines.append(_downgrade_line(line, m, name, summary))
            report.append(_entry(slug, name, pos, reason, url))
            logger.warning("[quality_gate] 강등 %s/%s — %s", slug, name, reason)
            continue

        # Rule 2 / 3 — 캐시 조회
        source = _source_text(url)
        if source is None:
            # Rule 3 — 캐시 미스, 패널티 없음
            logger.debug("[quality_gate] 캐시 미스 %s/%s url=%s", slug, name, url[:60])
            out_lines.append(line)
            continue

        if not _has_overlap(summary, source):
            reason = "인용문-원문 불일치"
            out_lines.append(_downgrade_line(line, m, name, summary))
            report.append(_entry(slug, name, pos, reason, url))
            logger.warning("[quality_gate] 강등 %s/%s — %s url=%s", slug, name, reason, url[:60])
            continue

        out_lines.append(line)

    return "\n".join(out_lines), report


def _downgrade_line(original: str, m: re.Match, name: str, summary: str) -> str:
    indent = original[: len(original) - len(original.lstrip())]
    # 링크 형식이면 보존, 볼드 형식이면 볼드 유지
    if m.group("name_link") is not None:
        # 원본에서 [이름](/path) 부분 추출
        name_part_match = re.search(r"\[([^\]]+)\]\([^)]*\)", original)
        name_part = name_part_match.group(0) if name_part_match else f"**{name}**"
    else:
        name_part = f"**{name}**"
    return f"{indent}- {name_part} — **{_UNKNOWN_KO}**: {summary}"


def _entry(slug: str, name: str, original_pos: str, reason: str, url: str | None) -> dict:
    return {
        "slug": slug,
        "name": name,
        "original_position": original_pos,
        "reason": reason,
        "url": url,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def append_log(entries: list[dict]) -> None:
    """검증 결과를 .logs/quality_gate.json 에 누적."""
    if not entries:
        return
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "quality_gate.json"
    existing: list[dict] = []
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
    log_path.write_text(
        json.dumps(existing + entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
