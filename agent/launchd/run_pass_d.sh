#!/bin/bash
# Pass C (poll & ingest) + Pass D (apply stances)
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$AGENT_DIR"

LOG=/tmp/com.candydate.agent.log

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "[Pass D] start"

set -a
# shellcheck source=../.env
source .env
set +a

# shellcheck source=../.venv/bin/activate
source .venv/bin/activate

log "[Pass C+D] --batch-apply"
set +e
python deep_agent.py --batch-apply >> "$LOG" 2>&1
STATUS=$?
set -e

if [ $STATUS -eq 10 ]; then
    log "[Pass D] active batch 없음 — 적용할 항목 없음"
    exit 0
elif [ $STATUS -eq 1 ]; then
    log "[Pass D] batch 아직 미완료 — 내일 재시도"
elif [ $STATUS -eq 42 ]; then
    log "[Pass D] Circuit Breaker 트립 (종료코드 42)"
else
    log "[Pass D] done (exit $STATUS) — push는 04:00 점검 작업에서 수행"
fi

exit $STATUS
