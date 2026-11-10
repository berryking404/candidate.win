"""정정·삭제 모달 → /api/report 페이로드 (GitHub URL 비노출)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JS = REPO / "wiki" / "static" / "js" / "report-issue-url.js"
BASEOF = REPO / "wiki" / "layouts" / "_default" / "baseof.html"
ISSUE_JS = REPO / "edge" / "report" / "src" / "issue.js"
CORRECTION_TMPL = REPO / ".github" / "ISSUE_TEMPLATE" / "correction.yml"
TAKEDOWN_TMPL = REPO / ".github" / "ISSUE_TEMPLATE" / "takedown.yml"

NODE_PAYLOAD = r"""
const fs = require('fs');
const path = process.argv[1];
const cases = JSON.parse(process.argv[2]);
eval(fs.readFileSync(path, 'utf8'));
const out = cases.map((c) => globalThis.CandydateReport.buildReportPayload(c));
process.stdout.write(JSON.stringify(out));
"""


def _payloads(cases: list[dict]) -> list[dict]:
    assert JS.is_file(), f"missing {JS}"
    proc = subprocess.run(
        ["node", "-e", NODE_PAYLOAD, str(JS), json.dumps(cases)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def _issues(payloads: list[dict]) -> list[dict]:
    assert ISSUE_JS.is_file(), f"missing {ISSUE_JS}"
    # Dynamic import path as file URL for ESM
    import_path = ISSUE_JS.resolve().as_uri()
    code = f"""
import {{ buildGitHubIssue }} from '{import_path}';
const payloads = JSON.parse(process.argv[1]);
const out = payloads.map((p) => buildGitHubIssue(p));
process.stdout.write(JSON.stringify(out));
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", code, json.dumps(payloads)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def test_js_module_exists() -> None:
    assert JS.is_file()


def test_correction_payload_maps_template_fields() -> None:
    page = "https://wiki.candidate.win/people/i-si-ba/"
    payload = _payloads(
        [
            {
                "type": "correction",
                "pageUrl": page,
                "desc": "직함이 잘못됨",
                "source": "https://example.com/bio",
            }
        ]
    )[0]
    assert payload["type"] == "correction"
    assert payload["pageUrl"] == page
    assert payload["targetSlug"] == "i-si-ba"
    assert payload["targetKind"] == "person"
    assert payload["incorrect"] == "직함이 잘못됨"
    assert payload["sources"] == "https://example.com/bio"
    assert "github.com" not in json.dumps(payload)


def test_takedown_payload_maps_template_fields() -> None:
    page = "https://wiki.candidate.win/issues/special-counsel-investigation-2026/"
    payload = _payloads(
        [
            {
                "type": "takedown",
                "pageUrl": page,
                "desc": "사생활 침해 문단",
                "source": "https://example.com/ruling",
            }
        ]
    )[0]
    assert payload["type"] == "takedown"
    assert payload["pageUrl"] == page
    assert payload["targetSlug"] == "special-counsel-investigation-2026"
    assert payload["targetKind"] == "issue"
    assert payload["reason"] == "사생활 침해 문단"
    assert payload["scope"] == "사생활 침해 문단"
    assert payload["legalBasis"] == "https://example.com/ruling"
    assert "identity" not in payload


def test_payload_keys_align_with_issue_template_ids() -> None:
    correction_ids = {
        "page-url",
        "target-slug",
        "target-kind",
        "incorrect",
        "sources",
    }
    takedown_ids = {
        "page-url",
        "target-slug",
        "target-kind",
        "reason",
        "scope",
        "legal-basis",
    }
    correction_text = CORRECTION_TMPL.read_text(encoding="utf-8")
    takedown_text = TAKEDOWN_TMPL.read_text(encoding="utf-8")
    for field_id in correction_ids:
        assert f"id: {field_id}" in correction_text
    for field_id in takedown_ids:
        assert f"id: {field_id}" in takedown_text


def test_worker_builds_github_issue_from_payload() -> None:
    correction = _issues(
        [
            {
                "type": "correction",
                "pageUrl": "https://wiki.candidate.win/people/i-si-ba/",
                "targetSlug": "i-si-ba",
                "targetKind": "person",
                "incorrect": "직함이 잘못됨",
                "sources": "https://example.com/bio",
            }
        ]
    )[0]
    assert correction["title"].startswith("[correction]")
    assert "correction" in correction["labels"]
    assert "직함이 잘못됨" in correction["body"]
    assert "https://example.com/bio" in correction["body"]
    assert "대상 페이지" in correction["body"]

    takedown = _issues(
        [
            {
                "type": "takedown",
                "pageUrl": "https://wiki.candidate.win/issues/x/",
                "targetSlug": "x",
                "targetKind": "issue",
                "reason": "사생활",
                "scope": "사생활",
                "legalBasis": "https://example.com/ruling",
            }
        ]
    )[0]
    assert takedown["title"].startswith("[takedown]")
    assert "takedown" in takedown["labels"]
    assert "사생활" in takedown["body"]
    assert "본인·대리인 확인" not in takedown["body"]
    assert "identity" not in takedown["body"].lower()


def test_baseof_submits_via_api_without_github_ux() -> None:
    text = BASEOF.read_text(encoding="utf-8")
    assert "report-issue-url.js" in text
    assert "CandydateReport.buildReportPayload" in text
    assert "CandydateReport.submitReport" in text
    assert "window.open" not in text
    assert "github.com" not in text.lower()
    assert "GitHub" not in text
    assert "점검 중" not in text


def test_baseof_done_button_click_closes_modal() -> None:
    """성공 후 [접수 완료] 클릭 시 모달이 닫혀야 한다."""
    text = BASEOF.read_text(encoding="utf-8")
    assert 'btn.textContent = "접수 완료"' in text
    # 두 번째 클릭(완료 상태)에서 close
    assert 'btn.textContent === "접수 완료"' in text
    assert "closeReportModal()" in text
    # 성공 직후 버튼이 다시 클릭 가능해야 함
    ok_idx = text.index('btn.textContent = "접수 완료"')
    snippet = text[ok_idx : ok_idx + 120]
    assert "btn.disabled = false" in snippet


def test_js_has_no_github_new_issue_url() -> None:
    text = JS.read_text(encoding="utf-8")
    assert "github.com" not in text.lower()
    assert "buildReportIssueUrl" not in text
    assert 'REPORT_API = "/api/report"' in text or "REPORT_API:" in text
