from publishers.stance_filter import filter_stance_section, is_negative_unknown_stance


def test_drop_pure_absence():
    line = (
        "- [손훈모](/people/son-hun-mo) — **미확인**: "
        "제공된 기사들에서 구체적 발언이 확인되지 않았다. [출처](http://x)"
    )
    assert is_negative_unknown_stance(line)


def test_keep_substantive_unknown():
    line = (
        "- [위성락](/people/wi-seong-rak) — **미확인**: "
        "쿠팡 유출이 협상에 영향을 준다고 언급했다. [출처](http://x)"
    )
    assert not is_negative_unknown_stance(line)


def test_filter_section():
    content = (
        "- [A](/people/a) — **지지**: 찬성 입장. [출처](http://x)\n"
        "- [B](/people/b) — **미확인**: 확인되지 않았다.\n"
        "- [A](/people/a) — **미확인**: 이번 수집에서 확인되지 않았다.\n"
    )
    out = filter_stance_section(content)
    assert "people/a" in out and "지지" in out
    assert "people/b" not in out
    assert out.count("people/a") == 1
