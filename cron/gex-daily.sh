#!/bin/bash
# Daily GEX levels fetch — runs every trading day pre-market
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p ~/.rumbling-hedge/logs

echo "[$(date)] Starting GEX fetch..." >> ~/.rumbling-hedge/logs/gex_fetch.log
python3 scripts/fetch_gex_levels.py >> ~/.rumbling-hedge/logs/gex_fetch.log 2>&1
echo "[$(date)] GEX fetch complete" >> ~/.rumbling-hedge/logs/gex_fetch.log
