"""외부 출처 링크는 새 탭, 내부 위키 링크는 같은 탭. invalid source는 앵커 금지."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "wiki" / "layouts" / "_markup" / "render-link.html"
TODAY = REPO / "wiki" / "layouts" / "today" / "list.html"
ISSUES = REPO / "wiki" / "layouts" / "partials" / "issues-single.html"


def test_render_link_hook_opens_http_sources_in_new_tab() -> None:
    text = HOOK.read_text(encoding="utf-8")
    assert "target=\"_blank\"" in text
    assert "noopener" in text
    assert "noreferrer" in text
    assert "strings.HasPrefix" in text
    assert "http://" in text and "https://" in text
    assert ".Destination" in text
    assert ".Text" in text


def test_render_link_hook_skips_anchor_for_invalid_destination() -> None:
    """N/A·비-URL destination은 <a> 없이 텍스트만 (prod href=N/A 회귀 방지)."""
    text = HOOK.read_text(encoding="utf-8")
    # http(s) 또는 사이트 내부 경로만 앵커
    assert 'strings.HasPrefix $dest "http://"' in text or 'strings.HasPrefix .Destination "http://"' in text
    assert 'strings.HasPrefix $dest "/"' in text or 'strings.HasPrefix .Destination "/"' in text
    # invalid 분기: 앵커 없이 .Text 만
    assert "else" in text
    # 무조건 <a href="{{ .Destination 패턴만 쓰지 않도록, 조건 분기 뒤에 앵커
    assert "{{ .Text | safeHTML }}" in text
    # 가드 없는 구형 한 줄 훅이 아니어야 함
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("{{/*")]
    assert len(lines) >= 3


def test_today_source_urls_open_in_new_tab() -> None:
    text = TODAY.read_text(encoding="utf-8")
    assert "target=\"_blank\"" in text
    assert ".url" in text
    assert "HasPrefix" in text
    assert "http://" in text


def test_issue_stance_table_source_keeps_new_tab() -> None:
    text = ISSUES.read_text(encoding="utf-8")
    assert "target=\"_blank\"" in text
    assert "rel=\"noopener\"" in text
    assert "HasPrefix" in text
    assert "http://" in text
