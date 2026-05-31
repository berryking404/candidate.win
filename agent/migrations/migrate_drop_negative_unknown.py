#!/usr/bin/env python3
"""wiki agent:stances 에서 부정적 미확인 bullet 일괄 제거."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from migrations._paths import AGENT_ROOT, REPO_ROOT

sys.path.insert(0, str(AGENT_ROOT))

from publishers.stance_filter import filter_stance_section

WIKI = REPO_ROOT / "wiki" / "content"
SECTION_RE = re.compile(
    r"(<!--\s*agent:stances\s*-->)(.*?)(<!--\s*/agent:stances\s*-->)",
    re.DOTALL,
)


def migrate_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False

    def repl(m: re.Match) -> str:
        nonlocal changed
        body = m.group(2).strip("\n")
        if body:
            lines = [ln for ln in body.splitlines() if ln.strip()]
            body_for_filter = "\n".join(lines) + ("\n" if lines else "")
        else:
            body_for_filter = ""
        filtered = filter_stance_section(body_for_filter)
        new_body = ("\n" + filtered.rstrip("\n")) if filtered else ""
        if new_body != ("\n" + body if body else ""):
            changed = True
        return f"{m.group(1)}{new_body}\n{m.group(3)}"

    new_text = SECTION_RE.sub(repl, text)
    if changed:
        path.write_text(new_text, encoding="utf-8")
    return changed


def main() -> None:
    n = 0
    for kind in ("issues", "people"):
        for path in sorted((WIKI / kind).glob("*.md")):
            if migrate_file(path):
                print(path.relative_to(REPO_ROOT))
                n += 1
    print(f"updated {n} files")


if __name__ == "__main__":
    main()
