#!/bin/bash
# Refresh the public prediction snapshot and its no-lookahead evidence chain.
set -euo pipefail
cd /Users/brain/hedge

export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false
export RH_TOPSTEP_READ_ONLY=true
export RH_LIVE_EXECUTION_ENABLED=false

run_quiet() {
  npm run --silent "$1" >/dev/null
}

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Refreshing public prediction evidence..."
npx tsx src/cli.ts prediction-collect polymarket 500 .rumbling-hedge/runtime/prediction/latest-combined-snapshot.json >/dev/null
run_quiet bill:prediction-category-drilldown
run_quiet bill:prediction-narrow-scan
run_quiet bill:prediction-event-news-rss
run_quiet bill:prediction-event-market-mapping-plan
run_quiet bill:prediction-event-timestamp-dataset
run_quiet bill:prediction-event-clob-capture-targets
run_quiet bill:prediction-event-lag-replay

complete_events=$(jq -r '.completeEventCount // 0' .rumbling-hedge/state/prediction-event-lag-replay.latest.json)
if [[ "$complete_events" =~ ^[0-9]+$ ]] && (( complete_events > 0 )); then
  run_quiet bill:prediction-event-lag-sensitivity
  run_quiet bill:prediction-event-lag-watch-review
  run_quiet bill:prediction-event-lag-manual-review
  run_quiet bill:prediction-event-mapping-refinement
fi

run_quiet bill:prediction-event-paper-promotion-gate
run_quiet bill:prediction-evidence-triage
run_quiet bill:goal-completion-audit

jq -cn \
  --slurpfile recorder .rumbling-hedge/state/polymarket-clob-recorder.latest.json \
  --slurpfile mapping .rumbling-hedge/state/prediction-event-market-mapping-plan.latest.json \
  --slurpfile replay .rumbling-hedge/state/prediction-event-lag-replay.latest.json \
  --slurpfile paper .rumbling-hedge/state/prediction-event-paper-promotion-gate.latest.json \
  '{wakeAgent:false,status:"ok",researchOnly:true,writesOrders:false,touchesBroker:false,recorderStatus:$recorder[0].status,mappingDecision:$mapping[0].decision,mappingCandidates:$mapping[0].candidateCount,completeEvents:$replay[0].completeEventCount,completeWindows:$replay[0].completeWindowCount,paperReady:$paper[0].readyForPaper}'
