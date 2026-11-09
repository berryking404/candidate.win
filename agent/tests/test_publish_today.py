from __future__ import annotations

import json
from pathlib import Path

import yaml

import publish_today


def test_refuse_empty_overwrite_when_existing_has_items(tmp_path: Path):
    out = tmp_path / "today.yaml"
    out.write_text(
        yaml.safe_dump({"generated_at": "old", "items": [{"rank": 1, "title": "keep"}]}),
        encoding="utf-8",
    )
    assert publish_today.refuse_empty_overwrite({"items": []}, out) is True
    assert publish_today.refuse_empty_overwrite({"items": [{"rank": 1}]}, out) is False


def test_allow_empty_when_existing_empty_or_missing(tmp_path: Path):
    missing = tmp_path / "missing.yaml"
    empty = tmp_path / "empty.yaml"
    empty.write_text(yaml.safe_dump({"items": []}), encoding="utf-8")
    assert publish_today.refuse_empty_overwrite({"items": []}, missing) is False
    assert publish_today.refuse_empty_overwrite({"items": []}, empty) is False


def test_main_empty_overwrite_exits_2(tmp_path: Path, monkeypatch, capsys):
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"date": "2026-11-09", "candidates": []}), encoding="utf-8")
    out = tmp_path / "today.yaml"
    out.write_text(
        yaml.safe_dump({"items": [{"rank": 1, "title": "keep"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["publish_today.py", "--input", str(cache), "--output", str(out)],
    )
    assert publish_today.main() == 2
    assert "empty-overwrite guard" in capsys.readouterr().err
    assert yaml.safe_load(out.read_text(encoding="utf-8"))["items"][0]["title"] == "keep"
