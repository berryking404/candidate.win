#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/paths.sh"

cd "$CANDYDATE_REPO"
JOB_NAME="Candydate Pass D batch apply 00/01/02"
LOG_FILE="$CANDYDATE_LOG_FILE"
REPORTER="$CANDYDATE_SCRIPTS_DIR/leantime_cron_report.py"

set +e
bash agent/launchd/run_pass_d.sh
status=$?
set -e
case "$status" in
  0|1|10)
    python3 "$REPORTER" --job-name "$JOB_NAME" --status done --exit-code "$status" --summary "Pass D batch apply completed or reached an accepted no-op/incomplete state." --log-file "$LOG_FILE" >/dev/null || true
    exit 0
    ;;
  42)
    python3 "$REPORTER" --job-name "$JOB_NAME" --status canceled --exit-code "$status" --summary "Pass D circuit breaker tripped." --log-file "$LOG_FILE" >&2 || true
    echo "[Candydate Pass D] circuit breaker tripped. Check ${LOG_FILE}"
    exit 42
    ;;
  *)
    python3 "$REPORTER" --job-name "$JOB_NAME" --status canceled --exit-code "$status" --summary "Pass D failed." --log-file "$LOG_FILE" >&2 || true
    echo "[Candydate Pass D] failed with exit ${status}. Check ${LOG_FILE}"
    exit "$status"
    ;;
esac
