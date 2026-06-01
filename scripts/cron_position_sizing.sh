#!/usr/bin/env bash
# Cron wrapper: position sizing engine
# Runs every 30 min during market hours (Mon-Fri 13:30-21:00 UTC)
# MUST run after drawdown_circuit_breaker.sh (depends on breaker state)
set -euo pipefail
cd /Users/brain/hedge
STATE_DIR="${BILL_STATE_DIR:-/Users/brain/hedge/.rumbling-hedge/state}"
python3 scripts/position_sizing_engine.py --state-dir "$STATE_DIR" --balance "${BILL_POSITION_SIZING_BALANCE:-104335}" > /dev/null 2>&1
