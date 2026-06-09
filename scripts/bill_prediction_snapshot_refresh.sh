#!/bin/bash
# Refresh polymarket prediction snapshot — keeps CLOB recorder terms fresh.
set -euo pipefail
cd /Users/brain/hedge
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Refreshing prediction snapshot (500 markets)..."
npx tsx src/cli.ts prediction-collect polymarket 500 .rumbling-hedge/runtime/prediction/latest-combined-snapshot.json
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Snapshot refresh complete."
