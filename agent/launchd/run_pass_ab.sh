#!/bin/bash
# Pass A — deterministic research (--all). Escalation 큐는 sw-factory candidate IC 가 처리.
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$AGENT_DIR"

LOG="${CANDYDATE_LOG_FILE:-/tmp/com.candydate.agent.log}"
mkdir -p "$(dirname "$LOG")"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "[Pass A] start"

set -a
# shellcheck source=../.env
source .env
set +a

# shellcheck source=../.venv/bin/activate
source .venv/bin/activate

log "[Pass A] --all"
python deep_agent.py --all >> "$LOG" 2>&1

log "[Pass A] done"
