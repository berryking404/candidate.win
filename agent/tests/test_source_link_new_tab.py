"""외부 출처 링크는 새 탭, 내부 위키 링크는 같은 탭."""

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


def test_today_source_urls_open_in_new_tab() -> None:
    text = TODAY.read_text(encoding="utf-8")
    assert "target=\"_blank\"" in text
    assert ".url" in text


def test_issue_stance_table_source_keeps_new_tab() -> None:
    text = ISSUES.read_text(encoding="utf-8")
    assert "target=\"_blank\"" in text
    assert "rel=\"noopener\"" in text
