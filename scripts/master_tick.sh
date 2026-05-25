#!/bin/bash
# MASTER SYSTEM TICK — Consolidates heartbeat/health crons
# Runs every 5 min. Replaces 9 duplicate heartbeat crons.
set -uo pipefail

cd /Users/brain/hedge
mkdir -p .rumbling-hedge/state .rumbling-hedge/logs
ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# ── Fast checks (every tick = 5m) ──

# 1. Process watchdog
for proc in "gengarMonitor" "gengarExecution" "strategyEngineRunner" "agentpay-labs-bridge"; do
  if ! pgrep -f "$proc" > /dev/null 2>&1; then
    echo "[$ts] $proc DEAD" >> .rumbling-hedge/logs/master-tick.log
  fi
done

# Check special processes that need restart
if ! pgrep -f gengarMonitor > /dev/null 2>&1 && [ -f ops/start-gengar-monitor.sh ]; then
  bash ops/start-gengar-monitor.sh 2>/dev/null &
fi

# ── Medium checks (every 15m) ──
t=$(python3 -c "import time; print(int(time.time()) // 15)")
if [ $((t % 3)) -eq 0 ]; then
  python3 scripts/bill-futures-heartbeat.py 2>/dev/null || true
fi

# ── PM health (every 30m) ──
if [ $((t % 6)) -eq 0 ]; then
  python3 scripts/bill-pm-cycle-health.py 2>/dev/null || true
fi

# ── Log cleanup (once per hour) ──
if [ $((t % 12)) -eq 0 ]; then
  logfile=".rumbling-hedge/logs/master-tick.log"
  if [ -f "$logfile" ]; then
    size=$(stat -f "%z" "$logfile" 2>/dev/null || echo 0)
    if [ "$size" -gt 10485760 ] 2>/dev/null; then
      tail -1000 "$logfile" > "${logfile}.tmp" && mv "${logfile}.tmp" "$logfile"
    fi
  fi
fi

# Silent unless error
echo "[SILENT]"
