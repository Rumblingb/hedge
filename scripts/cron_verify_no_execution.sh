#!/bin/bash
# Silent on pass, outputs JSON on fail
set -euo pipefail

export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false
export RH_TOPSTEP_READ_ONLY=true
export RH_LIVE_EXECUTION_ENABLED=false
export PREDICTION_LIVE_EXECUTION_ENABLED=false

cd /Users/brain/hedge
RESULT=$(python3 scripts/verify_no_execution_enabled_processes.py 2>&1)
if echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('candidateCount',1)==0 else 1)" 2>/dev/null; then
    exit 0
else
    echo "FAILED: verify_no_execution_enabled_processes"
    echo "$RESULT"
    exit 1
fi
