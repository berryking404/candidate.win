"""issue apply-meta: yaml title_ko → wiki front matter title 동기화."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT / "data" / "cli" / "main.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("data_cli_main", CLI_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_update_issue_wiki_syncs_title_ko_when_missing(tmp_path: Path, monkeypatch):
    cli = _load_cli()
    wiki_dir = tmp_path / "issues"
    wiki_dir.mkdir()
    monkeypatch.setattr(cli, "WIKI_ISSUES", wiki_dir)

    slug = "korea-japan-acsa-2026"
    (wiki_dir / f"{slug}.md").write_text(
        "---\nslug: korea-japan-acsa-2026\ncategory: foreign\nstatus: ongoing\n"
        "summary: 요약\n---\n\n## 인물별 입장\n\n",
        encoding="utf-8",
    )
    yaml_data = {
        "slug": slug,
        "title_ko": "한일 상호군수지원협정(ACSA) 논의 (2026)",
        "status": "ongoing",
    }

    assert cli._update_issue_wiki(slug, yaml_data) is True

    text = (wiki_dir / f"{slug}.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---", 2)[1])
    assert fm["title"] == "한일 상호군수지원협정(ACSA) 논의 (2026)"


def test_update_issue_wiki_updates_stale_title(tmp_path: Path, monkeypatch):
    cli = _load_cli()
    wiki_dir = tmp_path / "issues"
    wiki_dir.mkdir()
    monkeypatch.setattr(cli, "WIKI_ISSUES", wiki_dir)

    slug = "sample-issue-2026"
    (wiki_dir / f"{slug}.md").write_text(
        "---\ntitle: 옛 제목\nslug: sample-issue-2026\nstatus: ongoing\n---\n\nbody\n",
        encoding="utf-8",
    )

    assert cli._update_issue_wiki(slug, {"title_ko": "새 제목", "status": "ongoing"}) is True

    text = (wiki_dir / f"{slug}.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---", 2)[1])
    assert fm["title"] == "새 제목"
