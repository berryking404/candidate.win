"""wiki I/O 헬퍼(_read_wiki_text, _write_wiki_text) 단위 테스트."""

from pathlib import Path

import pytest

from tools import _read_wiki_text, _write_wiki_text, append_agent_stances, create_wiki_page, write_agent_section


def test_write_wiki_text_atomic(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    _write_wiki_text(path, "전영현\n")
    assert path.read_text(encoding="utf-8") == "전영현\n"


def test_read_wiki_text_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "bad.md"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(UnicodeDecodeError) as exc:
        _read_wiki_text(path)
    assert str(path) in str(exc.value)
    assert "UTF-8이 아닌 바이트" in str(exc.value)


def test_create_people_page_requires_registered_person_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools

    wiki_root = tmp_path / "wiki"
    data_people = tmp_path / "data" / "people"
    monkeypatch.setattr(tools, "WIKI_ROOT", wiki_root)
    monkeypatch.setattr(tools, "DATA_PEOPLE", data_people)

    result = create_wiki_page("people", "jhyunjae", "이현재")

    assert result["created"] is False
    assert "missing person data" in result["error"]
    assert not (wiki_root / "people" / "jhyunjae.md").exists()


def test_write_people_section_requires_registered_person_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools

    wiki_root = tmp_path / "wiki"
    data_people = tmp_path / "data" / "people"
    page = wiki_root / "people" / "orphan.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "---\ntitle: Orphan\nslug: orphan\n---\n\n## 행적\n\n<!-- agent:events -->\n<!-- /agent:events -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tools, "WIKI_ROOT", wiki_root)
    monkeypatch.setattr(tools, "DATA_PEOPLE", data_people)

    result = write_agent_section("people", "orphan", "events", "- should not be written")

    assert result["written"] is False
    assert "missing person data" in result["error"]
    assert "should not be written" not in page.read_text(encoding="utf-8")


def test_append_people_stances_requires_registered_person_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools

    wiki_root = tmp_path / "wiki"
    data_people = tmp_path / "data" / "people"
    page = wiki_root / "people" / "orphan.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "---\ntitle: Orphan\nslug: orphan\n---\n\n## 이슈별 입장\n\n<!-- agent:stances -->\n<!-- /agent:stances -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tools, "WIKI_ROOT", wiki_root)
    monkeypatch.setattr(tools, "DATA_PEOPLE", data_people)

    result = append_agent_stances("people", "orphan", "- should not be written")

    assert result["written"] is False
    assert "missing person data" in result["error"]
    assert "should not be written" not in page.read_text(encoding="utf-8")
