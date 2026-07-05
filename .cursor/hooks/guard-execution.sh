#!/bin/bash
# Flag shell commands that could arm live/demo execution — operator review, not auto-block.
set -euo pipefail

input=$(cat)
command=$(echo "$input" | jq -r '.command // empty')

if [[ -z "$command" ]]; then
  echo '{ "permission": "allow" }'
  exit 0
fi

if echo "$command" | grep -qE \
  'BILL_ENABLE_FUTURES_DEMO_EXECUTION=true|RH_LIVE_EXECUTION_ENABLED=true|RH_TOPSTEP_READ_ONLY=false|bill-prediction-execute|master_bridge\.py|topstep_demo_bridge|bill:kill-switch off'; then
  echo '{
    "permission": "ask",
    "user_message": "This command may arm Bill/Hermes execution. Confirm daily plan + broker gates are green.",
    "agent_message": "Execution-adjacent command flagged. Verify Obsidian daily plan approves orders and ops env (not secure env alone) matches intent."
  }'
  exit 0
fi

echo '{ "permission": "allow" }'
