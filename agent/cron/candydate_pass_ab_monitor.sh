#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/paths.sh"

STATE_DIR="$CANDYDATE_PASS_AB_STATE_DIR"
STATE_FILE="$STATE_DIR/state.env"
LOCK_FILE="$STATE_DIR/lock"
LOG_FILE="$CANDYDATE_LOG_FILE"
WORKER_LOG="$STATE_DIR/worker.log"
REPORTER="$CANDYDATE_SCRIPTS_DIR/leantime_cron_report.py"
JOB_NAME="Candydate Pass AB daily collection"

mkdir -p "$STATE_DIR"

now_utc() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
write_state() {
  local tmp
  tmp="$(mktemp "$STATE_DIR/state.env.XXXXXX")"
  cat > "$tmp"
  mv "$tmp" "$STATE_FILE"
}

run_id=""
status=""
exit_code=""
pid=""
started_at=""
finished_at=""
message=""
report_status=""
summary=""
should_report="0"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  exit 0
fi

if [[ ! -f "$STATE_FILE" ]]; then
  flock -u 9
  exit 0
fi

job_name="$JOB_NAME"
reported=""
# shellcheck disable=SC1090
source "$STATE_FILE" || true

if [[ "${reported:-0}" == "1" ]]; then
  flock -u 9
  exit 0
fi

if [[ "${status:-}" == "running" ]]; then
  if is_pid_running "${pid:-}"; then
    flock -u 9
    exit 0
  fi
  status="failed"
  exit_code="99"
  finished_at="$(now_utc)"
  message="Pass AB process disappeared before writing completion status."
  write_state <<EOF
job_name="$JOB_NAME"
run_id="${run_id:-unknown}"
status="$status"
exit_code="$exit_code"
pid="${pid:-}"
started_at="${started_at:-}"
finished_at="$finished_at"
reported="0"
message="$message"
EOF
fi

case "${status:-}" in
  done)
    report_status="done"
    summary="Pass AB collection completed asynchronously. run_id=${run_id:-unknown}, started=${started_at:-unknown}, finished=${finished_at:-unknown}."
    should_report="1"
    ;;
  failed)
    report_status="canceled"
    summary="Pass AB collection failed asynchronously. run_id=${run_id:-unknown}, exit_code=${exit_code:-unknown}, started=${started_at:-unknown}, finished=${finished_at:-unknown}. ${message:-}"
    should_report="1"
    ;;
  *)
    flock -u 9
    exit 0
    ;;
esac

orig_run_id="${run_id:-}"
orig_status="${status:-}"
orig_exit_code="${exit_code:-}"
orig_pid="${pid:-}"
orig_started_at="${started_at:-}"
orig_finished_at="${finished_at:-}"
orig_message="${message:-}"

flock -u 9

if [[ "$should_report" != "1" ]]; then
  exit 0
fi

python3 "$REPORTER" --job-name "$JOB_NAME" --status "$report_status" --exit-code "${orig_exit_code:-0}" --summary "$summary" --log-file "$LOG_FILE" >/dev/null

if ! flock -w 5 9; then
  echo "[Candydate Pass AB] report created but state lock busy; will mark reported on next monitor tick. worker_log=$WORKER_LOG"
  exit 0
fi

cur_run_id=""
cur_status=""
cur_reported=""
if [[ -f "$STATE_FILE" ]]; then
  run_id=""
  status=""
  reported=""
  # shellcheck disable=SC1090
  source "$STATE_FILE" || true
  cur_run_id="${run_id:-}"
  cur_status="${status:-}"
  cur_reported="${reported:-0}"
fi

if [[ "$cur_run_id" == "$orig_run_id" && "$cur_status" == "$orig_status" && "$cur_reported" != "1" ]]; then
  write_state <<EOF
job_name="$JOB_NAME"
run_id="${orig_run_id:-unknown}"
status="$orig_status"
exit_code="${orig_exit_code:-}"
pid="${orig_pid:-}"
started_at="${orig_started_at:-}"
finished_at="${orig_finished_at:-}"
reported="1"
message="${orig_message:-Reported by monitor.}"
EOF
fi

echo "[Candydate Pass AB] reported ${orig_status}: run_id=${orig_run_id:-unknown} exit_code=${orig_exit_code:-} worker_log=$WORKER_LOG"
