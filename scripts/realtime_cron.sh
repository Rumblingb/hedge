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
TOPSTEP_REALTIME_SCRIPT="$HOME_DIR/hedge/scripts/topstep_realtime_proof.py"
PYTHON_BIN="${PYTHON_BIN:-$HOME_DIR/hedge/.venv/bin/python}"
TOPSTEP_DURATION_SEC="${TOPSTEP_DURATION_SEC:-12}"
TOPSTEP_LOCK_FILE="$LOG_DIR/topstep-realtime-proof.lock"
TOPSTEP_REALTIME_CRON_ENABLED="${BILL_TOPSTEP_REALTIME_CRON_ENABLED:-false}"
TOPSTEP_BROKER_TOUCH_PAUSED="${BILL_TOPSTEP_BROKER_TOUCH_PAUSED:-false}"
DOM_CAPTURE_ENABLED="${BILL_DOM_CAPTURE_ENABLED:-false}"
DOM_CAPTURE_SCRIPT="$HOME_DIR/hedge/scripts/topstep_dom_capture.py"
DOM_CAPTURE_STAMP="$LOG_DIR/dom-capture.last-run"
DOM_CAPTURE_INTERVAL_SEC="${BILL_DOM_CAPTURE_INTERVAL_SEC:-900}"

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
    if [ "$TOPSTEP_BROKER_TOUCH_PAUSED" = "true" ]; then
        echo "[bridge] TopstepX realtime refresh skipped: BILL_TOPSTEP_BROKER_TOUCH_PAUSED=true"
    elif [ "$TOPSTEP_REALTIME_CRON_ENABLED" = "true" ]; then
        if mkdir "$TOPSTEP_LOCK_FILE" 2>/dev/null; then
            trap 'rmdir "$TOPSTEP_LOCK_FILE" 2>/dev/null || true' EXIT
            "$PYTHON_BIN" "$TOPSTEP_REALTIME_SCRIPT" --include-es --write-realtime-quote-state --duration-sec "$TOPSTEP_DURATION_SEC" 2>&1 \
                || echo "[bridge] TopstepX realtime refresh did not produce canonical NQ/ES quotes; falling back through bridge stack"
            rmdir "$TOPSTEP_LOCK_FILE" 2>/dev/null || true
            trap - EXIT
        else
            echo "[bridge] TopstepX realtime refresh skipped: prior proof still running ($TOPSTEP_LOCK_FILE)"
        fi
    else
        echo "[bridge] TopstepX realtime refresh skipped: BILL_TOPSTEP_REALTIME_CRON_ENABLED is not true"
    fi
    if [ "$TOPSTEP_BROKER_TOUCH_PAUSED" = "true" ]; then
        echo "[bridge] Topstep DOM capture skipped: BILL_TOPSTEP_BROKER_TOUCH_PAUSED=true"
    elif [ "$DOM_CAPTURE_ENABLED" = "true" ]; then
        now_epoch=$(date +%s)
        last_epoch=$(cat "$DOM_CAPTURE_STAMP" 2>/dev/null || echo 0)
        if [ $((now_epoch - last_epoch)) -ge "$DOM_CAPTURE_INTERVAL_SEC" ]; then
            echo "$now_epoch" > "$DOM_CAPTURE_STAMP"
            # Read-only market-hub DOM/tape capture (60s window); runs in the
            # background so it never delays the 30s quote refresh cadence.
            (RH_TOPSTEP_READ_ONLY=true BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_LIVE_EXECUTION_ENABLED=false                 "$PYTHON_BIN" "$DOM_CAPTURE_SCRIPT" >/dev/null 2>&1 || true) &
        fi
    fi
    "$PYTHON_BIN" "$BRIDGE_SCRIPT" "$@" 2>&1
    echo ""
} >> "$LOG_FILE" 2>&1

exit $?
