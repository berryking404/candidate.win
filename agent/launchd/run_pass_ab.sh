#!/bin/bash
# Pass A — main을 맞춘 뒤 deterministic research (--all). 성공하면 main을 push한다.
# Escalation 큐는 sw-factory candidate IC 가 workspace 심링크를 통해 읽는다.
set -euo pipefail

AGENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_DIR="$(cd "$AGENT_DIR/.." && pwd)"

LOG="${CANDYDATE_LOG_FILE:-/tmp/com.candydate.agent.log}"
mkdir -p "$(dirname "$LOG")"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

git_to_log() {
  local status
  set +e
  "$@" 2>&1 | sed -E 's#x-access-token:[^@[:space:]]+#x-access-token:***#g; s#gho_[A-Za-z0-9]+#gho_***#g' >> "$LOG"
  status=${PIPESTATUS[0]}
  set -e
  return "$status"
}

log "[Pass A] start"

cd "$REPO_DIR"
branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != "main" ]]; then
  log "[Pass A] abort: HEAD is ${branch}"
  exit 1
fi

before="$(git rev-parse HEAD)"
if ! git_to_log git pull --ff-only origin main; then
  log "[Pass A] abort: git pull --ff-only failed"
  exit 1
fi
after="$(git rev-parse HEAD)"
if [[ "$before" != "$after" && "${CANDYDATE_PASS_A_REEXECED:-}" != "1" ]]; then
  log "[Pass A] updated ${before} -> ${after}, re-exec"
  export CANDYDATE_PASS_A_REEXECED=1
  exec "$0" "$@"
fi

cd "$AGENT_DIR"

set -a
# shellcheck source=../.env
source .env
set +a

# shellcheck source=../.venv/bin/activate
source .venv/bin/activate

log "[Pass A] --all"
python deep_agent.py --all >> "$LOG" 2>&1

log "[Pass A] push"
if ! git_to_log git -C "$REPO_DIR" push origin main; then
  log "[Pass A] abort: git push failed"
  exit 1
fi

log "[Pass A] done"
