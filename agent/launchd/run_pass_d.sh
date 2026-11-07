#!/bin/bash
# Legacy Pass D stub — OpenAI Batch apply 제거됨.
# 저신뢰 stance 는 agent/.cache/escalation/pending.jsonl → sw-factory candidate IC.
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$AGENT_DIR"

LOG="${CANDYDATE_LOG_FILE:-/tmp/com.candydate.agent.log}"
mkdir -p "$(dirname "$LOG")"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "[Pass D] skipped — escalation owned by sw-factory candidate IC"
exit 0
