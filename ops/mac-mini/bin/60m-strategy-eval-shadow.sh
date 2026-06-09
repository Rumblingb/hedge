#!/usr/bin/env bash
set -euo pipefail

cd /Users/brain/hedge

CSV_PATH="${BILL_60M_EVAL_CSV_PATH:-data/free/ALL-6MARKETS-60m-60d-normalized.csv}"
STATE_PATH="${BILL_60M_EVAL_STATE_PATH:-.rumbling-hedge/state/60m-signals-latest.json}"
TMP_PATH="${STATE_PATH}.tmp"

mkdir -p "$(dirname "$STATE_PATH")"

npx tsx scripts/probe-60m-signals.ts "$CSV_PATH" > "$TMP_PATH"

# GUARD: if all signals are null, write minimal state and skip overwrite
NULL_COUNT=$(python3 -c "
import json
d = json.load(open('$TMP_PATH'))
results = d.get('results', [])
real = [r for r in results if r.get('signal')]
print(len(results) - len(real))
")
TOTAL_COUNT=$(python3 -c "
import json
d = json.load(open('$TMP_PATH'))
print(len(d.get('results', [])))
")

if [ "$NULL_COUNT" -eq "$TOTAL_COUNT" ] && [ "$TOTAL_COUNT" -gt 0 ]; then
  # All signals null — write minimal no-signal state, don't pollute arbitration
  python3 -c "
import json
json.dump({
  'researchOnly': True,
  'advisoryOnly': True,
  'writesOrders': False,
  'touchesBroker': False,
  'tradableSignal': False,
  'promotedForExecution': False,
  'readyForExecution': False,
  'executionRole': 'diagnostic_only',
  'executionBlockReason': 'probe-output-research-only',
  'results': [],
  'latestBars': json.load(open('$TMP_PATH')).get('latestBars', {}),
  'note': 'All signals null — no actionable output this tick',
}, open('$TMP_PATH', 'w'), indent=2)
"
fi

mv "$TMP_PATH" "$STATE_PATH"

python3 - "$STATE_PATH" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())
signals = [row for row in data.get("results", []) if row.get("signal")]
print(json.dumps({
    "status": "ok",
    "statePath": str(path),
    "signalCount": len(signals),
    "latestBars": data.get("latestBars", {}),
    "execution": "shadow_only",
    "writesOrders": False,
}, sort_keys=True))
PY
