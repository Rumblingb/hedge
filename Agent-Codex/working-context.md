2026-07-05T14:00:00Z
- Co-founder sprint slice 2: strategy audit + HA feasibility + AI Scientist `seed_ideas.json` (3-queue)
- Strategy truth: 0 promotable; wq-vol-regime best Backtrader seed but 15m OOS netR -56.6; ORB/MA 60m no-edge
- HA: agent + TS reversal exist; bill-core has no HA; propose `--ha_confirm_gate` on experiment.py
- Dry-run: `experiment.py wq_vol_regime 60m-nq-3yr` → OOS PF 1.20 blocked (WF fold negative)

2026-07-05T13:00:00Z
- Commit f710a28e: Cursor bootstrap (.cursor rules/hooks, .cursorignore, .vscode, AGENTS.md)
- Co-founder sprint: Obsidian [[BILL-COFOUNDER-RESEARCH-SPRINT-2026-07-05]]; hub + compound ladder linked
- Obsidian sync OK → daily/2026-07-05-bill-trading-plan.md
- Execution posture: LOCKED — daily route approval BLOCKED, broker reconciliation UNKNOWN
- Seagate mount: absent → bill-prediction-forward-clob-capture cannot run
- SSD disk: ~3.4GB free (78%) — below recorder min-free-gb 20 preflight
- CFTC TFF refreshed (latest 2026-06-23)

## Gates (synced 2026-07-05)

| Gate | Status |
|------|--------|
| Goal audit | 24/28 pass; blocked: execution-locked, futures-demo-not-cleared, prediction-paper-not-cleared, source-hygiene-not-cleared |
| Prediction review | 0 watch/paper; no-edge ledger 14 entries, promotable 0 |
| Capital allocator | research-budget-only; £200 bankroll; all lanes budget=0 |
| Prop payout plan | needs-evidence |
| Topstep monitor | OK; hard blockers [] |
| Daily decision | No new Bill/Hermes orders approved |

## Default env (ops — scheduled safe)

- BILL_ENABLE_FUTURES_DEMO_EXECUTION=false
- RH_TOPSTEP_READ_ONLY=true
- RH_LIVE_EXECUTION_ENABLED=false

## Agent read order (token cheap)

1. This file
2. `.rumbling-hedge/state/<topic>.latest.json` (2–4 files max)
3. Obsidian hub + daily plan (after `npm run bill:obsidian-sync`)
4. GitNexus query for code navigation

## Active automations

- bill-prediction-forward-clob-capture: requires `/Volumes/Seagate Expansion Drive` mount + ≥20GB free
- 74 Hermes crons; master-strategy-bridge paused

## Compounding ladder

Obsidian: `Agent-Hermes/BILL-COMPOUND-LADDER-2026-07-05.md`
Sprint: `Agent-Hermes/BILL-COFOUNDER-RESEARCH-SPRINT-2026-07-05.md` (+ consulting→trade map, IB harvest, buy-rating sketch, localhost audit appended 2026-07-05)
Stage 0 now → Stage 1 prediction paper after CLOB + promotion gate

## Top research priorities (co-founder sprint)

1. Mount Seagate + forward CLOB capture during news windows
2. Free SSD via hermes-storage-audit (profiles/sessions archive)
3. Futures evidence triage — ORB + vol-regime one-variable
4. CFTC TFF regime filter as shadow overlay (data fresh)
5. Source hygiene manual review (3 items)

## Next commands

```
npm run bill:hermes-storage-audit
npm run bill:futures-evidence-triage
npm run bill:vol-regime-oos-15m
npm run bill:source-packet-review
npm run bill:obsidian-sync
```
