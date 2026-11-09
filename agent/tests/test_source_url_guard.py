"""Pass A stance format: placeholder source_url must not block fallback http(s)."""

from deep_agent import _format_person_stance_line, _source_url_from_stance


def test_source_url_skips_na_and_uses_fallback() -> None:
    stance = {
        "position": "support",
        "summary": "협력 필요",
        "quotes": [{"text": "중요 과제", "source_url": "N/A"}],
    }
    fallback = ["https://news.example.com/acsa"]
    assert _source_url_from_stance(stance, fallback) == "https://news.example.com/acsa"


def test_format_person_stance_omits_line_without_valid_url() -> None:
    stance = {
        "position": "support",
        "summary": "협력 필요",
        "quotes": [{"text": "중요 과제", "source_url": "N/A"}],
    }
    assert _format_person_stance_line("korea-japan-acsa-2026", "ACSA", stance, []) is None


def test_format_person_stance_uses_fallback_when_quote_na() -> None:
    stance = {
        "position": "support",
        "summary": "협력 필요",
        "quotes": [{"text": "중요 과제", "source_url": "N/A"}],
    }
    line = _format_person_stance_line(
        "korea-japan-acsa-2026",
        "ACSA",
        stance,
        ["https://news.example.com/acsa"],
    )
    assert line is not None
    assert "[출처](https://news.example.com/acsa)" in line
    assert "N/A" not in line
