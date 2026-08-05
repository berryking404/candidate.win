"""run_pass_ab/d honor CANDYDATE_LOG_FILE (durable path over /tmp)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

AGENT = Path(__file__).resolve().parents[1]
LAUNCHD = AGENT / "launchd"


def _log_line(script: str, env: dict[str, str] | None = None) -> str:
    """Extract resolved LOG assignment the same way the wrappers do."""
    merged = os.environ.copy()
    if env:
        merged.update(env)
    else:
        merged.pop("CANDYDATE_LOG_FILE", None)
    expr = 'LOG="${CANDYDATE_LOG_FILE:-/tmp/com.candydate.agent.log}"; printf "%s" "$LOG"'
    return subprocess.check_output(["bash", "-c", expr], env=merged, text=True)


def test_default_log_falls_back_to_tmp():
    assert _log_line("run_pass_ab.sh") == "/tmp/com.candydate.agent.log"
    assert _log_line("run_pass_d.sh") == "/tmp/com.candydate.agent.log"


def test_env_overrides_log_to_persistent_path(tmp_path: Path):
    target = str(tmp_path / "agent.log")
    assert _log_line("run_pass_ab.sh", {"CANDYDATE_LOG_FILE": target}) == target
    assert _log_line("run_pass_d.sh", {"CANDYDATE_LOG_FILE": target}) == target


def test_wrappers_contain_mkdir_and_env_log():
    for name in ("run_pass_ab.sh", "run_pass_d.sh"):
        text = (LAUNCHD / name).read_text()
        assert 'LOG="${CANDYDATE_LOG_FILE:-/tmp/com.candydate.agent.log}"' in text
        assert 'mkdir -p "$(dirname "$LOG")"' in text
