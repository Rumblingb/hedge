#!/usr/bin/env bash
# kill_switch.sh — Emergency stop for ALL system activity
# Usage: bash kill_switch.sh
# Stages: 1=gentle (stop new), 2=hard (close all), 3=nuclear (kill everything)

set -e

STAGE=${1:-1}
echo "=== KILL SWITCH — Stage $STAGE ==="
echo ""

if [ "$STAGE" -ge 1 ]; then
  echo "[1/3] Stopping new signal generation..."
  # Clear Gengar state to stop execution
  echo '{"lastExecutedSignal":0,"totalExecuted":0,"totalFilled":0,"totalRejected":0}' > /Users/brain/hedge/.rumbling-hedge/state/gengar-execution.json 2>/dev/null || true
  # Clear pending signals
  > /Users/brain/hedge/.rumbling-hedge/journal/gengar-signals.jsonl 2>/dev/null || true
  # Disable cron jobs
  crontab -l 2>/dev/null | grep -v "gengar\|pipeline\|backtest\|watchdog" | crontab - 2>/dev/null || true
  echo "  ✅ Signal generation stopped"
fi

if [ "$STAGE" -ge 2 ]; then
  echo "[2/3] Killing active processes..."
  # Kill gengar processes
  pkill -f "gengarMonitor" 2>/dev/null || true
  pkill -f "gengarExecution" 2>/dev/null || true
  # Kill any running strategy execution
  pkill -f "tsx.*strategy" 2>/dev/null || true
  pkill -f "tsx.*trade" 2>/dev/null || true
  echo "  ✅ All processes stopped"
fi

if [ "$STAGE" -ge 3 ]; then
  echo "[3/3] NUCLEAR — Kill all Hermes-related processes..."
  pkill -9 -f "gengar" 2>/dev/null || true
  pkill -9 -f "tsx" 2>/dev/null || true
  pkill -9 -f "hermes" 2>/dev/null || true
  # Clear all state files
  rm -f /Users/brain/hedge/.rumbling-hedge/state/*.json 2>/dev/null || true
  echo "  ✅ System fully stopped"
fi

echo ""
echo "=== Kill switch complete ==="
echo "To restart: cd ~/hedge && bash ops/start_system.sh (if it exists)"
