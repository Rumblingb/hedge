#!/bin/bash
set -euo pipefail

cd /Users/brain/hedge

source /Users/brain/hedge/ops/mac-mini/env/bill.env 2>/dev/null || true
source "/Users/brain/Library/Application Support/AgentPay/bill/bill.env" 2>/dev/null || true

if [[ "${BILL_GENGAR_LIVE_EXECUTION_ENABLED:-false}" != "true" ]]; then
  echo "[gengar] Live execution is disabled; watcher will run in DRY_RUN mode."
fi

# Correct profile address: funder for Polymarket signatureType 3.
export POLYMARKET_PROFILE_ADDRESS="${POLYMARKET_PROFILE_ADDRESS:-0xaA5585AeB0708060565827FD1b94019E79b5546F}"
if [[ "${BILL_GENGAR_LIVE_EXECUTION_ENABLED:-false}" == "true" ]]; then
  : "${POLYMARKET_PRIVATE_KEY:?Set POLYMARKET_PRIVATE_KEY through a secure env source before enabling live Gengar execution}"
fi

# Keep profile-derived API credentials from bill.env when present. For
# signatureType 3, deriving from the EOA produces signer-scoped API creds that
# Polymarket rejects for profile/funder orders.

# Route CLOB traffic through local Tor if available. Axios honors HTTPS_PROXY.
if nc -z 127.0.0.1 9050 2>/dev/null; then
  export HTTPS_PROXY=socks5://127.0.0.1:9050
  echo "[gengar] Tor detected; routing via socks5://127.0.0.1:9050"
fi

npx tsx src/prediction/gengarExecutionWatcher.ts >> .rumbling-hedge/logs/gengar-execution.log 2>&1
