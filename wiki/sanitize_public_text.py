"""공개 /status/ 등 웹 표면에 나가기 전 내부·GitHub 표식 제거 + 사용자 포맷 변환."""

from __future__ import annotations

import re

_MD_LINK_GITHUB = re.compile(
    r"\[([^\]]*)\]\(\s*https?://(?:www\.)?github\.com/[^)]+\)",
    re.IGNORECASE,
)
_GITHUB_URL = re.compile(
    r"https?://(?:www\.)?github\.com/[^\s)\]>'\"<>]+",
    re.IGNORECASE,
)
_GITHUB_BARE = re.compile(
    r"(?:www\.)?github\.com/[^\s)\]>'\"<>]+",
    re.IGNORECASE,
)
_GITHUB_WORD = re.compile(r"\bGitHub\b", re.IGNORECASE)
_FACTORY_URL = re.compile(
    r"https?://(?:[\w.-]+\.)?factory\.askwho\.net/[^\s)\]>'\"<>]*",
    re.IGNORECASE,
)
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NL = re.compile(r"\n{3,}")

_FIELD_HEADER = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
_LEGACY_PAGE = re.compile(r"^\*\*페이지\*\*", re.MULTILINE)
_AGENT_CLOSEOUT = re.compile(
    r"(?i)(Closed after factory|Resolved by PR\b|Pages Deploy|factory ticket|"
    r"factory Intent|merge PR\s*#\d+|Live verified:)"
)
_PR_OR_SHA = re.compile(
    r"(?i)(\bPR\s*#\d+\b|`?[0-9a-f]{7,40}`?|\bTicket\s+[0-9a-f-]{8,}\b)"
)

_PLACEHOLDER_CONTENT = re.compile(
    r"^\(모달 단일 서술|^_No response_|^\(none\)$|^No response$",
    re.IGNORECASE,
)


def sanitize_public_status_text(text: str | None) -> str:
    """요청·답변 본문에서 github.com / GitHub / factory URL을 제거한다."""
    if not text:
        return ""
    out = _MD_LINK_GITHUB.sub(r"\1", text)
    out = _GITHUB_URL.sub("", out)
    out = _GITHUB_BARE.sub("", out)
    out = _GITHUB_WORD.sub("", out)
    out = _FACTORY_URL.sub("", out)
    out = _MULTI_SPACE.sub(" ", out)
    out = _MULTI_NL.sub("\n\n", out)
    return out.strip()


def _parse_gh_form_fields(body: str) -> dict[str, str]:
    """GitHub Issue form / Option A Worker body의 ### 필드를 dict로 파싱."""
    matches = list(_FIELD_HEADER.finditer(body))
    if not matches:
        return {}
    fields: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        value = body[start:end]
        # footer --- Submitted… 제거
        value = re.split(r"\n---\n", value, maxsplit=1)[0]
        fields[name] = value.strip()
    return fields


def _clean_field_value(value: str) -> str:
    text = sanitize_public_status_text(value)
    if not text or _PLACEHOLDER_CONTENT.match(text.splitlines()[0].strip()):
        return ""
    # checkbox / 확인 사항 블록은 공개면에 불필요
    if text.startswith("- [") or "명예훼손·사생활" in text:
        return ""
    return text


def format_public_request(body: str | None) -> str:
    """GH Issue form 덤프 → 예전 공개 포맷 (`**페이지**` / `**내용**`)."""
    raw = body or ""
    if _LEGACY_PAGE.search(raw):
        return sanitize_public_status_text(raw)

    fields = _parse_gh_form_fields(raw)
    if not fields:
        return sanitize_public_status_text(raw)

    page = _clean_field_value(
        fields.get("대상 페이지 URL") or fields.get("페이지") or ""
    )
    content = _clean_field_value(
        fields.get("잘못된 내용")
        or fields.get("사유")
        or fields.get("삭제 범위")
        or fields.get("내용")
        or ""
    )

    parts: list[str] = []
    if page:
        parts.append(f"**페이지**: {page}")
    if content:
        parts.append(f"**내용**\n{content}")
    if parts:
        return "\n\n".join(parts)
    return sanitize_public_status_text(raw)


def _public_reply_fallback(text: str) -> str:
    lowered = text.lower()
    if any(
        k in lowered
        for k in ("404", "removed", "takedown", "삭제", "제거", "strip")
    ):
        return (
            "요청하신 삭제 요청을 반영했습니다. "
            "해당 페이지에서 요청하신 내용을 제거·정리했습니다."
        )
    return "요청하신 내용을 반영했습니다. 관련 항목을 바로잡았습니다."


def format_public_reply(body: str | None) -> str:
    """agent/GH closeout → 「요청하신 … 반영했습니다」 사용자 문장."""
    raw = body or ""
    cleaned = sanitize_public_status_text(raw)
    if not cleaned:
        return ""
    if _AGENT_CLOSEOUT.search(raw) or _AGENT_CLOSEOUT.search(cleaned):
        return _public_reply_fallback(cleaned)
    if _PR_OR_SHA.search(cleaned) and not cleaned.startswith("요청하신"):
        # "Resolved by PR" 변형 등
        if re.search(r"(?i)\b(resolved by|closed after|merge pr)\b", cleaned):
            return _public_reply_fallback(cleaned)
    return cleaned
