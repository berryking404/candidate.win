"""[Tier 0] 키워드 ±N문장 윈도우 청킹.

키워드가 등장하는 문장의 앞뒤 window_sentences 만 추출해
LLM 입력 토큰을 대폭 줄인다.

일반적으로 자막의 5~10% 만 청크로 남는다.
키워드가 전혀 없으면 빈 리스트를 반환 → LLM 호출 0건 = 비용 0.
"""

from __future__ import annotations

import re

# 한국어 문장 구분자: 마침표·느낌표·물음표 + 줄바꿈 또는 공백
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")


def chunk(
    text: str,
    keywords: list[str],
    window_sentences: int = 2,
    max_chunk_chars: int = 800,
) -> list[str]:
    """키워드가 등장하는 문장의 ±window_sentences 를 모아 청크 리스트 반환.

    Args:
        text: 입력 원문 (기사 본문 또는 자막).
        keywords: 하나라도 포함된 문장을 앵커로 삼음.
        window_sentences: 앵커 문장 앞뒤로 포함할 문장 수.
        max_chunk_chars: 청크 1개 최대 글자 수 (초과 시 분할).

    Returns:
        청크 문자열 리스트. 키워드 미발견 시 빈 리스트.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    # 키워드 포함 문장 인덱스 수집
    anchor_indices: set[int] = set()
    lower_kws = [kw.lower() for kw in keywords]
    for i, sent in enumerate(sentences):
        lower_sent = sent.lower()
        if any(kw in lower_sent for kw in lower_kws):
            anchor_indices.add(i)

    if not anchor_indices:
        return []

    # 앵커 인덱스에서 window 만큼 확장, 인접 윈도우는 병합
    windows = _build_windows(anchor_indices, len(sentences), window_sentences)

    chunks: list[str] = []
    for start, end in windows:
        block = " ".join(sentences[start:end + 1]).strip()
        if not block:
            continue
        # 최대 길이 초과 시 분할
        for sub in _split_by_length(block, max_chunk_chars):
            chunks.append(sub)

    return chunks


def chunk_many(
    texts: list[str],
    keywords: list[str],
    window_sentences: int = 2,
) -> list[str]:
    """여러 텍스트를 한꺼번에 청킹."""
    result: list[str] = []
    for text in texts:
        result.extend(chunk(text, keywords, window_sentences))
    return result


# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """텍스트를 문장 단위로 분할."""
    parts = _SENT_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _build_windows(
    anchors: set[int],
    total: int,
    window: int,
) -> list[tuple[int, int]]:
    """앵커 인덱스에서 window 확장 후 겹치는 구간 병합."""
    intervals: list[tuple[int, int]] = []
    for i in sorted(anchors):
        start = max(0, i - window)
        end = min(total - 1, i + window)
        intervals.append((start, end))

    # 인접·겹침 병합
    merged: list[tuple[int, int]] = []
    for s, e in intervals:
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _split_by_length(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    while text:
        parts.append(text[:max_chars])
        text = text[max_chars:]
    return parts
