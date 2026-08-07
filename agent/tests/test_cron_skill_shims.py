"""Skill-path cron scripts must be thin shims to repo agent/cron SSoT.

Stale full copies under the skill PVC (nohup + bare exec \"$@\" on 0644 workers)
cause empty worker.log and monitor exit 99. See PVC-Nonexec-Script-Setsid-Bash.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CRON = REPO / "agent" / "cron"
INSTALLER = CRON / "install_skill_shims.sh"

SHIM_NAMES = (
    "candydate_pass_ab_launcher.sh",
    "candydate_pass_ab_monitor.sh",
    "candydate_pass_ab_worker.sh",
    "candydate_pass_d_watchdog.sh",
    "test_pass_ab_launcher_detach.sh",
    "paths.sh",
    "leantime_cron_report.py",
)


def test_installer_script_exists() -> None:
    assert INSTALLER.is_file(), f"missing {INSTALLER}"


def test_installer_writes_thin_shims_not_stale_nohup() -> None:
    with tempfile.TemporaryDirectory(prefix="candydate_shim_") as tmp:
        target = Path(tmp)
        # Simulate stale PVC seed that caused ticket 308 exit 99.
        stale = target / "candydate_pass_ab_launcher.sh"
        stale.write_text(
            "#!/usr/bin/env bash\n"
            "nohup bash -c 'exec \"$@\"' _ ./worker.sh >/dev/null 2>&1 &\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            ["bash", str(INSTALLER), str(target)],
            cwd=str(CRON),
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "CANDYDATE_REPO": str(REPO)},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        for name in SHIM_NAMES:
            path = target / name
            assert path.is_file(), f"shim missing: {name}"
            text = path.read_text(encoding="utf-8")
            assert "nohup" not in text, f"{name} still contains nohup"
            assert 'exec "$@"' not in text, f"{name} still bare-execs worker"
            assert "agent/cron/" in text or name == "paths.sh", f"{name} must point at repo cron"
            if name.endswith(".sh") and name != "paths.sh":
                assert "exec bash" in text, f"{name} must exec bash repo script"


def test_installed_launcher_uses_repo_setsid_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="candydate_shim_") as tmp:
        target = Path(tmp)
        subprocess.run(
            ["bash", str(INSTALLER), str(target)],
            cwd=str(CRON),
            check=True,
            env={**os.environ, "CANDYDATE_REPO": str(REPO)},
        )
        # Resolving the shim must surface the repo launcher setsid+bash contract.
        launcher = (target / "candydate_pass_ab_launcher.sh").read_text(encoding="utf-8")
        assert str(CRON / "candydate_pass_ab_launcher.sh") in launcher.replace(
            "${CANDYDATE_REPO:-/workspace/repo}", str(REPO)
        ) or "agent/cron/candydate_pass_ab_launcher.sh" in launcher
        repo_launcher = (CRON / "candydate_pass_ab_launcher.sh").read_text(encoding="utf-8")
        assert "setsid" in repo_launcher
        assert 'exec bash "$@"' in repo_launcher
