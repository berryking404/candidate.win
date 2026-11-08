"""Pass A wrapper: main에서 pull --ff-only 한 뒤에만 수집하고, 성공 시 main을 push한다."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "agent" / "launchd" / "run_pass_ab.sh"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(GIT_ENV)
    if env:
        merged.update(env)
    return subprocess.run(cmd, cwd=cwd, env=merged, text=True, capture_output=True, check=False)


def _git(cwd: Path, *args: str) -> None:
    proc = _run(["git", *args], cwd)
    assert proc.returncode == 0, proc.stderr


def _init_pair(tmp: Path) -> tuple[Path, Path]:
    origin = tmp / "origin.git"
    work = tmp / "host"
    _run(["git", "init", "--bare", "-b", "main", str(origin)], tmp)
    work.mkdir()
    _git(work, "init", "-b", "main")
    _git(work, "remote", "add", "origin", str(origin))
    (work / "README").write_text("base\n", encoding="utf-8")
    _git(work, "add", "README")
    _git(work, "commit", "-m", "base")
    _git(work, "push", "-u", "origin", "main")
    return origin, work


def _install_wrapper(work: Path, python_body: str) -> Path:
    launchd = work / "agent" / "launchd"
    launchd.mkdir(parents=True)
    shutil.copy(SCRIPT, launchd / "run_pass_ab.sh")
    (work / "agent" / ".env").write_text("TIER1_BACKEND=ollama\n", encoding="utf-8")
    venv_bin = work / "agent" / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text(
        'export PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd):$PATH"\n',
        encoding="utf-8",
    )
    python = venv_bin / "python"
    python.write_text(python_body, encoding="utf-8")
    python.chmod(0o755)
    return launchd / "run_pass_ab.sh"


def _python_body(marker: Path, *, fail: bool = False, commit_repo: Path | None = None) -> str:
    commit = ""
    if commit_repo is not None:
        commit = f"""
git -C {commit_repo} add -A
git -C {commit_repo} commit -m "[agent] collected" >/dev/null
"""
    fail_line = "exit 1" if fail else commit.strip() or "exit 0"
    return f"""#!/bin/bash
echo ran >> {marker}
{fail_line}
"""


def test_pull_failure_does_not_collect(tmp_path: Path):
    origin, work = _init_pair(tmp_path)
    marker = tmp_path / "python.log"
    script = _install_wrapper(work, _python_body(marker))
    (work / "local.txt").write_text("local\n", encoding="utf-8")
    _git(work, "add", "local.txt")
    _git(work, "commit", "-m", "local")
    side = tmp_path / "side"
    _run(["git", "clone", str(origin), str(side)], tmp_path)
    (side / "remote.txt").write_text("remote\n", encoding="utf-8")
    _git(side, "add", "remote.txt")
    _git(side, "commit", "-m", "remote")
    _git(side, "push", "origin", "main")

    log = tmp_path / "agent.log"
    proc = _run(["bash", str(script)], work, {"CANDYDATE_LOG_FILE": str(log)})

    assert proc.returncode != 0
    assert not marker.exists()
    assert "abort: git pull --ff-only failed" in log.read_text(encoding="utf-8")


def test_success_pulls_then_pushes_main(tmp_path: Path):
    origin, work = _init_pair(tmp_path)
    marker = tmp_path / "python.log"
    script = _install_wrapper(work, _python_body(marker, commit_repo=work))
    side = tmp_path / "side"
    _run(["git", "clone", str(origin), str(side)], tmp_path)
    (side / "remote.txt").write_text("remote\n", encoding="utf-8")
    _git(side, "add", "remote.txt")
    _git(side, "commit", "-m", "remote")
    _git(side, "push", "origin", "main")

    log = tmp_path / "agent.log"
    proc = _run(["bash", str(script)], work, {"CANDYDATE_LOG_FILE": str(log), "PATH": f"{work}/agent/.venv/bin:{os.environ['PATH']}"})

    assert proc.returncode == 0, proc.stderr + log.read_text(encoding="utf-8")
    assert marker.read_text(encoding="utf-8").strip() == "ran"
    assert (work / "remote.txt").is_file()
    local = _run(["git", "rev-parse", "main"], work).stdout.strip()
    remote = _run(["git", "rev-parse", "main"], origin).stdout.strip()
    assert local == remote
    subject = _run(["git", "log", "-1", "--format=%s"], origin).stdout.strip()
    assert subject == "[agent] collected"


def test_python_failure_does_not_push(tmp_path: Path):
    origin, work = _init_pair(tmp_path)
    before = _run(["git", "rev-parse", "main"], origin).stdout.strip()
    marker = tmp_path / "python.log"
    script = _install_wrapper(work, _python_body(marker, fail=True))
    (work / "pending.txt").write_text("pending\n", encoding="utf-8")
    _git(work, "add", "pending.txt")
    _git(work, "commit", "-m", "[agent] unpushed")

    log = tmp_path / "agent.log"
    proc = _run(["bash", str(script)], work, {"CANDYDATE_LOG_FILE": str(log)})

    assert proc.returncode != 0
    assert marker.read_text(encoding="utf-8").strip() == "ran"
    assert _run(["git", "rev-parse", "main"], origin).stdout.strip() == before


def test_non_main_branch_aborts_before_collect(tmp_path: Path):
    _origin, work = _init_pair(tmp_path)
    marker = tmp_path / "python.log"
    script = _install_wrapper(work, _python_body(marker))
    _git(work, "checkout", "-b", "feature/other")

    log = tmp_path / "agent.log"
    proc = _run(["bash", str(script)], work, {"CANDYDATE_LOG_FILE": str(log)})

    assert proc.returncode != 0
    assert not marker.exists()
    assert "abort: HEAD is feature/other" in log.read_text(encoding="utf-8")
