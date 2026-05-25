#!/bin/bash
# ============================================================
# GENGAR GO-LIVE SETUP — Run once before June 1
# ============================================================
# This script prepares Gengar for live Polymarket trading.
# 
# REQUIREMENTS BEFORE RUNNING:
# 1. Fund wallet 0x25D1...99C with ~50 MATIC for gas
# 2. Fund wallet with ~$200 USDC.e for first trades
# 3. Set POLYMARKET_PRIVATE_KEY in bill.env
# ============================================================

set -euo pipefail
cd /Users/brain/hedge

echo "=== GENGAR PRE-FLIGHT CHECK ==="

# 1. Check wallet balance
echo "--- Wallet check ---"
BALANCE=$(curl -s "https://polygon-rpc.com" \
  -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_getBalance","params":["0x25D10ACCAF13021fbE7648Cbe202C2273408199C","latest"],"id":1}' \
  | python3 -c "import sys,json; print(int(json.load(sys.stdin).get('result','0x0'),16)/1e18)" 2>/dev/null || echo "0")

echo "  MATIC balance: $BALANCE"
if [ "$(echo "$BALANCE < 5" | bc -l 2>/dev/null)" = "1" ] || [ "$BALANCE" = "0" ]; then
  echo "  ❌ Need at least 5 MATIC for gas"
  echo "  Send to: 0x25D10ACCAF13021fbE7648Cbe202C2273408199C"
fi

# 2. Check env vars
echo "--- Environment check ---"
for var in POLYMARKET_PRIVATE_KEY POLYMARKET_API_KEY POLYMARKET_API_SECRET POLYMARKET_API_PASSPHRASE; do
  if grep -q "$var" "/Users/brain/Library/Application Support/AgentPay/bill/bill.env" 2>/dev/null; then
    echo "  ✅ $var is set"
  else
    echo "  ❌ $var is NOT set"
  fi
done

# 3. Check RPC access
echo "--- RPC check ---"
curl -s -o /dev/null -w "%{http_code}" "https://polygon-rpc.com" -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' 2>/dev/null
echo " Polygon RPC"

# 4. Check execution watcher health
echo "--- Watcher check ---"
if pgrep -f gengarExecutionWatcher > /dev/null 2>&1; then
  echo "  ✅ Gengar execution watcher RUNNING"
  echo "  PID: $(pgrep -f gengarExecutionWatcher)"
  echo "  Rejected trades: $(cat .rumbling-hedge/state/gengar-execution.json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('totalRejected','?'))" 2>/dev/null || echo "?")"
else
  echo "  ❌ Gengar execution watcher NOT running"
fi

echo ""
echo "=== TO GO LIVE ==="
echo "1. Send 50 MATIC to 0x25D10ACCAF13021fbE7648Cbe202C2273408199C"
echo "2. Add to bill.env:"
echo "   POLYMARKET_PRIVATE_KEY=your_key"
echo "   POLYMARKET_API_KEY=your_api_key"
echo "   POLYMARKET_API_SECRET=your_api_secret"
echo "   POLYMARKET_API_PASSPHRASE=your_passphrase"
echo "3. Restart watcher: launchctl kickstart com.agentpay.bill.gengar-execution"
echo "4. OR kill && restart: pkill -f gengarExecution && bash ops/start-gengar-live.sh"
