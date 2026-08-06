#!/usr/bin/env bash
set -u

exec 9>&- 2>/dev/null || true

# shellcheck source=paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/paths.sh"

RUN_ID="${1:?run_id required}"
STARTED_AT="${2:?started_at required}"
REPO="$CANDYDATE_REPO"
RUNNER="$REPO/agent/launchd/run_pass_ab.sh"
STATE_DIR="$CANDYDATE_PASS_AB_STATE_DIR"
STATE_FILE="$STATE_DIR/state.env"
LOCK_FILE="$STATE_DIR/lock"
WORKER_LOG="$STATE_DIR/worker.log"
JOB_NAME="Candydate Pass AB daily collection"
_completion_written=0

now_utc() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
write_state() {
  local tmp
  tmp="$(mktemp "$STATE_DIR/state.env.XXXXXX")"
  cat > "$tmp"
  mv "$tmp" "$STATE_FILE"
}

write_completion() {
  local rc="${1:-1}" finished_at status flock_rc=0
  [[ "$_completion_written" -eq 1 ]] && return 0
  finished_at="$(now_utc)"
  status="failed"
  [[ "$rc" -eq 0 ]] && status="done"
  echo "$(date '+%Y-%m-%d %H:%M:%S') [Pass A+B worker] finishing run_id=$RUN_ID rc=$rc status=$status" >> "$WORKER_LOG"
  (
    if flock -w 30 8; then
      write_state <<EOF
job_name="$JOB_NAME"
run_id="$RUN_ID"
status="$status"
exit_code="$rc"
pid="$$"
started_at="$STARTED_AT"
finished_at="$finished_at"
reported="0"
message="Pass AB worker finished."
EOF
      exit 0
    fi
    exit 98
  ) 8>"$LOCK_FILE"
  flock_rc=$?
  if [[ "$flock_rc" -ne 0 ]]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') [Pass A+B worker] failed to acquire state lock after completion; run_id=$RUN_ID rc=$rc" >> "$WORKER_LOG"
    return 98
  fi
  _completion_written=1
  return 0
}

on_exit() {
  local rc=$?
  write_completion "$rc" || true
}

trap on_exit EXIT

mkdir -p "$STATE_DIR"
echo "$(date '+%Y-%m-%d %H:%M:%S') [Pass A+B worker] start run_id=$RUN_ID pid=$$" >> "$WORKER_LOG"
set +e
cd "$REPO"
cd_rc=$?
if [[ "$cd_rc" -ne 0 ]]; then
  rc=97
  echo "$(date '+%Y-%m-%d %H:%M:%S') [Pass A+B worker] failed to cd $REPO" >> "$WORKER_LOG"
else
  bash "$RUNNER" >> "$WORKER_LOG" 2>&1
  rc=$?
fi
write_completion "$rc"
trap - EXIT
exit "$rc"
