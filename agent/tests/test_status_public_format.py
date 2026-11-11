"""공개 /status/ 요청·답변을 예전(#8/#10) 사용자 포맷으로 맞춤."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SANITIZE_MOD = REPO / "wiki" / "sanitize_public_text.py"
FETCH_ISSUES = REPO / "wiki" / "fetch_issues.py"
AGENTS = REPO / "AGENTS.md"

CORRECTION_FORM = """### 대상 페이지 URL

https://wiki.candidate.win/people/yun-jeon/

### 대상 slug

yun-jeon

### 페이지 종류

person

### 잘못된 내용

윤전 은 윤석열 로 모아 주어야 합니다.

### 올바른 내용

(모달 단일 서술 — 잘못된 내용/정정 요지를 위 필드에 포함)

### 근거 출처

(none)


---
_Submitted via wiki report form (server-side)._
"""

TAKEDOWN_FORM = """### 대상 페이지 URL

https://wiki.candidate.win/people/jeong-bu/

### 대상 slug

jeong-bu

### 페이지 종류

person

### 삭제 범위

인물이 아닙니다.

### 사유

인물이 아닙니다.

### 법적 근거 또는 1차 출처

(none)


---
_Submitted via wiki report form (server-side)._
"""

AGENT_CLOSEOUT = (
    "Closed after factory Intent pass + merge PR #33 (`6046ac51`) + "
    "Pages Deploy https://github.com/berryking404/candidate.win/actions/runs/42937271745 "
    "success; live https://wiki.candidate.win/people/jeong-bu/ → 404. Ticket ee9febc4."
)

RESOLVED_BY_PR = (
    "Resolved by PR #32 (merge 18649b9). Sourceless ACSA stance removed from "
    "people/i-si-ba and issue mirror. Live verified: "
    "https://wiki.candidate.win/people/i-si-ba/ — factory ticket d9210245."
)

GOOD_REPLY = (
    "요청하신 쿠팡 개인정보 유출 이슈 입장 판정을 재검토해, "
    "규제 중단 요구를 비판한 이훈기·우원식 항목을 이슈 기준상 지지로 바로잡았습니다. "
    "반영 커밋: 29addc1"
)

GOOD_REQUEST = (
    "**페이지**: https://wiki.candidate.win/issues/coupang-data-leak-2026/\n\n"
    "**내용**\n태도를 잘못판정한 건이 다수 있다. 확인해서 바로 잡아 달라."
)


def _load():
    spec = importlib.util.spec_from_file_location(
        "sanitize_public_text", SANITIZE_MOD
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_format_public_request_correction_like_issue_8() -> None:
    mod = _load()
    out = mod.format_public_request(CORRECTION_FORM)
    assert out.startswith("**페이지**: https://wiki.candidate.win/people/yun-jeon/")
    assert "**내용**" in out
    assert "윤전 은 윤석열 로 모아 주어야 합니다." in out
    assert "### 대상" not in out
    assert "Submitted via wiki report form" not in out
    assert "대상 slug" not in out
    assert "모달 단일 서술" not in out


def test_format_public_request_takedown() -> None:
    mod = _load()
    out = mod.format_public_request(TAKEDOWN_FORM)
    assert "**페이지**: https://wiki.candidate.win/people/jeong-bu/" in out
    assert "인물이 아닙니다." in out
    assert "법적 근거" not in out
    assert "github.com" not in out.lower()


def test_format_public_request_preserves_legacy_format() -> None:
    mod = _load()
    out = mod.format_public_request(GOOD_REQUEST)
    assert out == mod.sanitize_public_status_text(GOOD_REQUEST) or out == GOOD_REQUEST
    assert "**페이지**" in out
    assert "**내용**" in out


def test_format_public_reply_rewrites_agent_closeout() -> None:
    mod = _load()
    out = mod.format_public_reply(AGENT_CLOSEOUT)
    assert "요청하신" in out
    assert "반영" in out
    assert "factory" not in out.lower()
    assert "PR #" not in out
    assert "github.com" not in out.lower()
    assert "Ticket" not in out
    assert "6046ac51" not in out


def test_format_public_reply_rewrites_resolved_by_pr() -> None:
    mod = _load()
    out = mod.format_public_reply(RESOLVED_BY_PR)
    assert "요청하신" in out
    assert "PR #" not in out
    assert "factory" not in out.lower()
    assert "18649b9" not in out


def test_format_public_reply_preserves_good_exemplar() -> None:
    mod = _load()
    out = mod.format_public_reply(GOOD_REPLY)
    assert out == GOOD_REPLY or out.startswith("요청하신 쿠팡")
    assert "바로잡았습니다" in out


def test_fetch_issues_uses_public_formatters() -> None:
    src = FETCH_ISSUES.read_text(encoding="utf-8")
    assert "format_public_request" in src
    assert "format_public_reply" in src


def test_agents_documents_public_status_format() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "**페이지**" in text or "페이지" in text
    assert "요청하신" in text
