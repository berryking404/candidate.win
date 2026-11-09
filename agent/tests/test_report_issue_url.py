"""정정·삭제 모달 제출 → GitHub Issue 템플릿 사전채움 URL."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[2]
JS = REPO / "wiki" / "static" / "js" / "report-issue-url.js"
BASEOF = REPO / "wiki" / "layouts" / "_default" / "baseof.html"
CORRECTION_TMPL = REPO / ".github" / "ISSUE_TEMPLATE" / "correction.yml"
TAKEDOWN_TMPL = REPO / ".github" / "ISSUE_TEMPLATE" / "takedown.yml"

NODE_HARNESS = r"""
const fs = require('fs');
const path = process.argv[1];
const cases = JSON.parse(process.argv[2]);
eval(fs.readFileSync(path, 'utf8'));
const out = cases.map((c) => globalThis.CandydateReport.buildReportIssueUrl(c));
process.stdout.write(JSON.stringify(out));
"""


def _build_urls(cases: list[dict]) -> list[str]:
    assert JS.is_file(), f"missing {JS}"
    proc = subprocess.run(
        ["node", "-e", NODE_HARNESS, str(JS), json.dumps(cases)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def test_js_module_exists() -> None:
    assert JS.is_file()


def test_correction_url_prefills_template_fields() -> None:
    page = "https://wiki.candidate.win/people/i-si-ba/"
    url = _build_urls(
        [
            {
                "type": "correction",
                "pageUrl": page,
                "desc": "직함이 잘못됨",
                "source": "https://example.com/bio",
            }
        ]
    )[0]
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "github.com"
    assert parsed.path == "/berryking404/candidate.win/issues/new"
    q = parse_qs(parsed.query)
    assert q["template"] == ["correction.yml"]
    assert q["page-url"] == [page]
    assert q["target-slug"] == ["i-si-ba"]
    assert q["target-kind"] == ["person"]
    assert q["incorrect"] == ["직함이 잘못됨"]
    assert q["sources"] == ["https://example.com/bio"]


def test_takedown_url_prefills_template_fields() -> None:
    page = "https://wiki.candidate.win/issues/special-counsel-investigation-2026/"
    url = _build_urls(
        [
            {
                "type": "takedown",
                "pageUrl": page,
                "desc": "사생활 침해 문단",
                "source": "https://example.com/ruling",
            }
        ]
    )[0]
    q = parse_qs(urlparse(url).query)
    assert q["template"] == ["takedown.yml"]
    assert q["page-url"] == [page]
    assert q["target-slug"] == ["special-counsel-investigation-2026"]
    assert q["target-kind"] == ["issue"]
    assert q["reason"] == ["사생활 침해 문단"]
    assert q["scope"] == ["사생활 침해 문단"]
    assert q["legal-basis"] == ["https://example.com/ruling"]


def test_query_keys_match_issue_template_ids() -> None:
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


def test_baseof_wires_submit_to_github_not_stub() -> None:
    text = BASEOF.read_text(encoding="utf-8")
    assert "report-issue-url.js" in text
    assert "CandydateReport.buildReportIssueUrl" in text
    assert "window.open" in text
    assert "점검 중" not in text
    assert "운영자에게 전달" not in text
