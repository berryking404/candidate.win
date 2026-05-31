"""agent:stances 블록 병합 — 기존 줄을 유지하고 신규 줄만 추가.

중복 키 (동일하면 incoming 줄 skip):
- 이슈 페이지: /people/{slug} 링크 + **입장** 한글
- 인물 페이지: /issues/{issue_slug} 링크 + **입장** 한글
키를 만들 수 없는 줄(형식 불일치)은 중복 제거 대상이 아니며, incoming 은 항상 추가된다.
"""

from __future__ import annotations

import re

# prompts.py 입장 레이블과 동일
_STANCE_RE = re.compile(
    r"—\s*\*\*(지지|반대|중립|혼합|미확인)\*\*\s*:",
)
_PEOPLE_PATH = re.compile(r"\]\(/people/([a-z0-9-]+)\)")
_ISSUES_PATH = re.compile(r"\]\(/issues/([a-z0-9-]+)\)")


def parse_stance_merge_key(line: str) -> str | None:
    """병합·중복 판정용 키. 없으면 None (incoming 은 항상 append)."""
    st = _STANCE_RE.search(line)
    if not st:
        return None
    stance = st.group(1)
    m_p = _PEOPLE_PATH.search(line)
    if m_p:
        return f"p:{m_p.group(1)}:{stance}"
    m_i = _ISSUES_PATH.search(line)
    if m_i:
        return f"i:{m_i.group(1)}:{stance}"
    return None


def merge_stance_sections(existing: str, incoming: str) -> str:
    """existing 본문 뒤에 incoming 에서 키가 새로운 줄만 붙인다."""
    ex_lines = [ln.rstrip() for ln in existing.splitlines()]
    in_lines = [ln.rstrip() for ln in incoming.splitlines() if ln.strip()]

    out: list[str] = []
    seen: set[str] = set()

    for ln in ex_lines:
        if ln.strip():
            out.append(ln)
            k = parse_stance_merge_key(ln)
            if k is not None:
                seen.add(k)
        else:
            out.append(ln)

    for ln in in_lines:
        k = parse_stance_merge_key(ln)
        if k is None:
            out.append(ln)
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(ln)

    merged = "\n".join(out)
    if not merged.strip():
        return ""
    return merged.rstrip() + "\n"
