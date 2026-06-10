"""Publication safety checks for Candydate wiki content.

This module is intentionally deterministic: the nightly Hermes publication gate can run
it before pushing, and hold publication when newly added/changed ongoing issue pages
still have no person stances.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_ISSUES = ROOT / "data" / "issues"
WIKI_ISSUES = ROOT / "wiki" / "content" / "issues"

_STANCE_BLOCK_RE = re.compile(r"<!--\s*agent:stances\s*-->(.*?)<!--\s*/agent:stances\s*-->", re.S)
_STANCE_LINE_RE = re.compile(r"^\s*-\s+\[[^\]]+\]\(/people/[a-z0-9-]+\)\s+—\s+\*\*", re.M)


@dataclass(frozen=True)
class ZeroStanceBlocker:
    slug: str
    status: str
    stance_count: int
    path: str
    reason: str


def count_issue_stances(markdown: str) -> int:
    """Count linked person stance bullets inside the agent-managed stance block."""
    match = _STANCE_BLOCK_RE.search(markdown)
    body = match.group(1) if match else markdown
    return len(_STANCE_LINE_RE.findall(body))


def issue_status(slug: str, *, data_dir: Path = DATA_ISSUES, wiki_dir: Path = WIKI_ISSUES) -> str:
    yaml_path = data_dir / f"{slug}.yaml"
    if yaml_path.exists():
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        return str(data.get("status", "ongoing"))
    md_path = wiki_dir / f"{slug}.md"
    if md_path.exists():
        text = md_path.read_text(encoding="utf-8")
        front = text.split("---", 2)[1] if text.startswith("---") and text.count("---") >= 2 else ""
        data = yaml.safe_load(front) or {}
        return str(data.get("status", "ongoing"))
    return "missing"


def slugs_from_changed_paths(paths: Iterable[str]) -> set[str]:
    slugs: set[str] = set()
    for path in paths:
        p = path.strip()
        if not p:
            continue
        if p.startswith("data/issues/") and p.endswith((".yaml", ".yml")):
            slugs.add(Path(p).stem)
        elif p.startswith("wiki/content/issues/") and p.endswith(".md"):
            slugs.add(Path(p).stem)
    return slugs


def changed_paths_since(base_ref: str = "origin/main") -> list[str]:
    """Return issue-related paths changed in commits/worktree relative to base_ref."""
    cmd = ["git", "diff", "--name-only", base_ref, "--", "data/issues", "wiki/content/issues"]
    proc = subprocess.run(cmd, cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def find_zero_stance_blockers(
    *,
    changed_paths: Iterable[str] | None = None,
    base_ref: str = "origin/main",
    data_dir: Path = DATA_ISSUES,
    wiki_dir: Path = WIKI_ISSUES,
) -> list[ZeroStanceBlocker]:
    """Find changed ongoing issue pages that would publish with zero person stances."""
    if changed_paths is None:
        changed_paths = changed_paths_since(base_ref)
    blockers: list[ZeroStanceBlocker] = []
    for slug in sorted(slugs_from_changed_paths(changed_paths)):
        md_path = wiki_dir / f"{slug}.md"
        if not md_path.exists():
            continue
        status = issue_status(slug, data_dir=data_dir, wiki_dir=wiki_dir)
        if status != "ongoing":
            continue
        count = count_issue_stances(md_path.read_text(encoding="utf-8"))
        if count == 0:
            blockers.append(ZeroStanceBlocker(
                slug=slug,
                status=status,
                stance_count=count,
                path=str(md_path.relative_to(ROOT)) if md_path.is_relative_to(ROOT) else str(md_path),
                reason="ongoing 이슈의 인물별 입장 0개",
            ))
    return blockers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Candydate publication safety gate")
    parser.add_argument("--base", default="origin/main", help="base git ref for pending publication diff")
    args = parser.parse_args(argv)

    blockers = find_zero_stance_blockers(base_ref=args.base)
    if blockers:
        print("PUBLICATION HOLD: ongoing 이슈 중 인물별 입장 0개인 변경사항이 있습니다.")
        for b in blockers:
            print(f"- {b.slug}: {b.reason} ({b.path})")
        return 2
    print("publication_gate: zero-stance ongoing issue blockers 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
