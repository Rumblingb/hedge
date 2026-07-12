#!/bin/bash
# Inject compact Bill/Hermes gate snapshot at session start (~500 tokens max).
set -euo pipefail

HEDGE="${HOME}/hedge"
STATE="${HEDGE}/.rumbling-hedge/state"
CTX="${HEDGE}/Agent-Codex/working-context.md"

jq_compact() {
  local f="$1"
  local q="$2"
  if [[ -f "$f" ]] && command -v jq >/dev/null 2>&1; then
    jq -c "$q" "$f" 2>/dev/null || echo "null"
  else
    echo "null"
  fi
}

topstep=$(jq_compact "${STATE}/topstep-100k-monitor.latest.json" '{status:.status, brokerFlat:.brokerFlat, blockers:(.blockers//[])}')
goal=$(jq_compact "${STATE}/bill-goal-completion-audit.latest.json" '{decision:.decision, blockedIds:.blockedIds, pass:(.checkCount - .blockedCount)}')
pred=$(jq_compact "${STATE}/prediction-review.latest.json" '{blockers:(.review.blockers//[]), paperCandidates:(.review.counts["paper-trade"]//0)}')
signal=$(jq_compact "${STATE}/master-signal.latest.json" '{id:.signal.strategyId, side:.signal.side, status:.signal.status}')

wc_snippet=""
if [[ -f "$CTX" ]]; then
  wc_snippet=$(head -n 20 "$CTX" | sed 's/"/\\"/g' | tr '\n' ' ')
fi

cat <<EOF
{
  "additional_context": "## Bill session snapshot (auto)\n- working-context: ${wc_snippet}\n- topstep: ${topstep}\n- goal-audit: ${goal}\n- prediction: ${pred}\n- master-signal: ${signal}\n\nRead Agent-Codex/working-context.md once. Use gitnexus_query for code. Default: execution locked."
}
EOF
