#!/usr/bin/env bash
# Install thin skill-path shims that exec repo agent/cron SSoT.
# Stale full copies (nohup + bare exec "$@" on 0644) → empty worker.log / exit 99.
set -euo pipefail

TARGET="${1:?usage: install_skill_shims.sh <target_dir>}"
REPO="${CANDYDATE_REPO:-/workspace/repo}"
CRON="$REPO/agent/cron"

mkdir -p "$TARGET"

write_sh_shim() {
  local name="$1"
  cat > "$TARGET/$name" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec bash "\${CANDYDATE_REPO:-/workspace/repo}/agent/cron/$name" "\$@"
EOF
}

write_paths_shim() {
  cat > "$TARGET/paths.sh" <<'EOF'
# Runtime shim → repo agent/cron/paths.sh (zombie-safe is_pid_running, durable log).
# shellcheck shell=bash
_CANDYDATE_CRON="${CANDYDATE_REPO:-/workspace/repo}/agent/cron"
# shellcheck source=/dev/null
source "$_CANDYDATE_CRON/paths.sh"
# Keep SCRIPTS_DIR as this skill directory so entry shims remain the cron entrypoints.
CANDYDATE_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EOF
}

write_py_shim() {
  local name="$1"
  cat > "$TARGET/$name" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec python3 "\${CANDYDATE_REPO:-/workspace/repo}/agent/cron/$name" "\$@"
EOF
}

for name in \
  candydate_pass_ab_launcher.sh \
  candydate_pass_ab_monitor.sh \
  candydate_pass_ab_worker.sh \
  candydate_pass_d_watchdog.sh \
  test_pass_ab_launcher_detach.sh
do
  write_sh_shim "$name"
done

write_paths_shim
write_py_shim leantime_cron_report.py

# Preserve local factory env if present; otherwise copy repo defaults (no secrets).
if [[ ! -f "$TARGET/candydate.env" && -f "$CRON/candydate.env" ]]; then
  cp "$CRON/candydate.env" "$TARGET/candydate.env"
fi

echo "[install_skill_shims] wrote thin shims → $TARGET (repo=$REPO)"
