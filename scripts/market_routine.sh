#!/bin/bash
# Bill/Hedge Market Routine — Session-Aware Pipeline Orchestrator
# Runs pre-market checks, session trading, and end-of-day processing.
# Only operates during US regular session (9:30 AM – 4:00 PM ET).
# Hermes Agent — 2026-05-05

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/ops/mac-mini/bin/_bill-common.sh"
load_bill_env

NOW=$(date -u +%H:%M)
DAY=$(date -u +%u)  # 1=Mon, 7=Sun
ET_HOUR=$(( (10#${NOW%:*} - 4 + 24) % 24 ))  # UTC-4 for ET

# ─── Market Hours Gate ───
SESSION_ACTIVE=false
if [[ $DAY -ge 1 && $DAY -le 5 ]]; then
  if [[ $ET_HOUR -ge 9 && $ET_HOUR -lt 16 ]]; then
    if [[ $ET_HOUR -eq 9 && ${NOW#*:} < "30" ]]; then
      SESSION_ACTIVE=false  # Before 9:30 AM
    else
      SESSION_ACTIVE=true
    fi
  fi
fi

# ─── Pre-Market (9:25-9:30 AM ET) ───
run_premarket() {
  echo "[$(date -Iseconds)] PRE-MARKET CHECK"
  cd "$ROOT"

  # Run morning checklist
  python3 scripts/morning_checklist.py 2>&1 || true

  # Clear stale locks
  rm -rf .rumbling-hedge/run/*.lock 2>/dev/null || true

  # Fire prediction cycle for fresh data
  bash ops/mac-mini/bin/bill-prediction-cycle-scheduled 2>&1 || true

  # Quick health check
  npm run bill:health --silent 2>&1 | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin)
  warnings=d.get('warnings',[])
  print(f'Health: {len(warnings)} warnings')
  for w in warnings[:3]: print(f'  - {w}')
except: print('Health check failed')
" 2>/dev/null || echo "Health: skipped"
}

# ─── Session Trading Loop (every 30 min) ───
run_session_cycle() {
  echo "[$(date -Iseconds)] SESSION CYCLE"
  cd "$ROOT"

  # 1. Prediction cycle (PM data + scan)
  bash ops/mac-mini/bin/bill-prediction-cycle-scheduled 2>&1 | tail -1 || true

  # 2. Paper loop (futures signals → Topstep shadow)
  BILL_PAPER_LOOP_MIN_FREE_GB=15 bash ops/mac-mini/bin/bill-paper-loop 2>&1 | tail -1 || true

  # 3. PM data bridge + execution (runs paper trades on PM opportunities)
  python3 scripts/pm_data_bridge.py --quiet 2>&1 || true
  python3 scripts/pm_execution_engine.py 2>&1 | tail -3 || true
}

# ─── End of Day (4:00 PM ET) ───
run_eod() {
  echo "[$(date -Iseconds)] END OF DAY"
  cd "$ROOT"

  # Strategy lab (OOS rolling + live readiness)
  BILL_STRATEGY_LAB_FULL_EVERY_NTH_RUN=1 \
  BILL_STRATEGY_LAB_LIVE_READINESS_EVERY_NTH_RUN=1 \
  bash ops/mac-mini/bin/bill-strategy-lab-scheduled 2>&1 | tail -5 || true

  # Health check
  npm run bill:health --silent 2>&1 | tail -1 || true

  # Write daily summary
  echo "=== EOD $(date -I) ===" >> .rumbling-hedge/logs/daily-summary.log
  echo "Strategies: $(grep -c 'strategyId' .rumbling-hedge/logs/futures-demo-samples.jsonl 2>/dev/null || echo 0) signals logged" >> .rumbling-hedge/logs/daily-summary.log
}

# ─── Main ───
case "${1:-auto}" in
  premarket)
    run_premarket
    ;;
  cycle)
    if $SESSION_ACTIVE; then
      run_session_cycle
    else
      echo "[$(date -Iseconds)] Outside session hours — skipping"
    fi
    ;;
  eod)
    run_eod
    ;;
  auto)
    # Determine phase based on time
    if [[ $ET_HOUR -eq 9 && ${NOW#*:} < "30" ]]; then
      run_premarket
    elif [[ $ET_HOUR -ge 9 && $ET_HOUR -lt 16 ]]; then
      run_session_cycle
    elif [[ $ET_HOUR -eq 16 && ${NOW#*:} < "05" ]]; then
      run_eod
    else
      echo "[$(date -Iseconds)] Market closed — no trading"
    fi
    ;;
  *)
    echo "Usage: $0 {premarket|cycle|eod|auto}"
    ;;
esac
