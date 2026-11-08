#!/bin/bash
# launchd 잡 설치 스크립트
# 사용법: bash agent/launchd/install.sh [--uninstall]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
LAUNCHD_DIR="$REPO_DIR/agent/launchd"
TARGET_DIR="$HOME/Library/LaunchAgents"
PLISTS=(com.candydate.research)
LEGACY_PLISTS=(com.candydate.apply)

drop_plist() {
    local label="$1"
    local plist="$TARGET_DIR/$label.plist"
    launchctl unload "$plist" 2>/dev/null && echo "unloaded: $label" || true
    rm -f "$plist" && echo "removed:  $plist"
}

uninstall() {
    for label in "${PLISTS[@]}" "${LEGACY_PLISTS[@]}"; do
        drop_plist "$label"
    done
    echo "Uninstall complete."
    exit 0
}

[[ "${1:-}" == "--uninstall" ]] && uninstall

mkdir -p "$TARGET_DIR"

for label in "${LEGACY_PLISTS[@]}"; do
    drop_plist "$label"
done

for label in "${PLISTS[@]}"; do
    template="$LAUNCHD_DIR/$label.plist.template"
    dest="$TARGET_DIR/$label.plist"

    sed "s|__REPO_DIR__|$REPO_DIR|g" "$template" > "$dest"
    echo "installed: $dest"

    launchctl unload "$dest" 2>/dev/null || true
    launchctl load "$dest"
    echo "loaded:    $label"
done

echo ""
echo "Done. 스케줄:"
echo "  com.candydate.research — 매일 09:00 KST (Pass A: pull, --all, push)"
echo "로그: /tmp/com.candydate.agent.log"
