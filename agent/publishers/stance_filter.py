"""agent:stances 에서 부정적 **미확인**(조사 실패·언급만) 줄을 걸러낸다."""

from __future__ import annotations

import re

_STANCE_LABEL = re.compile(r"—\s*\*\*(지지|반대|중립|혼합|미확인)\*\*\s*:")
_PEOPLE_PATH = re.compile(r"\]\(/people/([a-z0-9-]+)\)")
_ISSUES_PATH = re.compile(r"\]\(/issues/([a-z0-9-]+)\)")

# 본문에 실질 발언·행위가 있으면 미확인이라도 유지
_SUBSTANTIVE = re.compile(
    r"언급했다|지적했다|말했다|밝혔다|밝혔|제기했다|강조했다|"
    r"다뤘다|영향을|엇갈|사전통지|조사를|제재|처분|"
    r"지적했다|제기했다|언급했다",
)

# 순수 부재·조사 실패·이름만 등장
_NEGATIVE = re.compile(
    r"확인되지|확인하지 못|확인할 수 없|확인하기 어려|"
    r"직접 발언은 없|직접 발언이 없|직접적인 입장 표명이 확인되지|"
    r"구체적 발언이 확인되지|명시적 찬반 입장은|직접 입장은 확인되지|"
    r"직접 입장은 드러나지|기사에서 확인되지|"
    r"제공된 기사|제공된 텍스트|수집 기사|수집된 자료|이번 수집|"
    r"텍스트에서 이슈에 대한 구체적 입장이 직접 확인되지|"
    r"이슈 직접 발언은 없|본인 입장은 기사에서|"
    r"로만 등장|로만 확인|부족하다\.|명확하지 않다|"
    r"거론되지만|주목되지만|놓였으나|맥락에서 거론|"
    r"드러나지 않|찾기 어려|어렵다\.|언급됐|확인됐|확정하기 어렵|"
    r"언급은 있었",
)


def entity_key(line: str) -> str | None:
    m = _PEOPLE_PATH.search(line)
    if m:
        return f"p:{m.group(1)}"
    m = _ISSUES_PATH.search(line)
    if m:
        return f"i:{m.group(1)}"
    return None


def is_negative_unknown_stance(line: str) -> bool:
    """조사 실패·이름만 거론 등 기록 가치가 낮은 **미확인** bullet."""
    if "— **미확인**" not in line:
        return False
    body = line.split("— **미확인**:", 1)[-1]
    # 송치·거론만 있고 입장 부재를 밝히는 줄
    if re.search(r"직접 입장.*확인되지|직접 발언.*확인되지", body):
        return True
    if re.search(r"핵심 당사자로 거론|연루된 인물로", body):
        return True
    if _SUBSTANTIVE.search(body):
        return False
    return bool(_NEGATIVE.search(body))


def filter_stance_section(content: str) -> str:
    """stances 블록 본문에서 부정적 미확인 줄을 제거한다."""
    lines = [ln.rstrip() for ln in content.splitlines()]
    kept: list[str] = []
    for ln in lines:
        if not ln.strip():
            continue
        if ln.strip().startswith("-") and is_negative_unknown_stance(ln):
            continue
        kept.append(ln)

    # 동일 인물/이슈에 지지·반대·중립·혼합(또는 실질 미확인)이 있으면 남은 미확인 중복도 제거
    substantive_keys: set[str] = set()
    for ln in kept:
        k = entity_key(ln)
        if k and not is_negative_unknown_stance(ln):
            st = _STANCE_LABEL.search(ln)
            if st and st.group(1) != "미확인":
                substantive_keys.add(k)
            elif st and st.group(1) == "미확인":
                substantive_keys.add(k)

    final: list[str] = []
    for ln in kept:
        k = entity_key(ln)
        if (
            k
            and k in substantive_keys
            and "— **미확인**" in ln
            and is_negative_unknown_stance(ln)
        ):
            continue
        final.append(ln)

    if not final:
        return ""
    return "\n".join(final).rstrip() + "\n"
