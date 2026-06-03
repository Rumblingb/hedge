#!/usr/bin/env bash
# Cron wrapper: drawdown circuit breaker
# Runs every 30 min during market hours (Mon-Fri 13:30-21:00 UTC)
set -euo pipefail
cd /Users/brain/hedge
STATE_DIR="${BILL_STATE_DIR:-/Users/brain/hedge/.rumbling-hedge/state}"
python3 scripts/drawdown_circuit_breaker.py --state-dir "$STATE_DIR" --balance "${BILL_DRAWDOWN_BALANCE:-104335}" > /dev/null 2>&1
