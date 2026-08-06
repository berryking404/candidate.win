#!/usr/bin/env bash
# Regression: Pass AB worker must survive parent-shell exit (kubectl exec teardown)
# and must start when skill scripts are mode 0644 (no +x on PVC seed).
# TDD: fail if launcher uses nohup-only or bare exec of non-executable worker.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$SCRIPTS_DIR/candydate_pass_ab_launcher.sh"
WORKER="$SCRIPTS_DIR/candydate_pass_ab_worker.sh"
TMP_ROOT="$(mktemp -d /tmp/pass_ab_detach_test.XXXXXX)"
cleanup() {
  if [[ -f "$TMP_ROOT/pid" ]]; then
    kill "$(cat "$TMP_ROOT/pid")" 2>/dev/null || true
  fi
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

# Contract: durable detach uses setsid (nohup alone dies with kubectl exec session).
if ! grep -q 'setsid' "$LAUNCHER"; then
  echo "FAIL: $LAUNCHER must launch worker via setsid (kubectl exec session teardown)"
  exit 1
fi
if grep -qE '^\s*nohup bash -c' "$LAUNCHER"; then
  echo "FAIL: $LAUNCHER still backgrounds with nohup; setsid required"
  exit 1
fi

# Contract: skill scripts on PVC are often 0644 — must invoke via bash, not bare exec.
if ! grep -qE 'exec bash |bash "\$' "$LAUNCHER"; then
  echo "FAIL: $LAUNCHER must exec via bash (worker may lack +x; bare exec → exit 99)"
  exit 1
fi
if grep -qE "exec \"\\\$@\"" "$LAUNCHER"; then
  echo "FAIL: $LAUNCHER still uses bare exec \"\$@\" on worker path (Permission denied if 0644)"
  exit 1
fi
mode="$(stat -c '%a' "$WORKER" 2>/dev/null || stat -f '%OLp' "$WORKER")"
if [[ "$mode" == "755" || "$mode" == "0755" ]]; then
  echo "NOTE: worker mode=$mode (executable); regression still requires bash invoke for 0644 seeds"
fi

# Behavioral check: setsid child survives subshell+flock exit (launcher pattern).
(
  flock -w 5 9 || exit 1
  setsid bash -c "echo \$\$ > '$TMP_ROOT/pid'; echo started > '$TMP_ROOT/out'; exec sleep 20" \
    </dev/null >/dev/null 2>&1 &
) 9>"$TMP_ROOT/lock"

sleep 0.3
pid="$(cat "$TMP_ROOT/pid")"
if [[ ! -d "/proc/$pid" ]]; then
  echo "FAIL: setsid worker pid=$pid died after parent subshell exit"
  exit 1
fi

# Behavioral check: bare exec of 0644 script fails; bash invoke works.
stub="$TMP_ROOT/stub.sh"
printf '%s\n' '#!/usr/bin/env bash' 'echo ok > "'"$TMP_ROOT"'/stub.out"' > "$stub"
chmod 644 "$stub"
if "$stub" 2>/dev/null; then
  echo "FAIL: expected Permission denied for 0644 direct exec"
  exit 1
fi
bash "$stub"
if [[ "$(cat "$TMP_ROOT/stub.out")" != "ok" ]]; then
  echo "FAIL: bash invoke of 0644 stub did not run"
  exit 1
fi

# Contract: zombie PIDs must not count as running (kill -0 is true for State=Z).
# shellcheck source=paths.sh
source "$SCRIPTS_DIR/paths.sh"
if ! grep -q 'State' "$SCRIPTS_DIR/paths.sh" || ! grep -q 'is_pid_running' "$SCRIPTS_DIR/paths.sh"; then
  echo "FAIL: paths.sh must define zombie-safe is_pid_running"
  exit 1
fi
# Simulate: live sleep is running; after kill, if it becomes zombie briefly, must report not running.
(
  sleep 30 &
  echo $! > "$TMP_ROOT/live.pid"
)
live_pid="$(cat "$TMP_ROOT/live.pid")"
if ! is_pid_running "$live_pid"; then
  echo "FAIL: expected live pid=$live_pid to be running"
  exit 1
fi
kill "$live_pid" 2>/dev/null || true
# Wait until gone or zombie
for _ in 1 2 3 4 5 6 7 8 9 10; do
  state="$(awk '/^State:/{print $2}' "/proc/$live_pid/status" 2>/dev/null || echo gone)"
  [[ "$state" == "gone" || "$state" == "Z" ]] && break
  sleep 0.05
done
if is_pid_running "$live_pid"; then
  echo "FAIL: is_pid_running must be false for dead/zombie pid=$live_pid state=${state:-?}"
  exit 1
fi

echo "PASS: launcher uses setsid+bash; detach survived; 0644 needs bash; zombie-safe pid check (pid=$pid)"
