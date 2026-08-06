# Shared path constants for Candydate cron scripts (factory remap).
# shellcheck shell=bash

CANDYDATE_REPO="${CANDYDATE_REPO:-/workspace/repo}"
CANDYDATE_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANDYDATE_STATE_ROOT="${CANDYDATE_STATE_ROOT:-/cursor-home/candydate/state}"
CANDYDATE_PASS_AB_STATE_DIR="${CANDYDATE_PASS_AB_STATE_DIR:-$CANDYDATE_STATE_ROOT/pass_ab}"
CANDYDATE_LOG_FILE="${CANDYDATE_LOG_FILE:-$CANDYDATE_STATE_ROOT/agent.log}"

if [[ -f "$CANDYDATE_SCRIPTS_DIR/candydate.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  # shellcheck source=/dev/null
  source "$CANDYDATE_SCRIPTS_DIR/candydate.env"
  set +a
fi

# kill -0 succeeds on zombies; treat State=Z as not running (avoids false exit 99 / stuck running).
is_pid_running() {
  local pid="${1:-}" state
  [[ -n "$pid" ]] || return 1
  [[ -d "/proc/$pid" ]] || return 1
  state="$(awk '/^State:/{print $2}' "/proc/$pid/status" 2>/dev/null || true)"
  [[ "$state" != "Z" && -n "$state" ]]
}
