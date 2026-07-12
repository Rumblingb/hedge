#!/bin/bash
# Brain Tick — writes system state to Obsidian daily note every 15min
# Reads state files directly. No HTTP. Research-only. No execution authority.
set -euo pipefail

export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false
export RH_TOPSTEP_READ_ONLY=true
export RH_LIVE_EXECUTION_ENABLED=false
export PREDICTION_LIVE_EXECUTION_ENABLED=false

DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M)
VAULT="/Users/brain/Documents/memorybrain/Agent-Hermes/daily/${DATE}.md"
STATE="/Users/brain/hedge/.rumbling-hedge/state"
LEGACY="/Users/brain/.rumbling-hedge/state"
STATEDIR="$STATE"
mkdir -p "$(dirname "$VAULT")"

# Prefer canonical state, fall back to legacy
for dir in "$STATE" "$LEGACY"; do
    [ -f "$dir/bill-runtime-architecture-audit.latest.json" ] && STATEDIR="$dir" && break
done

# Extract key facts
AUDIT=$(python3 -c "
import json
try:
    d = json.load(open('$STATEDIR/bill-runtime-architecture-audit.latest.json'))
    print(f\"{d.get('decision','?')}|exec={d.get('readyForExecution',False)}|demo={d.get('readyForDemoExpansion',False)}\")
except: print('?|?|?')
" 2>/dev/null)

PREFLIGHT=$(python3 -c "
import json
try:
    d = json.load(open('$STATEDIR/realtime-data-preflight.latest.json'))
    print(f\"{d.get('decision','?')}|grade={d.get('readyForExecutionData',False)}\")
except: print('?|?')
" 2>/dev/null)

# Append to daily note
echo "" >> "$VAULT"
echo "## 🧠 Brain Tick — ${TIME} BST" >> "$VAULT"
echo "- Audit: ${AUDIT} | Data: ${PREFLIGHT}" >> "$VAULT"
echo "- State: ${STATEDIR}" >> "$VAULT"
