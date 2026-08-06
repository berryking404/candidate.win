"""Pass AB launcher contracts: setsid+bash (PVC 0644 / kubectl exec teardown)."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CRON = REPO / "agent" / "cron"
LAUNCHER = CRON / "candydate_pass_ab_launcher.sh"
DETACH_TEST = CRON / "test_pass_ab_launcher_detach.sh"


def test_launcher_uses_setsid_and_bash_invoke() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "setsid" in text
    assert "nohup bash -c" not in text
    assert 'exec bash "$@"' in text or "exec bash " in text
    assert 'exec "$@"' not in text.replace('exec bash "$@"', "")


def test_detach_regression_script_passes() -> None:
    proc = subprocess.run(
        ["bash", str(DETACH_TEST)],
        cwd=str(CRON),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout
