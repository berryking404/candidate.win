"""migrations 스크립트 공통 경로."""

from __future__ import annotations

from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENT_ROOT.parent
