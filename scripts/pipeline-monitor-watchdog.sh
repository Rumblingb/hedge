#!/bin/bash
# pipeline-monitor-watchdog.sh — No-agent pipeline watchdog
# Runs pipeline_monitor.py --alert and outputs only on problems.
# Designed for cron no-agent mode: silent when healthy, alerts on issues.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HEDGE_SCRIPTS="${HOME}/hedge/scripts"
MONITOR="${HEDGE_SCRIPTS}/pipeline_monitor.py"

if [ ! -f "$MONITOR" ]; then
    echo "🔴 pipeline_monitor.py not found at $MONITOR"
    exit 1
fi

# Run alert mode — exits 0 (no output) if healthy, non-zero with alert text if problems
OUTPUT=$(python3 "$MONITOR" --alert 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ] && [ -n "$OUTPUT" ]; then
    echo "$OUTPUT"
    exit 1
fi

# Silent if healthy
exit 0
