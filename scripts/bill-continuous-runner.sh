#!/bin/bash
# Bill Continuous Runner - 24/7 automation
# Legacy fallback runner. Prefer ops/mac-mini/bin/bill-install-launchd for 24/7 operation.

set -euo pipefail

script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BILL_ROOT="$(CDPATH='' cd -- "$script_dir/.." && pwd)"
source "$BILL_ROOT/ops/mac-mini/bin/_bill-common.sh"
load_bill_env

if [[ "${BILL_ALLOW_LEGACY_CONTINUOUS_RUNNER:-false}" != "true" ]]; then
    cat >&2 <<'EOF'
Bill continuous runner is disabled by default.

Use ops/mac-mini/bin/bill-install-launchd for the canonical 24/7 supervisor.
If you intentionally need this legacy fallback, set BILL_ALLOW_LEGACY_CONTINUOUS_RUNNER=true.
EOF
    exit 2
fi

LOG_DIR="$BILL_ROOT/.rumbling-hedge/logs"
STATE_DIR="$BILL_ROOT/.rumbling-hedge/state"

ensure_bill_runtime_dirs
mkdir -p "$STATE_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "===== Bill Continuous Runner Started ====="

# Function to run a command with retry and logging
run_bill_cmd() {
    local name="$1"
    shift
    local cmd="$*"
    local timestamp=$(date +%Y%m%d-%H%M%S)
    local logfile="$LOG_DIR/bill-${name}-${timestamp}.log"
    
    log "Running: $cmd"
    if $cmd >> "$logfile" 2>&1; then
        log "SUCCESS: $name"
        return 0
    else
        log "FAILED: $name - check $logfile"
        return 1
    fi
}

# Track 1: Prediction Market Collection (every 5 min)
prediction_loop() {
    while true; do
        run_bill_cmd "prediction-collect" npm run bill:prediction-collect
        log "Sleeping 5m before next prediction collection..."
        sleep 300
    done
}

# Track 2: Prediction Review (every 5 min)
prediction_review_loop() {
    while true; do
        run_bill_cmd "prediction-review" npm run bill:prediction-review
        log "Sleeping 5m before next prediction review..."
        sleep 300
    done
}

# Track 3: Research Collection (every 30 min)
research_loop() {
    while true; do
        run_bill_cmd "research-collect" npm run bill:research-collect
        run_bill_cmd "research-report" npm run bill:research-report
        log "Sleeping 30m before next research cycle..."
        sleep 1800
    done
}

# Track 4: Futures Demo (every 30 min)
futures_loop() {
    while true; do
        run_bill_cmd "paper-loop" npm run bill:paper-loop
        log "Sleeping 30m before next futures demo..."
        sleep 1800
    done
}

# Track 5: Health Check (every 15 min)
health_loop() {
    while true; do
        run_bill_cmd "health" npm run bill:health
        log "Sleeping 15m before next health check..."
        sleep 900
    done
}

# Track 6: Market Track Status (every 30 min)
track_status_loop() {
    while true; do
        run_bill_cmd "market-track-status" npm run bill:market-track-status
        log "Sleeping 30m before next track status..."
        sleep 1800
    done
}

# Main: Run all tracks in background
log "Starting all Bill tracks in parallel..."

# Start all tracks in background
prediction_loop &
PRED_COLLECT_PID=$!

prediction_review_loop &
PRED_REVIEW_PID=$!

research_loop &
RESEARCH_PID=$!

futures_loop &
FUTURES_PID=$!

health_loop &
HEALTH_PID=$!

track_status_loop &
TRACK_PID=$!

log "All tracks started:"
log "  Prediction Collect: $PRED_COLLECT_PID"
log "  Prediction Review: $PRED_REVIEW_PID"  
log "  Research: $RESEARCH_PID"
log "  Futures Demo: $FUTURES_PID"
log "  Health Monitor: $HEALTH_PID"
log "  Track Status: $TRACK_PID"

# Wait for all (or until interrupted)
cleanup() {
    log "Stopping Bill continuous runner..."
    kill $PRED_COLLECT_PID $PRED_REVIEW_PID $RESEARCH_PID $FUTURES_PID $HEALTH_PID $TRACK_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

wait
