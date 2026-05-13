# Bill/Hedge Consolidation Audit — 2026-05-13

## Objective

Consolidate Bill/Hedge into one canonical no-data-loss runtime, preserve worktree/HDD/prediction-market research assets, and fix critical orchestration/data-path holes so the system can safely progress toward demo/paper compounding.

## Prompt-To-Artifact Checklist

| Requirement | Evidence | Status |
| --- | --- | --- |
| One canonical worktree | `/Users/brain/hedge` is active runtime/source; `master` contains newer commits than `codex/goal-live-market-readiness`. | Covered |
| Do not lose other worktrees | `/Users/brain/worktrees/hedge-goal-live` is kept harvest-only; no files deleted. | Covered |
| Preserve HDD futures data | Cold futures root recorded as `/Volumes/Seagate Expansion Drive/rumbling-hedge/data/free/free`; wrappers fall back there when SSD CSV paths are missing. | Covered |
| Preserve prediction-market research data | Prediction analysis root recorded as `/Volumes/Seagate Expansion Drive/rumbling-hedge-cold/prediction-market-analysis`; count observed at 15,116 files. | Covered |
| Preserve existing PM edges/fills | Canonicalization ledger names `.rumbling-hedge/state/prediction-edge-intake.latest.json` and `.rumbling-hedge/runtime/prediction/fills.jsonl` as first-class custody trails. | Covered |
| Fix data-path hole | `_bill-common.sh` and `strategy-lab.mjs` resolve missing hot CSVs to Seagate paths. | Covered |
| Fix Hermes cron noise/path drift | Hermes `daily_oos_rolling`, `hourly_health`, and `bill-demo-eod-execution` use local deterministic scripts instead of prompt-style commands. | Covered |
| Keep 16GB Mac Mini bounded | Secure Bill env restored `BILL_STRATEGY_LAB_FULL_EVERY_NTH_RUN=4`; bounded strategy-lab pass no longer forces full factory every cycle. | Covered |
| Preserve founder PM micro-live intent | Prediction live routing is distinguished from full live and capped as a micro-sandbox at `BILL_PREDICTION_LIVE_MAX_STAKE=2`. | Covered |
| Verify Topstep demo adapter safety | ProjectX demo test now covers entry plus separate SL/TP protective orders; duplicate order-search bug removed. | Covered |
| Preserve Obsidian project map | `/Users/brain/Documents/memorybrain/Agent-Shared/Fleet/04-bill-hedge/README.md` points to canonical repo, Codex context, goal-live, OpenClaw retired Bill memory, and HDD roots. | Covered |
| Harvest goal-live useful assets | High-value modules were compared; most are already identical in canonical. Three source diffs are older/weaker than canonical and intentionally not imported. | Partially covered |
| Import retired OpenClaw memory | `.rumbling-hedge/research/openclaw-retired/intake-card.latest.md` and `.json` distill retired Bill memories without reactivating old OpenClaw runtime. | Covered |
| Clean source custody | Working tree still has intentional uncommitted source changes from this repair pass. | Missing |
| Prove edge/profitability | Not achieved; current gates still block promotion due thin OOS, zero paper candidates, stale COT, degraded dealer gamma. | Not a claimed deliverable |

## Goal-Live Harvest Decision

Keep `/Users/brain/worktrees/hedge-goal-live` for reference. Do not make it canonical.

| Path | Comparison | Decision |
| --- | --- | --- |
| `src/engine/riskPolicyGuard.ts` | Same as canonical | Already preserved |
| `src/engine/strategyResearchContracts.ts` | Same as canonical | Already preserved |
| `src/engine/signalDecayLedger.ts` | Same as canonical | Already preserved |
| `src/engine/cashflowBoard.ts` | Same as canonical | Already preserved |
| `src/engine/macroConditionedPolicy.ts` | Same as canonical | Already preserved |
| `tests/edgeForensics.test.ts` | Same as canonical | Already preserved |
| `tests/riskPolicyGuard.test.ts` | Same as canonical | Already preserved |
| `tests/strategyResearchContracts.test.ts` | Same as canonical | Already preserved |
| `tests/freeMacroContext.test.ts` | Same as canonical | Already preserved |
| `src/engine/edgeForensics.ts` | Different; goal-live lacks canonical review-wrapper support | Keep canonical |
| `src/engine/walkforwardMatrix.ts` | Different; goal-live lacks canonical max-profile limiter | Keep canonical |
| `tests/walkforwardMatrix.test.ts` | Different only because goal-live lacks max-profile argument coverage | Keep canonical |
| `src/research/freeMacroContext.ts` | Different mostly formatting; canonical is newer and passes tests | Keep canonical |
| `data/research/macro/free-macro-context.latest.csv` | Different runtime data snapshot | Preserve both; do not treat as source |

## Current Remaining Blockers

- Source is not yet committed/pushed.
- OpenClaw retired Bill memories are distilled into canonical research cards, but the card is a custody/intake artifact; it is not yet a fully automated parser.
- Live-readiness remains blocked because evidence is weak, not because paths are missing; prediction micro-live is capped separately and must not be treated as full live-readiness.
- SSD headroom remains low even though heavy futures and PM corpora are now on HDD.
- COT is stale and dealer gamma remains degraded, so positioning/gamma-conditioned promotion must remain blocked.

## Next Concrete Step

Keep consolidating source custody: commit or stash the repair pass, then add a small parser that hashes retired OpenClaw memory files and emits deduped strategy hypotheses or no-edge entries.
