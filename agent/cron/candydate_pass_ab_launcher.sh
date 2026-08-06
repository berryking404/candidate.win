#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/paths.sh"

STATE_DIR="$CANDYDATE_PASS_AB_STATE_DIR"
STATE_FILE="$STATE_DIR/state.env"
LOCK_FILE="$STATE_DIR/lock"
LOG_FILE="$CANDYDATE_LOG_FILE"
WORKER_LOG="$STATE_DIR/worker.log"
WORKER="$CANDYDATE_SCRIPTS_DIR/candydate_pass_ab_worker.sh"
JOB_NAME="Candydate Pass AB daily collection"

mkdir -p "$STATE_DIR"

now_utc() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
write_state() {
  local tmp
  tmp="$(mktemp "$STATE_DIR/state.env.XXXXXX")"
  cat > "$tmp"
  mv "$tmp" "$STATE_FILE"
}

(
  if ! flock -w 5 9; then
    echo "[Candydate Pass AB] state lock busy; skipped launch tick"
    exit 0
  fi

  status=""
  pid=""
  run_id=""
  reported=""
  started_at=""
  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE" || true
  fi

  if [[ "${status:-}" == "running" ]] && is_pid_running "${pid:-}"; then
    echo "[Candydate Pass AB] already running: run_id=${run_id:-unknown} pid=${pid}"
    exit 0
  fi

  if [[ "${status:-}" == "running" && "${reported:-0}" != "1" ]]; then
    finished_at="$(now_utc)"
    write_state <<EOF
job_name="$JOB_NAME"
run_id="${run_id:-unknown}"
status="failed"
exit_code="99"
pid="${pid:-}"
started_at="${started_at:-}"
finished_at="$finished_at"
reported="0"
message="Previous Pass AB process disappeared before writing completion status."
EOF
    echo "[Candydate Pass AB] previous run is stale; monitor will report it. New run not started to avoid overwriting state."
    exit 0
  fi

  run_id="$(date -u '+%Y%m%dT%H%M%SZ')-$$"
  started_at="$(now_utc)"

  if [[ "${PASS_AB_LAUNCHER_DRY_RUN:-0}" == "1" ]]; then
    echo "[Candydate Pass AB] dry-run ok: would launch run_id=$run_id worker=$WORKER"
    exit 0
  fi

  : > "$WORKER_LOG"

  # PVC seed is often 0644 (no +x); kubectl exec teardown kills nohup children.
  # setsid + bash keeps the worker alive and runnable without +x (see wiki PVC-Nonexec-Script-Setsid-Bash).
  setsid bash -c 'exec 9>&- 2>/dev/null || true; exec bash "$@"' _ "$WORKER" "$run_id" "$started_at" \
    </dev/null >/dev/null 2>&1 &
  worker_pid=$!

  write_state <<EOF
job_name="$JOB_NAME"
run_id="$run_id"
status="running"
exit_code=""
pid="$worker_pid"
started_at="$started_at"
finished_at=""
reported="0"
message="Pass AB worker started."
EOF

  echo "[Candydate Pass AB] launched: run_id=$run_id pid=$worker_pid log=$LOG_FILE worker_log=$WORKER_LOG"
) 9>"$LOCK_FILE"
