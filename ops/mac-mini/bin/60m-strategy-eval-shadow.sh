#!/usr/bin/env bash
set -euo pipefail

cd /Users/brain/hedge

CSV_PATH="${BILL_60M_EVAL_CSV_PATH:-data/free/ALL-6MARKETS-60m-60d-normalized.csv}"
STATE_PATH="${BILL_60M_EVAL_STATE_PATH:-.rumbling-hedge/state/60m-signals-latest.json}"
TMP_PATH="${STATE_PATH}.tmp"

mkdir -p "$(dirname "$STATE_PATH")"

npx tsx scripts/probe-60m-signals.ts "$CSV_PATH" > "$TMP_PATH"
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
