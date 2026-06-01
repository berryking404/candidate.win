"""[agent] Git 커밋 자동화.

커밋 메시지는 반드시 [agent] 접두사를 붙인다 (CLAUDE.md 규칙).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent
AGENT_GIT_NAME = "Hermes Agent"
AGENT_GIT_EMAIL = "hermes-agent@users.noreply.github.com"


def commit_changes(summary: str, dry_run: bool = False) -> str | None:
    """변경된 wiki/content/ 및 data/people/ 파일을 커밋.

    Args:
        summary: 커밋 메시지 본문 (접두사 [agent] 자동 추가).
        dry_run: True 면 커밋하지 않고 변경 파일 목록만 반환.

    Returns:
        커밋 SHA (dry_run 이면 "dry-run"), 변경 없으면 None.
    """
    import git

    try:
        repo = git.Repo(REPO_ROOT)
    except git.InvalidGitRepositoryError:
        logger.error("Git 저장소를 찾을 수 없습니다: %s", REPO_ROOT)
        return None

    # 커밋 대상: wiki/content/ 와 data/people/ 만
    changed = [
        item.a_path
        for item in repo.index.diff(None)  # unstaged
    ] + [
        item.a_path
        for item in repo.index.diff("HEAD")  # staged
    ] + repo.untracked_files

    target_paths = [
        p for p in changed
        if p.startswith("wiki/content/") or p.startswith("data/people/")
    ]

    if not target_paths:
        logger.info("커밋 대상 변경 없음")
        return None

    if dry_run:
        logger.info("[dry-run] 커밋 대상: %s", target_paths)
        return "dry-run"

    existing = [p for p in target_paths if (REPO_ROOT / p).exists()]
    deleted  = [p for p in target_paths if not (REPO_ROOT / p).exists()]
    if existing:
        repo.index.add(existing)
    if deleted:
        repo.index.remove(deleted, working_tree=False)
    message = f"[agent] {summary}"
    actor = git.Actor(AGENT_GIT_NAME, AGENT_GIT_EMAIL)
    commit = repo.index.commit(message, author=actor, committer=actor)
    logger.info("커밋 완료: %s — %s", commit.hexsha[:8], message)
    return commit.hexsha
