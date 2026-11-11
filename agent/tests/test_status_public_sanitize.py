"""공개 /status/ 렌더·카피에서 GitHub 비노출 (Repository Contract)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WIKI = REPO / "wiki"
STATUS_MD = WIKI / "content" / "status.md"
POLICY_MD = WIKI / "content" / "policy.md"
STATUS_LAYOUT = WIKI / "layouts" / "_default" / "status.html"
FETCH_ISSUES = WIKI / "fetch_issues.py"
SANITIZE_MOD = WIKI / "sanitize_public_text.py"


def _load_sanitize():
    spec = importlib.util.spec_from_file_location(
        "sanitize_public_text", SANITIZE_MOD
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sanitize():
    return _load_sanitize().sanitize_public_status_text


def test_sanitize_strips_github_actions_url_from_closeout(sanitize) -> None:
    raw = (
        "Closed after factory Intent pass + merge PR #33 (`6046ac51`) + "
        "Pages Deploy https://github.com/berryking404/candidate.win/actions/runs/42937271745 "
        "success; live https://wiki.candidate.win/people/jeong-bu/ → 404. Ticket ee9febc4."
    )
    out = sanitize(raw)
    assert "github.com" not in out.lower()
    assert "GitHub" not in out
    assert "wiki.candidate.win/people/jeong-bu" in out


def test_sanitize_strips_markdown_github_links_and_bare_hosts(sanitize) -> None:
    raw = (
        "반영 완료. 자세한 기록: [Actions](https://github.com/berryking404/candidate.win/actions/runs/1). "
        "mirror: github.com/berryking404/candidate.win/issues/28"
    )
    out = sanitize(raw)
    assert "github.com" not in out.lower()
    assert "반영 완료" in out


def test_sanitize_strips_factory_ticket_urls(sanitize) -> None:
    raw = (
        "근거 출처 https://factory.askwho.net/tickets/f35f32d7-3eeb-4ed6-983a-353d6db5c0ee "
        "Submitted via wiki report form."
    )
    out = sanitize(raw)
    assert "factory.askwho.net" not in out.lower()
    assert "Submitted via wiki report form" in out


def test_status_and_policy_copy_has_no_github_concepts() -> None:
    for path in (STATUS_MD, POLICY_MD):
        text = path.read_text(encoding="utf-8")
        assert "github.com" not in text.lower(), path.name
        assert "Closes #" not in text, path.name
        assert "저장소" not in text, path.name
        assert "GitHub" not in text, path.name


def test_fetch_issues_applies_sanitize_to_body_and_comments() -> None:
    src = FETCH_ISSUES.read_text(encoding="utf-8")
    assert "format_public_request" in src
    assert "format_public_reply" in src
    assert "from sanitize_public_text import" in src


def test_status_layout_sanitizes_before_markdownify() -> None:
    """렌더 가드: fetch 누락 시에도 github.com이 markdownify로 노출되지 않는다."""
    text = STATUS_LAYOUT.read_text(encoding="utf-8")
    assert "replaceRE" in text
    assert r"github\.com" in text
    assert text.count("replaceRE") >= 4
    # 요청 body + 답변 body 각각 markdownify 직전 sanitize
    assert text.count("markdownify") >= 2
