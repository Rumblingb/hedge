#!/usr/bin/env bash
# check_expiry.sh — Alerts user 1 day before subscription renewals
# Runs: daily via cron

# Check OpenRouter credits
RESULT=$(curl -s "https://openrouter.ai/api/v1/auth/key" \
  -H "Authorization: Bearer $(grep OPENROUTER_API_KEY ~/Library/Application\ Support/AgentPay/bill/bill.env 2>/dev/null | cut -d= -f2)" 2>/dev/null)

REMAINING=$(echo "$RESULT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    remaining = d.get('data', {}).get('limit_remaining')
    print(f'{float(remaining):.2f}' if remaining is not None else 'unknown')
except Exception:
    print('unknown')
" 2>/dev/null)

echo "OpenRouter remaining: \$$REMAINING"
echo ""

# Check Topstep renewal (due ~Jun 13)
TODAY=$(date +%s)
JUN13=$(date -j -f "%Y-%m-%d" "2026-06-13" +%s 2>/dev/null)
if [ "$JUN13" != "" ]; then
  DAYS_LEFT=$(( (JUN13 - TODAY) / 86400 ))
  if [ "$DAYS_LEFT" -eq 1 ]; then
    echo "⚠️ TOPSTEP RENEWAL TOMORROW (\$154.80)"
  elif [ "$DAYS_LEFT" -eq 7 ]; then
    echo "ℹ️ Topstep renewal in 7 days (\$154.80)"
  elif [ "$DAYS_LEFT" -le 0 ]; then
    echo "🔴 TOPSTEP RENEWAL OVERDUE!"
  else
    echo "Topstep renewal in $DAYS_LEFT days"
  fi
fi

echo ""
echo "Fund tracker: memorybrain/Agent-Shared/fund-tracker.md"
