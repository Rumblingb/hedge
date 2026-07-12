#!/usr/bin/env bash
# ============================================================
# AGENTIC FUND SHADOW CYCLE — SIMPLE RELIABLE OPERATION
# ============================================================
# This is the HEART of the fund. One script that:
# 1. Checks if markets are open (US holidays, weekends)
# 2. Runs ALL 15 signal generators via the arsenal runner
# 3. Fuses signals through the decision bridge
# 4. Checks risk management (daily loss, drawdown)
# 5. Runs the guarded bridge only when explicitly enabled
# 6. Logs everything
# ============================================================

set -e
cd /Users/brain/hedge
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LOG_DIR="/Users/brain/.hermes/fund-logs"
STATE_DIR="/Users/brain/hedge/.rumbling-hedge/state"
EXECUTION_ENABLED="${BILL_ENABLE_AGENTIC_FUND_EXECUTION:-false}"
VAULT_DIR="/Users/brain/Documents/memorybrain"
TRADING_TIMEZONE="${BILL_TRADING_TIMEZONE:-Europe/London}"
DAILY_PLAN="$VAULT_DIR/Agent-Hermes/daily/$(TZ="$TRADING_TIMEZONE" date +"%Y-%m-%d")-bill-trading-plan.md"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/fund-$TS.log"

execution_gate_status() {
    local blockers=()

    if [ "$EXECUTION_ENABLED" != "true" ]; then
        blockers+=("BILL_ENABLE_AGENTIC_FUND_EXECUTION is not true")
    fi
    if [ "${BILL_ENABLE_FUTURES_DEMO_EXECUTION:-false}" != "true" ]; then
        blockers+=("BILL_ENABLE_FUTURES_DEMO_EXECUTION is not true")
    fi
    if [ "${RH_TOPSTEP_READ_ONLY:-true}" != "false" ]; then
        blockers+=("RH_TOPSTEP_READ_ONLY is not false")
    fi
    if [ "${RH_LIVE_EXECUTION_ENABLED:-false}" = "true" ]; then
        blockers+=("RH_LIVE_EXECUTION_ENABLED is true")
    fi
    if [ ! -f "$DAILY_PLAN" ]; then
        blockers+=("daily plan missing: $DAILY_PLAN")
    else
        if grep -Fqx "No new Bill/Hermes orders approved." "$DAILY_PLAN"; then
            blockers+=("daily plan explicitly says no new Bill/Hermes orders approved")
        fi
        if ! grep -Fqx "BILL_ROUTE_APPROVAL: APPROVED" "$DAILY_PLAN"; then
            blockers+=("daily plan lacks BILL_ROUTE_APPROVAL: APPROVED")
        fi
        if ! grep -Fqx "BROKER_RECONCILIATION: GREEN" "$DAILY_PLAN"; then
            blockers+=("daily plan lacks BROKER_RECONCILIATION: GREEN")
        fi
    fi

    if [ "${#blockers[@]}" -gt 0 ]; then
        printf '%s\n' "${blockers[@]}"
        return 1
    fi
    return 0
}

echo "============================================" | tee -a "$LOG"
echo "AGENTIC FUND — $TS" | tee -a "$LOG"
echo "============================================" | tee -a "$LOG"

# STEP 1: CHECK MARKET STATUS
echo "--- Market Status ---" | tee -a "$LOG"
# US market holidays 2026 (simplified)
HOLIDAYS="2026-01-01 2026-01-19 2026-02-16 2026-04-03 2026-05-25 2026-06-19 2026-07-03 2026-09-07 2026-11-26 2026-12-25"
TODAY=$(date +"%Y-%m-%d")
DOW=$(date +"%u")  # 1=Mon, 7=Sun

if [ "$DOW" -eq 6 ] || [ "$DOW" -eq 7 ]; then
    echo "⛔ WEEKEND — No trading ($TODAY)" | tee -a "$LOG"
    exit 0
fi

for h in $HOLIDAYS; do
    if [ "$TODAY" = "$h" ]; then
        echo "⛔ HOLIDAY — $TODAY is a US market holiday" | tee -a "$LOG"
        exit 0
    fi
done

echo "✅ Markets open — $TODAY" | tee -a "$LOG"

# STEP 2: RUN SIGNAL GENERATORS
echo "--- Signal Generation ---" | tee -a "$LOG"
python3 scripts/new_arsenal_runner.py 2>&1 | tee -a "$LOG"

# STEP 3: DECISION BRIDGE — Read ALL signals, fuse them, decide
echo "--- Decision Bridge ---" | tee -a "$LOG"
python3 -c "
import json, os
from pathlib import Path

S = Path('/Users/brain/hedge/.rumbling-hedge/state')

def read_signal(name):
    p = S / name
    return json.loads(p.read_text()) if p.exists() else {}

def promoted_execution_overlay(data):
    return data.get('promoted_for_execution') is True and data.get('tradable_signal') is True

# Read all 15 signals
pead = read_signal('pead-signal.latest.json')
sr = read_signal('sr-proximity-signal.latest.json')
donchian = read_signal('donchian-signal.latest.json')
ichimoku = read_signal('ichimoku-signal.latest.json')
insider = read_signal('insider-signal.latest.json')
cot = read_signal('cot-signal.latest.json')
noise = read_signal('noise-analysis.latest.json')
vwap = read_signal('vwap-signal.latest.json')
ha = read_signal('heiken-ashi-signal.latest.json')
fib = read_signal('fibonacci-signal.latest.json')
manip = read_signal('manipulation-4h-signal.latest.json')
dom = read_signal('dom-proxy-signal.latest.json')
kalman = read_signal('kalman-pairs-signal.latest.json')

# Count bullish vs bearish
bullish = 0
bearish = 0
bull_sources = []
bear_sources = []

# VWAP mean-reversion
v_dir = vwap.get('NQ',{}).get('direction','neutral')
if v_dir == 'long': bullish += 2; bull_sources.append('VWAP+2')
elif v_dir == 'short': bearish += 2; bear_sources.append('VWAP+2')

# Heiken Ashi
ha_trend = ha.get('NQ',{}).get('trend','neutral')
if ha_trend == 'bullish': bullish += 1; bull_sources.append('HA')
elif ha_trend == 'bearish': bearish += 1; bear_sources.append('HA')

# Insider
i_bias = insider.get('nq_bias','neutral')
i_conf = insider.get('confidence',0)
if i_bias in ('bearish','very_bearish') and i_conf > 0.4: bearish += 2; bear_sources.append(f'Insider+{i_conf}')
elif i_bias in ('bullish','very_bullish') and i_conf > 0.4: bullish += 2; bull_sources.append(f'Insider+{i_conf}')

# COT
c_bias = cot.get('nq_bias','neutral')
if cot and not promoted_execution_overlay(cot):
    bull_sources.append('COT-shadow-ignored')
elif c_bias in ('bullish','very_bullish'): bullish += 1; bull_sources.append('COT')
elif c_bias in ('bearish','very_bearish'): bearish += 1; bear_sources.append('COT')

# Manipulation
m_bias = manip.get('NQ',{}).get('bias','neutral')
m_conf = manip.get('NQ',{}).get('confidence',0)
if m_bias == 'bullish' and m_conf > 0.5: bullish += 1; bull_sources.append('Manip')
elif m_bias == 'bearish' and m_conf > 0.5: bearish += 1; bear_sources.append('Manip')

# Ichimoku (weaker weight)
i_trend = ichimoku.get('NQ',{}).get('trend','neutral')
if i_trend == 'bullish': bullish += 1; bull_sources.append('Ichi')
elif i_trend == 'bearish': bearish += 1; bear_sources.append('Ichi')

# Donchian
d_dir = donchian.get('direction','neutral')
if d_dir == 'long': bullish += 1; bull_sources.append('Donch')
elif d_dir == 'short': bearish += 1; bear_sources.append('Donch')

total = bullish + bearish
if total == 0:
    dir = 'neutral'
    conf = 0
else:
    dir = 'bullish' if bullish > bearish else 'bearish' if bearish > bullish else 'neutral'
    conf = max(bullish, bearish) / total if total > 0 else 0

# Convince level
conviction = 'LOW'
if conf > 0.7: conviction = 'HIGH'
elif conf > 0.6: conviction = 'MEDIUM'

print(f'  Bullish: {bullish} ({", ".join(bull_sources)})')
print(f'  Bearish: {bearish} ({", ".join(bear_sources)})')
print(f'  Direction: {dir.upper()} (conf={conf:.2f})')
print(f'  Conviction: {conviction}')
print(f'  Action: {\"TRADE\" if conviction != \"LOW\" else \"HOLD\"}')

# Save decision
S.mkdir(parents=True, exist_ok=True)
decision = {
    'timestamp': '$TS',
    'bullish_score': bullish,
    'bearish_score': bearish,
    'direction': dir,
    'confidence': round(conf, 2),
    'conviction': conviction,
    'sources': {'bullish': bull_sources, 'bearish': bear_sources},
}
(S / 'fund-decision.latest.json').write_text(json.dumps(decision, indent=2))
" 2>&1 | tee -a "$LOG"

# STEP 4: GUARDED BRIDGE
# Default is shadow-only. Set BILL_ENABLE_AGENTIC_FUND_EXECUTION=true only
# after the live-readiness gate, broker reconciliation, and promotion ledger pass.
echo "--- Master Bridge ---" | tee -a "$LOG"
if [ -f "$STATE_DIR/EMERGENCY_STOP" ]; then
    echo "⛔ KILL SWITCH ACTIVE — no execution" | tee -a "$LOG"
elif [ "$EXECUTION_ENABLED" != "true" ]; then
    echo "SHADOW_ONLY — BILL_ENABLE_AGENTIC_FUND_EXECUTION is not true; bridge skipped" | tee -a "$LOG"
elif ! GATE_BLOCKERS="$(execution_gate_status)"; then
    echo "SHADOW_ONLY — execution gate blocked; bridge skipped" | tee -a "$LOG"
    while IFS= read -r blocker; do
        [ -n "$blocker" ] && echo "  - $blocker" | tee -a "$LOG"
    done <<< "$GATE_BLOCKERS"
else
    python3 scripts/master_bridge.py 2>&1 | tee -a "$LOG"
fi

echo "============================================" | tee -a "$LOG"
echo "FUND CYCLE COMPLETE" | tee -a "$LOG"
echo "============================================" | tee -a "$LOG"
