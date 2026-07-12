Daily morning operator sweep for the Bill/Hedge agentic fund (campaign to 2026-06-22). Work in /Users/brain/hedge. Be token-frugal: under ~15 tool calls when healthy, no subagents unless something is deeply broken.
1. Run `.venv/bin/python scripts/founder_quant_cto_metaprompt.py >/dev/null && python3 -c "import json; [print(e['status'].upper(),e['id'],'->',e['nextCommand']) for e in json.load(open('.rumbling-hedge/state/founder-quant-cto-metaprompt.latest.json'))['edgeCompoundingChecklist']]"`. Repair any BROKEN link using its nextCommand.
   HARD RULE: NEVER unload, rename, rewrite, or disable the launchd plist. Do not resume, authenticate,
   force-refresh, or open any ProjectX/TopstepX broker session while
   `.rumbling-hedge/state/topstep-session-safety.latest.json` has
   `pauseBrokerTouchingProofs=true`. Reports, fallback research data, and plans are allowed;
   broker-session/config changes are not.
   NOTE: the realtime-bridge launchd service (com.agentpay.bill.realtime-bridge) stays ENABLED
   but with BILL_TOPSTEP_REALTIME_CRON_ENABLED=false and BILL_DOM_CAPTURE_ENABLED=false —
   standing fix for TopstepX "multiple sessions detected" (2026-06-10 incident).
   Yahoo/TradingView fallback data may keep the research display current, but it remains
   `execution_grade=false`. Never force-refresh `topstep_auth_cache.py` or run a Topstep proof
   merely to turn a dashboard check green. Only after the operator confirms the platform warning
   is gone may the bounded read-only clearance command be run with all execution flags false.
2. Check ~/.hermes/cron/jobs.json. Keep `master-strategy-bridge`, `topstep-demo-watchdog`,
   `topstep-demo-fill-check`, `topstep-lanes-monitor`, and `es-orb-lane-b` PAUSED while session
   safety is active. For non-broker research producers (`futures-data-refresh`,
   `signal-quality-producers`), report unexpected pauses; do not change scheduler state without
   explicit approval or a current daily-plan instruction.
3. Verify today's plan ~/Documents/memorybrain/Agent-Hermes/daily/$(date +%F)-bill-trading-plan.md exists with `BILL_ROUTE_APPROVAL: APPROVED` and `BROKER_RECONCILIATION: GREEN` control lines.
   EVIDENCE for session approvals (docs/research/2026-06-11-session-rr-options-research.md, committed):
   London ORB OOS PF 0.54 and Asia 0.46 as executed live — both 2026-06 campaign losses were
   non-NY-session entries; NQ ORB 3m NY brackets validated OOS PF 2.92. ES ORB 15m loses with
   OCO brackets (PF 0.09-0.73) and is only verified with 4-bar time exits — surface this before
   approving BILL_LONDON/ASIA_ROUTE_APPROVAL or BILL_LANE_B_ROUTE_APPROVAL; the call is the
   operator's, the plan must cite this evidence either way. If missing: write it (mirror 2026-06-10 structure; weekday sizing Tue=full, Wed/Fri=half) ONLY when `npm run bill:live-readiness-gate` shows readyForDemoExpansion=true AND topstep-100k-monitor status OK AND broker reconciliation flat. Otherwise write BILL_ROUTE_APPROVAL: BLOCKED plus the reason. Never approve past a red gate.
4. `npm run goal` — fix only operational blockers (freshness, crons); leave evidence-gated research blockers alone.
5. Append a <=5-line morning status to today's plan: gate state, blocker count, checklist greens, repairs made.
