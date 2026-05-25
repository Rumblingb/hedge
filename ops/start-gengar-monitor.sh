#!/bin/bash
set -euo pipefail

cd /Users/brain/hedge

source /Users/brain/hedge/ops/mac-mini/env/bill.env 2>/dev/null || true
source "/Users/brain/Library/Application Support/AgentPay/bill/bill.env" 2>/dev/null || true

npx tsx src/prediction/gengarMonitor.ts 2>&1
