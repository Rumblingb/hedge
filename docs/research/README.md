# Bill Research Library

This folder is the canonical research handoff for Bill/Hermes agents.

Start here:

- `bill-corpus-audit-2026-05-26.md` — map of local/Obsidian/Hermes/Seagate artifacts.
- `bill-fund-os-completion-audit-2026-05-26.md` — prompt-to-artifact checklist and current blockers.
- `EVIDENCE_CARD_TEMPLATE.md` — required format before any idea can be promoted.
- `../BILL_FUND_OS_PHASE3_EXECUTION_FIREWALL_2026_05_26.md` — current safety posture, disabled execution paths, and reopen conditions.
- `../BILL_FUND_OS_PHASE2_2026_05_26.md` — current operating model and execution separation rules.
- `../BILL_HERMES_FINANCIAL_MARKETS_AUDIT_2026_05_26.md` — keep/kill/rebuild audit.
- `../TOPSTEP_CLOSED_LOOP_FRAMEWORK_PLAN_2026_05_26.md` — month-long Topstep demo framework.

Agent rule:

Research notes are not evidence. Evidence requires a dataset, command, output artifact, OOS result, and promotion decision.

Run the completion audit before changing trading automation:

```bash
npm run bill:fund-os-completion-audit
```

Expected current result: `HANDOFF_COMPLETE_TRADING_BLOCKED`. That means the handoff is clean enough for agents to use, while trading expansion remains blocked by OOS/live-readiness evidence.

Execution rule:

Do not route, size, or confirm trades from this folder. Execution is only through the guarded Topstep demo bridge after promotion gates pass.

Current posture:

- 15m data has been refreshed and normalized, but 15m strategies are still research-only.
- Legacy LucidFlex/PickMyTrade scripts are shadow-only unless explicitly enabled by env flags.
- The latest walk-forward matrix rejects the current strategy profile set. Treat that as contrary evidence, not a failure to be hand-waved away.
