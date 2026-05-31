#!/usr/bin/env python3
"""Candydate 데이터 관리 CLI.

사용법:
    python data/cli/main.py person list
    python data/cli/main.py person list --status stub
    python data/cli/main.py person show i-jae-myeong
    python data/cli/main.py person add gim-chul-su --name-ko 김철수 --party 국민의힘 --role 국회의원
    python data/cli/main.py person set-status i-jae-myeong curated
    python data/cli/main.py person sync i-jae-myeong
    python data/cli/main.py person sync-pending

    python data/cli/main.py issue list
    python data/cli/main.py issue show real-estate-tax-2026
    python data/cli/main.py issue sync real-estate-tax-2026
    python data/cli/main.py issue sync-all

    python data/cli/main.py status
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_PEOPLE = REPO_ROOT / "data" / "people"
DATA_ISSUES = REPO_ROOT / "data" / "issues"
WIKI_PEOPLE = REPO_ROOT / "wiki" / "content" / "people"
WIKI_ISSUES = REPO_ROOT / "wiki" / "content" / "issues"
AGENT = REPO_ROOT / "agent" / "deep_agent.py"

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
DIM = "\033[2m"


def _load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _has_wiki(slug: str, kind: str) -> bool:
    root = WIKI_PEOPLE if kind == "people" else WIKI_ISSUES
    return (root / f"{slug}.md").exists()


def _status_badge(status: str) -> str:
    if status == "curated":
        return f"{GREEN}curated{RESET}"
    if status == "stub":
        return f"{YELLOW}stub   {RESET}"
    return f"{DIM}{status:<7}{RESET}"


def _wiki_badge(has: bool) -> str:
    return f"{GREEN}wiki{RESET}" if has else f"{RED}no-wiki{RESET}"


def _run_agent(args: list[str], dry_run: bool = False) -> None:
    cmd = [sys.executable, str(AGENT)] + args
    if dry_run:
        cmd.append("--dry-run")
    print(f"{DIM}$ {' '.join(cmd)}{RESET}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT / "agent"))
    if result.returncode != 0:
        sys.exit(result.returncode)


# ---------------------------------------------------------------------------
# person commands
# ---------------------------------------------------------------------------

def cmd_person_list(args: argparse.Namespace) -> None:
    files = sorted(DATA_PEOPLE.glob("*.yaml"))
    for f in files:
        data = _load_yaml(f)
        slug = f.stem
        status = data.get("status", "stub")
        if args.status and status != args.status:
            continue
        has_wiki = _has_wiki(slug, "people")
        name = data.get("name_ko", slug)
        party = data.get("party") or ""
        role = data.get("role") or ""
        print(f"  {_status_badge(status)}  {_wiki_badge(has_wiki)}  {BOLD}{slug}{RESET}  {name}  {DIM}{party} {role}{RESET}")


def cmd_person_show(args: argparse.Namespace) -> None:
    path = DATA_PEOPLE / f"{args.slug}.yaml"
    if not path.exists():
        print(f"{RED}없음: {path}{RESET}", file=sys.stderr)
        sys.exit(1)
    print(path.read_text(encoding="utf-8"))
    wiki = WIKI_PEOPLE / f"{args.slug}.md"
    if wiki.exists():
        print(f"{DIM}--- wiki: {wiki.relative_to(REPO_ROOT)} ---{RESET}")
        print(wiki.read_text(encoding="utf-8")[:600])
    else:
        print(f"{YELLOW}wiki 페이지 없음{RESET}")


def cmd_person_add(args: argparse.Namespace) -> None:
    path = DATA_PEOPLE / f"{args.slug}.yaml"
    if path.exists():
        print(f"{YELLOW}이미 존재: {path.relative_to(REPO_ROOT)}{RESET}")
        sys.exit(1)
    data: dict = {"slug": args.slug, "name_ko": args.name_ko}
    if args.name_en:
        data["name_en"] = args.name_en
    if args.party:
        data["party"] = args.party
    if args.role:
        data["role"] = args.role
    data["status"] = "stub"
    path.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding="utf-8")
    print(f"{GREEN}생성:{RESET} {path.relative_to(REPO_ROOT)}")


def cmd_person_set_status(args: argparse.Namespace) -> None:
    path = DATA_PEOPLE / f"{args.slug}.yaml"
    if not path.exists():
        print(f"{RED}없음: {path}{RESET}", file=sys.stderr)
        sys.exit(1)
    data = _load_yaml(path)
    old = data.get("status", "stub")
    data["status"] = args.new_status
    path.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding="utf-8")
    print(f"{slug_display(args.slug)}: {_status_badge(old)} → {_status_badge(args.new_status)}")


def slug_display(slug: str) -> str:
    return f"{BOLD}{slug}{RESET}"


def _update_wiki_frontmatter(slug: str, yaml_data: dict) -> bool:
    """wiki 페이지 프론트매터의 status·role을 yaml 값으로 덮어쓴다. 변경 있으면 True."""
    import re
    wiki = WIKI_PEOPLE / f"{slug}.md"
    if not wiki.exists():
        return False
    try:
        text = wiki.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"{YELLOW}인코딩 오류, 건너뜀: {wiki.name}{RESET}")
        return False
    m = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not m:
        return False
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)

    changed = False
    for field in ("status", "role", "party"):
        val = yaml_data.get(field)
        if val and fm.get(field) != val:
            fm[field] = val
            changed = True

    if not changed:
        return False

    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
    wiki.write_text(f"---\n{fm_str}---\n{body}", encoding="utf-8")
    return True


def cmd_person_apply_meta(_args: argparse.Namespace) -> None:
    """data/people/*.yaml의 메타(status·role·party)를 wiki 프론트매터에 반영."""
    updated = []
    skipped = []
    for f in sorted(DATA_PEOPLE.glob("*.yaml")):
        slug = f.stem
        data = _load_yaml(f)
        if _update_wiki_frontmatter(slug, data):
            updated.append(slug)
        else:
            skipped.append(slug)
    for slug in updated:
        print(f"  {GREEN}updated{RESET}  {BOLD}{slug}{RESET}")
    if skipped:
        print(f"{DIM}변경 없음: {len(skipped)}명{RESET}")
    print(f"\n{GREEN}{len(updated)}명 반영 완료{RESET}")


def _update_issue_wiki(slug: str, yaml_data: dict) -> bool:
    """wiki 이슈 페이지의 status와 conclusion(편집자 노트)을 yaml 값으로 업데이트."""
    import re
    wiki = WIKI_ISSUES / f"{slug}.md"
    if not wiki.exists():
        return False
    try:
        text = wiki.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"{YELLOW}인코딩 오류, 건너뜀: {wiki.name}{RESET}")
        return False

    # 1. Frontmatter status 업데이트
    m_fm = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not m_fm:
        return False
    fm = yaml.safe_load(m_fm.group(1)) or {}
    body = m_fm.group(2)

    changed = False
    status = yaml_data.get("status")
    if status and fm.get("status") != status:
        fm["status"] = status
        changed = True

    # 2. Conclusion -> 편집자 노트 업데이트 (human-edit 섹션 내)
    conclusion = yaml_data.get("conclusion")
    if conclusion:
        conclusion = conclusion.strip()
        # human-edit 섹션 찾기
        h_match = re.search(r"(<!-- human-edit -->)(.*?)(<!-- /human-edit -->)", text, re.DOTALL)

        note_header = "## 편집자 노트"
        note_content = f"{note_header}\n{conclusion}"

        if h_match:
            h_prefix, h_body, h_suffix = h_match.groups()
            # 이미 편집자 노트가 있는지 확인
            if note_header in h_body:
                # 기존 노트 교체 (다음 헤더 전까지 또는 섹션 끝까지)
                new_h_body = re.sub(rf"{note_header}\n.*?(?=\n##| {re.escape(h_suffix)}|$)",
                                    f"{note_content}\n", h_body, flags=re.DOTALL)
                if new_h_body.strip() != h_body.strip():
                    body = body.replace(f"{h_prefix}{h_body}{h_suffix}", f"{h_prefix}{new_h_body}{h_suffix}")
                    changed = True
            else:
                # 노트가 없으면 섹션 처음에 추가
                new_h_body = f"\n{note_content}\n{h_body.lstrip()}"
                body = body.replace(f"{h_prefix}{h_body}{h_suffix}", f"{h_prefix}{new_h_body}{h_suffix}")
                changed = True
        else:
            # human-edit 섹션 자체가 없으면 body 끝에 생성
            body = body.rstrip() + f"\n\n<!-- human-edit -->\n{note_content}\n<!-- /human-edit -->\n"
            changed = True

    if not changed:
        return False

    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
    wiki.write_text(f"---\n{fm_str}---\n{body}", encoding="utf-8")
    return True


def cmd_issue_apply_meta(_args: argparse.Namespace) -> None:
    """data/issues/*.yaml의 메타(status, conclusion)를 wiki에 반영."""
    updated = []
    skipped = []
    for f in sorted(DATA_ISSUES.glob("*.yaml")):
        slug = f.stem
        data = _load_yaml(f)
        if _update_issue_wiki(slug, data):
            updated.append(slug)
        else:
            skipped.append(slug)

    for slug in updated:
        print(f"  {GREEN}updated{RESET}  {BOLD}{slug}{RESET}")
    if skipped:
        print(f"{DIM}변경 없음: {len(skipped)}개{RESET}")
    print(f"\n{GREEN}{len(updated)}개 이슈 반영 완료{RESET}")


def cmd_person_sync(args: argparse.Namespace) -> None:
    path = DATA_PEOPLE / f"{args.slug}.yaml"
    if not path.exists():
        print(f"{RED}없음: {path}{RESET}", file=sys.stderr)
        sys.exit(1)
    _run_agent(["--person", args.slug], dry_run=args.dry_run)


def cmd_person_sync_pending(args: argparse.Namespace) -> None:
    """curated 이면서 wiki 페이지가 없는 인물을 에이전트로 동기화."""
    targets = []
    for f in sorted(DATA_PEOPLE.glob("*.yaml")):
        data = _load_yaml(f)
        if data.get("status") == "curated" and not _has_wiki(f.stem, "people"):
            targets.append(f.stem)
    if not targets:
        print(f"{GREEN}동기화 대상 없음 (curated 인물 모두 wiki 존재){RESET}")
        return
    print(f"{CYAN}동기화 대상 {len(targets)}명:{RESET} {', '.join(targets)}")
    for slug in targets:
        _run_agent(["--person", slug], dry_run=args.dry_run)


# ---------------------------------------------------------------------------
# issue commands
# ---------------------------------------------------------------------------

def cmd_issue_list(args: argparse.Namespace) -> None:
    for f in sorted(DATA_ISSUES.glob("*.yaml")):
        data = _load_yaml(f)
        slug = f.stem
        status = data.get("status", "ongoing")
        if args.status and status != args.status:
            continue
        has_wiki = _has_wiki(slug, "issues")
        title = data.get("title_ko", slug)
        badge = f"{GREEN}ongoing{RESET}" if status == "ongoing" else f"{DIM}closed {RESET}"
        print(f"  {badge}  {_wiki_badge(has_wiki)}  {BOLD}{slug}{RESET}  {title}")


def cmd_issue_show(args: argparse.Namespace) -> None:
    path = DATA_ISSUES / f"{args.slug}.yaml"
    if not path.exists():
        print(f"{RED}없음: {path}{RESET}", file=sys.stderr)
        sys.exit(1)
    print(path.read_text(encoding="utf-8"))


def cmd_issue_sync(args: argparse.Namespace) -> None:
    path = DATA_ISSUES / f"{args.slug}.yaml"
    if not path.exists():
        print(f"{RED}없음: {path}{RESET}", file=sys.stderr)
        sys.exit(1)
    _run_agent(["--issue", args.slug], dry_run=args.dry_run)


def cmd_issue_sync_all(args: argparse.Namespace) -> None:
    _run_agent(["--all"], dry_run=args.dry_run)


# ---------------------------------------------------------------------------
# status overview
# ---------------------------------------------------------------------------

def cmd_status(_args: argparse.Namespace) -> None:
    people = list(DATA_PEOPLE.glob("*.yaml"))
    issues = list(DATA_ISSUES.glob("*.yaml"))

    curated = [f for f in people if _load_yaml(f).get("status") == "curated"]
    stubs   = [f for f in people if _load_yaml(f).get("status") != "curated"]
    curated_no_wiki = [f for f in curated if not _has_wiki(f.stem, "people")]
    stub_no_wiki    = [f for f in stubs   if not _has_wiki(f.stem, "people")]

    print(f"\n{BOLD}인물{RESET}")
    print(f"  전체        {len(people):>3}명")
    print(f"  curated     {GREEN}{len(curated):>3}명{RESET}  (wiki 없음: {RED}{len(curated_no_wiki)}명{RESET})")
    print(f"  stub        {YELLOW}{len(stubs):>3}명{RESET}  (wiki 없음: {len(stub_no_wiki)}명)")

    if curated_no_wiki:
        print(f"\n  {YELLOW}sync-pending 대상:{RESET}")
        for f in curated_no_wiki:
            print(f"    - {f.stem}")

    print(f"\n{BOLD}이슈{RESET}")
    for f in sorted(issues):
        data = _load_yaml(f)
        has_wiki = _has_wiki(f.stem, "issues")
        status = data.get("status", "ongoing")
        badge = f"{GREEN}ongoing{RESET}" if status == "ongoing" else f"{DIM}closed {RESET}"
        print(f"  {badge}  {_wiki_badge(has_wiki)}  {f.stem}")
    print()


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="candydate",
        description="Candydate 데이터 관리 CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- status --
    sub.add_parser("status", help="전체 현황 요약")

    # -- person --
    p = sub.add_parser("person", help="인물 관리")
    ps = p.add_subparsers(dest="subcommand", required=True)

    pl = ps.add_parser("list", help="인물 목록")
    pl.add_argument("--status", choices=["stub", "curated"])

    pw = ps.add_parser("show", help="인물 상세")
    pw.add_argument("slug")

    pa = ps.add_parser("add", help="새 stub 인물 추가")
    pa.add_argument("slug")
    pa.add_argument("--name-ko", required=True)
    pa.add_argument("--name-en")
    pa.add_argument("--party")
    pa.add_argument("--role")

    pss = ps.add_parser("set-status", help="status 변경")
    pss.add_argument("slug")
    pss.add_argument("new_status", choices=["stub", "curated"])

    psy = ps.add_parser("sync", help="에이전트로 wiki 갱신")
    psy.add_argument("slug")
    psy.add_argument("--dry-run", action="store_true")

    ps.add_parser("apply-meta", help="yaml 메타(status·role·party)를 wiki 프론트매터에 반영")

    psp = ps.add_parser("sync-pending", help="curated이지만 wiki 없는 인물 일괄 동기화")
    psp.add_argument("--dry-run", action="store_true")

    # -- issue --
    i = sub.add_parser("issue", help="이슈 관리")
    iss = i.add_subparsers(dest="subcommand", required=True)

    il = iss.add_parser("list", help="이슈 목록")
    il.add_argument("--status", choices=["ongoing", "closed"])

    iw = iss.add_parser("show", help="이슈 상세")
    iw.add_argument("slug")

    isy = iss.add_parser("sync", help="에이전트로 이슈 wiki 갱신")
    isy.add_argument("slug")
    isy.add_argument("--dry-run", action="store_true")

    iss.add_parser("apply-meta", help="yaml 메타(status, conclusion)를 wiki에 반영")

    isa = iss.add_parser("sync-all", help="전체 이슈 일괄 동기화")
    isa.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    dispatch = {
        ("status", None):              cmd_status,
        ("person", "list"):            cmd_person_list,
        ("person", "show"):            cmd_person_show,
        ("person", "add"):             cmd_person_add,
        ("person", "set-status"):      cmd_person_set_status,
        ("person", "apply-meta"):       cmd_person_apply_meta,
        ("person", "sync"):            cmd_person_sync,
        ("person", "sync-pending"):    cmd_person_sync_pending,
        ("issue",  "list"):            cmd_issue_list,
        ("issue",  "show"):            cmd_issue_show,
        ("issue",  "apply-meta"):       cmd_issue_apply_meta,
        ("issue",  "sync"):            cmd_issue_sync,
        ("issue",  "sync-all"):        cmd_issue_sync_all,
    }

    key = (args.command, getattr(args, "subcommand", None))
    fn = dispatch.get(key)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
