"""[Tier 0] kiwipiepy 기반 한국어 인명 후보 추출.

NNP(고유명사) 토큰 중 직함·역할어와 인접한 것을 인물 후보로 추출한다.
LLM 없이 순수 로컬에서 동작한다.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from functools import lru_cache

logger = logging.getLogger(__name__)

# 인물 직함·역할어 (앞·뒤 최대 2토큰 이내에 등장하면 인명으로 간주)
ROLE_KEYWORDS: frozenset[str] = frozenset({
    "의원", "국회의원", "장관", "대통령", "총리", "대표", "위원장", "후보",
    "지사", "시장", "구청장", "도지사", "군수", "청장", "처장", "본부장",
    "대변인", "원내대표", "부대표", "사무총장", "수석", "비서관", "보좌관",
    "교수", "박사", "변호사", "검사", "판사", "기자", "앵커", "기관장",
    "CEO", "대표이사", "회장", "이사장", "총재", "총장",
})

# 제외 목록: 인명이 아닌 NNP 노이즈
EXCLUDE_TOKENS: frozenset[str] = frozenset({
    "한국", "대한민국", "서울", "미국", "중국", "일본", "북한", "정부", "국회",
    "청와대", "용산", "민주당", "국민의힘", "공화당", "민주당", "여당", "야당",
    "뉴스", "연합", "기사", "보도", "발표", "전달", "오늘", "어제", "내일",
    "KBS", "MBC", "SBS", "JTBC", "YTN", "TV",
})

# 한국어 인명 패턴: 2~4글자 한글 (성 1글자 + 이름 1~3글자)
_KO_NAME_RE = re.compile(r"^[가-힣]{2,4}$")


class PersonCandidate:
    def __init__(self, name: str, mention_count: int, sample_contexts: list[str]) -> None:
        self.name = name
        self.mention_count = mention_count
        self.sample_contexts = sample_contexts[:3]

    def to_dict(self) -> dict:
        return {
            "name_ko": self.name,
            "mention_count": self.mention_count,
            "sample_contexts": self.sample_contexts,
        }


def extract_person_candidates(
    texts: list[str],
    *,
    min_mentions: int = 1,
    role_required: bool = False,
) -> list[PersonCandidate]:
    """텍스트 목록에서 인명 후보 추출.

    Args:
        texts: 청킹된 텍스트 목록.
        min_mentions: 이 횟수 이상 언급된 인물만 반환.
        role_required: True 면 직함 인접 NNP 만 반환 (정밀도 ↑, 재현율 ↓).

    Returns:
        PersonCandidate 리스트 (mention_count 내림차순).
    """
    kiwi = _get_kiwi()
    name_counter: Counter[str] = Counter()
    name_contexts: dict[str, list[str]] = {}

    for text in texts:
        if not text.strip():
            continue
        try:
            candidates = _extract_from_text(kiwi, text, role_required)
            for name, ctx in candidates:
                name_counter[name] += 1
                if name not in name_contexts:
                    name_contexts[name] = []
                if len(name_contexts[name]) < 3:
                    name_contexts[name].append(ctx)
        except Exception as exc:
            logger.debug("NER 분석 실패: %s", exc)

    results = [
        PersonCandidate(name, count, name_contexts.get(name, []))
        for name, count in name_counter.most_common()
        if count >= min_mentions and name not in EXCLUDE_TOKENS
    ]
    return results


def extract_names_simple(texts: list[str]) -> list[str]:
    """빠른 인명 후보 집합 반환 (중복 제거, 정렬)."""
    candidates = extract_person_candidates(texts, min_mentions=1)
    return [c.name for c in candidates]


# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_kiwi():
    from kiwipiepy import Kiwi
    return Kiwi()


def _extract_from_text(kiwi, text: str, role_required: bool) -> list[tuple[str, str]]:
    """단일 텍스트에서 (인명, 문맥) 튜플 목록 반환."""
    result = kiwi.analyze(text)
    if not result:
        return []

    # kiwi.analyze 는 리스트[리스트[Token]] 반환 (문장 단위)
    tokens_per_sent = result[0][0] if result else []
    # 실제로 result 는 (morphs, score) 튜플이므로:
    morphs = result[0][0]

    # 토큰 목록: (형태, 품사)
    token_list = [(m.form, m.tag) for m in morphs]

    candidates: list[tuple[str, str]] = []
    for i, (form, tag) in enumerate(token_list):
        if str(tag) not in ("NNP", "NNG"):
            continue
        if not _KO_NAME_RE.match(form):
            continue
        if form in EXCLUDE_TOKENS:
            continue

        # 인접 토큰(±2)에서 직함 검색
        window = token_list[max(0, i - 2): i + 3]
        nearby_forms = {t[0] for t in window}
        has_role = bool(nearby_forms & ROLE_KEYWORDS)

        if role_required and not has_role:
            continue

        # 문맥: 인접 문자 60자
        start = max(0, text.find(form) - 30)
        end = min(len(text), text.find(form) + len(form) + 30)
        ctx = text[start:end].replace("\n", " ").strip()

        candidates.append((form, ctx))

    return candidates
