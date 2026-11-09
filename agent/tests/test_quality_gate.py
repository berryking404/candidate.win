"""Pass E quality_gate: invalid/N/A source URL은 출처 없음과 동일하게 강등."""

from publishers.quality_gate import is_valid_source_url, validate_stances


def test_is_valid_source_url_accepts_http_https_only() -> None:
    assert is_valid_source_url("https://example.com/a")
    assert is_valid_source_url("http://example.com/a")
    assert is_valid_source_url("  https://example.com/a  ")
    assert not is_valid_source_url(None)
    assert not is_valid_source_url("")
    assert not is_valid_source_url("N/A")
    assert not is_valid_source_url("n/a")
    assert not is_valid_source_url("/people/i-si-ba")
    assert not is_valid_source_url("javascript:alert(1)")


def test_validate_stances_downgrades_na_placeholder_url() -> None:
    content = (
        "- [이시바](/people/i-si-ba) — **지지**: ACSA 협력 필요. [출처](N/A)\n"
        "- [이재명](/people/i-jae-myeong) — **반대**: 신중. "
        "[출처](https://www.ytn.co.kr/replay/view.php?idx=1)\n"
    )
    out, report = validate_stances(content, slug="korea-japan-acsa-2026")
    assert "[출처](N/A)" not in out
    assert "**미확인**" in out
    assert "[출처](https://www.ytn.co.kr/replay/view.php?idx=1)" in out
    assert any(e.get("reason") for e in report)
    assert any(e.get("url") == "N/A" for e in report)
