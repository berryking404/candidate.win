"""data/people/ stub 생성 + 동명이인 검출.

Agent 가 신규 발언자를 발견하면 이 모듈로 stub YAML 을 등록한다.
동명이인 의심 시 _pending/ 에 후보 정보를 기록하고 사람의 확인을 기다린다.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DATA_PEOPLE_DIR = Path(__file__).parent.parent.parent / "data" / "people"
PENDING_DIR = DATA_PEOPLE_DIR / "_pending"

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# 한국 실명 검증
_KO_NAME_RE = re.compile(r"^[가-힣]{2,4}$")

# 한국 주요 성씨 (첫 글자 기준 실명 판별)
_COMMON_SURNAMES: frozenset[str] = frozenset({
    "가", "강", "고", "곽", "구", "권", "길", "김", "나", "남",
    "노", "류", "문", "민", "박", "방", "배", "백", "변", "봉",
    "서", "선", "설", "성", "손", "송", "신", "심", "안", "양",
    "엄", "여", "염", "오", "온", "우", "원", "위", "유", "윤",
    "은", "이", "임", "장", "전", "정", "조", "주", "지", "진",
    "차", "채", "천", "최", "추", "탁", "표", "하", "한", "함",
    "허", "현", "형", "홍", "황",
})

# 이름 내부에 포함되면 조직·단체명으로 간주해 거부
_ORG_KEYWORDS: frozenset[str] = frozenset({
    "노총", "노조", "전자", "반도체", "그룹", "연합", "협회", "조합",
    "공사", "공단", "공기업", "은행", "증권", "보험", "투자", "자산",
    "병원", "대학", "학교", "연구", "재단", "기관", "센터", "원회",
    "위원", "국회", "민주", "국민", "자유", "정의", "진보", "보수",
    "한국", "대한", "서울", "부산", "인천", "광주", "대구", "울산",
})


def _is_valid_person_name(name: str) -> bool:
    """실명 여부 검사: 2~4자 한글이고 첫 글자가 한국 성씨인 자연인만 True.

    조직명·직책·영문 브랜드명을 거른다.
    """
    name = name.strip()
    # 영문·숫자·공백·특수문자 포함이면 사람 이름 아님 (E1, Samsung 등)
    if re.search(r"[a-zA-Z0-9\s]", name):
        return False
    # 한글 2~4자여야 함 (노조위원장 = 5자 → 제외)
    if not _KO_NAME_RE.match(name):
        return False
    # 첫 글자(성씨)가 일반 한국 성씨 목록에 없으면 조직명·단어로 간주
    if name[0] not in _COMMON_SURNAMES:
        return False
    # 이름 내부에 조직·단체 키워드 포함 시 거부 (한국노총, 민주연합 등)
    for kw in _ORG_KEYWORDS:
        if kw in name:
            return False
    return True


def register_person(
    name_ko: str,
    role_hint: str = "",
    discovered_via_issue: str | None = None,
    aliases: list[str] | None = None,
) -> dict:
    """인물 stub 을 등록하고 결과를 반환.

    Returns:
        {slug, created: bool, pending: bool}
        - created=True: 신규 파일 생성
        - pending=True: 동명이인 의심, _pending/ 에 기록
    """
    if not _is_valid_person_name(name_ko):
        logger.info("실명 검증 실패, stub 생성 생략: %r", name_ko)
        return {"slug": "", "created": False, "pending": False, "rejected": True}

    slug = _make_slug(name_ko)
    target = DATA_PEOPLE_DIR / f"{slug}.yaml"

    # 이미 존재하면 skip
    if target.exists():
        logger.debug("이미 등록된 인물: %s (%s)", name_ko, slug)
        return {"slug": slug, "created": False, "pending": False}

    # curated slug 로 이미 등록된 동일인 검출
    # (romanizer 표기 vs 관용 표기 불일치 케이스: jeong-dong-yeong vs jeong-dong-young)
    existing_slug = _find_existing_slug(name_ko, slug)
    if existing_slug:
        logger.debug("이미 등록된 인물(curated slug): %s (%s)", name_ko, existing_slug)
        return {"slug": existing_slug, "created": False, "pending": False}

    # 동명이인 검출: 같은 name_ko 또는 alias 가 이미 다른 slug 에 존재하고, curated 가 아닌 경우
    if _has_duplicate(name_ko, slug):
        _write_pending(name_ko, slug, role_hint, discovered_via_issue, aliases)
        logger.warning("동명이인 의심: %s → _pending/ 에 기록", name_ko)
        return {"slug": slug, "created": False, "pending": True}

    # stub 생성
    data = {
        "slug": slug,
        "name_ko": name_ko,
        "name_en": None,
        "party": None,
        "role": role_hint or None,
        "status": "stub",
        "aliases": aliases or [name_ko],
        "discovered_via_issue": discovered_via_issue,
        "discovered_at": str(date.today()),
        "sources": {
            "news_keywords": [name_ko],
            "youtube_channels": [],
        },
    }
    DATA_PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("stub 등록: %s (%s)", name_ko, slug)
    return {"slug": slug, "created": True, "pending": False}


# ---------------------------------------------------------------------------

def _make_slug(name_ko: str) -> str:
    """한글 이름을 로마자 slug 으로 변환.

    글자(음절) 단위로 로마자 변환 후 하이픈으로 연결.
    예: 이재명 → i-jae-myeong, 김동식 → gim-dong-sik
    사람이 curated 할 때 관용 표기(lee-jae-myung 등)로 교정 가능.
    """
    try:
        from korean_romanizer.romanizer import Romanizer
        parts = [Romanizer(c).romanize().lower() for c in name_ko.replace(" ", "")]
        romanized = "-".join(p for p in parts if p)
    except ImportError:
        # 폴백: 글자 수 기반 단순 분리 (URL 비친화적이지만 최소 동작)
        romanized = "-".join(name_ko.replace(" ", ""))

    slug = _SLUG_RE.sub("-", romanized).strip("-")
    return slug or name_ko.replace(" ", "-")


def _find_existing_slug(name_ko: str, new_slug: str) -> str | None:
    """name_ko 또는 aliases 가 일치하는 기존 파일의 slug 를 반환.

    romanizer 표기(jeong-dong-yeong)와 curated 표기(jeong-dong-young)가 다를 때
    동명이인으로 오판하지 않도록 먼저 이 함수로 동일인 여부를 확인한다.
    """
    for f in DATA_PEOPLE_DIR.glob("*.yaml"):
        if f.stem == new_slug:
            continue
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        existing_names = [data.get("name_ko"), data.get("hangul_name")] + (data.get("aliases") or [])
        if name_ko in [n for n in existing_names if n]:
            return data.get("slug", f.stem)
    return None


def _has_duplicate(name_ko: str, new_slug: str) -> bool:
    """같은 이름이 다른 slug 로 이미 존재하는지 검사."""
    for f in DATA_PEOPLE_DIR.glob("*.yaml"):
        if f.stem == new_slug:
            continue
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        existing_names = [data.get("name_ko"), data.get("hangul_name")] + (data.get("aliases") or [])
        if name_ko in [n for n in existing_names if n]:
            return True
    return False


def _write_pending(
    name_ko: str,
    slug: str,
    role_hint: str,
    discovered_via_issue: str | None,
    aliases: list[str] | None,
) -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    import time
    ts = int(time.time())
    candidate = {
        "name_ko": name_ko,
        "proposed_slug": slug,
        "role_hint": role_hint,
        "discovered_via_issue": discovered_via_issue,
        "aliases": aliases or [name_ko],
        "reason": "동명이인 의심",
    }
    path = PENDING_DIR / f"{slug}_{ts}.yaml"
    path.write_text(
        yaml.dump(candidate, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
