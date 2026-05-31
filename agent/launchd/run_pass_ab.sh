#!/bin/bash
# Pass A (--all research) + Pass B (--batch-submit)
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$AGENT_DIR"

LOG=/tmp/com.candydate.agent.log

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "[Pass A+B] start"

set -a
# shellcheck source=../.env
source .env
set +a

# shellcheck source=../.venv/bin/activate
source .venv/bin/activate

log "[Pass A] --all"
python deep_agent.py --all >> "$LOG" 2>&1

log "[Pass B] --batch-submit"
python deep_agent.py --batch-submit >> "$LOG" 2>&1

log "[Pass A+B] done"
