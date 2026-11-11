"""공개 /status/ 등 웹 표면에 나가기 전 내부·GitHub 표식 제거."""

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
