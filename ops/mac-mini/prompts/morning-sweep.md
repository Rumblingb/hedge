Daily morning operator sweep for the Bill/Hedge agentic fund (campaign to 2026-06-22). Work in /Users/brain/hedge. Be token-frugal: under ~15 tool calls when healthy, no subagents unless something is deeply broken.
1. Run `.venv/bin/python scripts/founder_quant_cto_metaprompt.py >/dev/null && python3 -c "import json; [print(e['status'].upper(),e['id'],'->',e['nextCommand']) for e in json.load(open('.rumbling-hedge/state/founder-quant-cto-metaprompt.latest.json'))['edgeCompoundingChecklist']]"`. Repair any BROKEN link using its nextCommand.
   NOTE: Do NOT re-enable the realtime-bridge launchd service (com.agentpay.bill.realtime-bridge).
   It was disabled on 2026-06-10 because BILL_TOPSTEP_REALTIME_CRON_ENABLED=true caused
   TopstepX "multiple sessions detected" warnings. The plist at
   ~/Library/LaunchAgents/com.agentpay.bill.realtime-bridge.plist has both flags set to false.
   Only re-enable after explicit operator approval.
2. Check ~/.hermes/cron/jobs.json for paused/disabled trading crons (master-strategy-bridge, topstep-demo-watchdog, topstep-demo-fill-check, topstep-bar-archive-accumulate, futures-data-refresh, signal-quality-producers). Resume any paused one with `hermes cron resume <id>` UNLESS today's daily plan documents a reason for the pause.
3. Verify today's plan ~/Documents/memorybrain/Agent-Hermes/daily/$(date +%F)-bill-trading-plan.md exists with `BILL_ROUTE_APPROVAL: APPROVED` and `BROKER_RECONCILIATION: GREEN` control lines. If missing: write it (mirror 2026-06-10 structure; weekday sizing Tue=full, Wed/Fri=half) ONLY when `npm run bill:live-readiness-gate` shows readyForDemoExpansion=true AND topstep-100k-monitor status OK AND broker reconciliation flat. Otherwise write BILL_ROUTE_APPROVAL: BLOCKED plus the reason. Never approve past a red gate.
4. `npm run goal` — fix only operational blockers (freshness, crons); leave evidence-gated research blockers alone.
5. Append a <=5-line morning status to today's plan: gate state, blocker count, checklist greens, repairs made.
