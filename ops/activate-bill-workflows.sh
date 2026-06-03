#!/usr/bin/env bash
set -euo pipefail

DEFAULT_DB_PATH="/Users/brain/.n8n/database.sqlite"
DB_PATH="${N8N_DB_PATH:-$DEFAULT_DB_PATH}"
N8N_URL="${N8N_URL:-http://localhost:5678}"
TODAY="$(TZ="${BILL_TRADING_TIMEZONE:-Europe/London}" date +%F)"
DAILY_PLAN="${BILL_DAILY_PLAN_PATH:-/Users/brain/Documents/memorybrain/Agent-Hermes/daily/${TODAY}-bill-trading-plan.md}"
APPLY="false"

if [[ "${1:-}" == "--apply" ]]; then
  APPLY="true"
fi

echo "Bill n8n workflow activation helper"
echo "===================================="
echo
echo "This script is operator-facing. It does not use SSH, MCP, or the n8n API."
echo "Default mode prints the exact workflows and manual UI steps."
echo "Any workflow-local APPROVED value is not BILL_ROUTE_APPROVAL: APPROVED."
echo

if [[ ! -f "$DB_PATH" ]]; then
  echo "n8n database not found: $DB_PATH"
  echo "Open $N8N_URL/workflows and search for Bill, Trading, Topstep, or Gengar workflows manually."
  exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "sqlite3 is required to inspect local workflow IDs."
  exit 1
fi

WORKFLOWS="$(sqlite3 -separator $'\t' "$DB_PATH" \
  "select id,name,active from workflow_entity where lower(name) like '%bill%' or lower(name) like '%trading%' or lower(name) like '%topstep%' or lower(name) like '%gengar%' order by name;")"

if [[ -z "$WORKFLOWS" ]]; then
  echo "No Bill/Trading/Topstep/Gengar workflows found in $DB_PATH."
  echo "Manual fallback: open $N8N_URL/workflows and inspect imported workflow folders."
  exit 0
fi

echo "Detected workflows:"
echo "$WORKFLOWS" | while IFS=$'\t' read -r id name active; do
  status="inactive"
  [[ "$active" == "1" ]] && status="active"
  echo "- $name"
  echo "  id: $id"
  echo "  status: $status"
done
echo

echo "Previously observed Bill workflows from n8n event logs:"
if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY'
import glob
import json
from pathlib import Path

seen = {}
terms = ("bill", "trading", "topstep", "gengar")
for path in sorted(glob.glob("/Users/brain/.n8n/n8nEventLog*.log")):
    log_path = Path(path)
    with log_path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - 2_000_000))
        text = handle.read().decode(errors="ignore")
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload") or {}
        name = str(payload.get("workflowName") or "")
        workflow_id = str(payload.get("workflowId") or "")
        if not workflow_id or not any(term in name.lower() or term in workflow_id.lower() for term in terms):
            continue
        current = seen.get(workflow_id)
        record = {
            "id": workflow_id,
            "name": name,
            "lastEvent": event.get("eventName"),
            "lastSeen": event.get("ts"),
        }
        if current is None or str(record["lastSeen"]) > str(current["lastSeen"]):
            seen[workflow_id] = record

if not seen:
    print("- none found in /Users/brain/.n8n/n8nEventLog*.log")
else:
    for record in sorted(seen.values(), key=lambda item: item["name"].lower()):
        print(f"- {record['name']}")
        print(f"  id: {record['id']}")
        print(f"  last_event: {record['lastEvent']}")
        print(f"  last_seen: {record['lastSeen']}")
PY
else
  echo "- python3 unavailable; skipping event-log inventory"
fi
echo
echo "If a workflow appears in event logs or Obsidian but not in the current DB list,"
echo "treat it as missing from this n8n database/runtime. Import or recreate it before"
echo "trying to activate it."
echo

echo "Manual activation path:"
echo "1. Open $N8N_URL/workflows"
echo "2. Search each workflow name above"
echo "3. Open workflow -> click the Active toggle -> confirm it says Active"
echo "4. Run this script again to verify active=1"
echo

if [[ "$APPLY" != "true" ]]; then
  echo "Dry run only. To attempt local n8n CLI activation, run:"
  echo "  N8N_DB_PATH=/path/to/current/n8n.sqlite BILL_N8N_WORKFLOW_ACTIVATION_APPLY_OK=I_UNDERSTAND_N8N_APPROVED_IS_NOT_TRADE_APPROVAL $0 --apply"
  echo "The daily plan must also contain: N8N_WORKFLOW_CHANGE_APPROVAL: APPROVED"
  exit 0
fi

if [[ "$DB_PATH" == "$DEFAULT_DB_PATH" && -z "${N8N_DB_PATH:-}" ]]; then
  echo "Refusing --apply: N8N_DB_PATH was not explicitly set."
  echo "The default SQLite path can be stale when the active n8n runtime uses another backend."
  exit 1
fi

if [[ "${BILL_N8N_WORKFLOW_ACTIVATION_APPLY_OK:-}" != "I_UNDERSTAND_N8N_APPROVED_IS_NOT_TRADE_APPROVAL" ]]; then
  echo "Refusing --apply: set BILL_N8N_WORKFLOW_ACTIVATION_APPLY_OK=I_UNDERSTAND_N8N_APPROVED_IS_NOT_TRADE_APPROVAL."
  echo "This prevents confusing n8n workflow-local approval with Bill route approval."
  exit 1
fi

if [[ ! -f "$DAILY_PLAN" ]] || ! grep -q '^N8N_WORKFLOW_CHANGE_APPROVAL: APPROVED$' "$DAILY_PLAN"; then
  echo "Refusing --apply: today's daily plan does not approve n8n workflow activation changes."
  echo "Expected control line in $DAILY_PLAN:"
  echo "N8N_WORKFLOW_CHANGE_APPROVAL: APPROVED"
  exit 1
fi

if ! command -v n8n >/dev/null 2>&1; then
  echo "n8n CLI is not on PATH. Use the manual activation path above."
  exit 1
fi

echo "Attempting n8n CLI activation for inactive detected workflows..."
echo "$WORKFLOWS" | while IFS=$'\t' read -r id name active; do
  if [[ "$active" == "1" ]]; then
    echo "Already active: $name ($id)"
    continue
  fi
  echo "Activating: $name ($id)"
  n8n update:workflow --id="$id" --active=true
done

echo
echo "Re-run without --apply to verify statuses."
