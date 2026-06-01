#!/bin/bash
# realtime_cron.sh — Cron-ready wrapper for realtime_data_bridge.py
#
# Runs every 30s via cron/launchd to refresh the real-time quote state file.
# The master bridge reads this file and requires freshness < 60s before trading.
#
# Crontab entry (every 30 seconds during trading hours):
#   * * * * * /Users/brain/hedge/scripts/realtime_cron.sh
#   * * * * * sleep 30; /Users/brain/hedge/scripts/realtime_cron.sh
#
# Or for launchd (preferred — sub-minute precision):
#   See realtime_data_bridge.plist
#
# Logs to: ~/hedge/.rumbling-hedge/logs/realtime-bridge.log

set -euo pipefail

HOME_DIR="${HOME:-/Users/brain}"
LOG_DIR="$HOME_DIR/hedge/.rumbling-hedge/logs"
LOG_FILE="$LOG_DIR/realtime-bridge.log"
BRIDGE_SCRIPT="$HOME_DIR/hedge/scripts/realtime_data_bridge.py"
PYTHON_BIN="${PYTHON_BIN:-$HOME_DIR/hedge/.venv/bin/python}"

# This job is data-only. Force inherited launchd shells into the safest posture.
export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false
export RH_TOPSTEP_READ_ONLY=true
export RH_LIVE_EXECUTION_ENABLED=false

mkdir -p "$LOG_DIR"

# Rotate log if > 10MB
if [ -f "$LOG_FILE" ] && [ "$(stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)" -gt 10485760 ]; then
    mv "$LOG_FILE" "$LOG_FILE.1"
fi

{
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    "$PYTHON_BIN" "$BRIDGE_SCRIPT" "$@" 2>&1
    echo ""
} >> "$LOG_FILE" 2>&1

exit $?
