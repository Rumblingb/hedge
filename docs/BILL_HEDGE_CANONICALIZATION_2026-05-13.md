# Bill/Hedge Canonicalization Ledger — 2026-05-13

## Non-Deletion Rule

- Do not delete or retire any Bill/Hedge, OpenClaw, Hermes, Obsidian, Discord, HDD, Codex, or prediction-market asset until it has been inventoried and either imported, indexed, or explicitly marked redundant.
- Treat `/Users/brain/hedge` as the active runtime/source tree, but treat other trees as harvest sources until their useful diffs and memories are reconciled.
- Preserve live/demo execution traces, paper fills, prediction-market edges, no-edge ledgers, and strategy-factory artifacts even when the current gate blocks promotion.

## Canonical Runtime

- Active canonical source/runtime: `/Users/brain/hedge`.
- Active branch: `master`, currently ahead of `origin/master` and newer than `codex/goal-live-market-readiness`.
- Launchd/Hermes wrappers should load Bill env through `ops/mac-mini/bin/_bill-common.sh`, which now falls back missing hot CSV paths to HDD cold futures data.
- The source tree must stay source-first; large corpora, old logs, and heavy parquet/CSV datasets stay outside Git.

## Worktree Disposition

- Keep `/Users/brain/worktrees/hedge-goal-live` as a harvest-only worktree for now.
- Do not make `/Users/brain/worktrees/hedge-goal-live` canonical: its branch has no commits beyond canonical, but it contains local source diffs and untracked research files that must be selectively reviewed.
- High-value goal-live harvest candidates include walk-forward matrix, edge forensics, macro context, cashflow board, risk-policy guard, signal-decay ledger, strategy-research contracts, and their tests.
- Untracked goal-live CSVs are not source truth; equivalent/heavier datasets now exist on the Seagate HDD under the futures cold-data root.

## Data Custody

- Hot runtime/source stays on SSD under `/Users/brain/hedge`.
- Futures cold data root: `/Volumes/Seagate Expansion Drive/rumbling-hedge/data/free/free`.
- Prediction-market analysis root: `/Volumes/Seagate Expansion Drive/rumbling-hedge-cold/prediction-market-analysis`.
- Prediction-market compact research outputs remain under `/Users/brain/hedge/.rumbling-hedge/research/prediction-market-analysis`.
- The prediction-market cold root currently contains 15,116 files and must be preserved because it is the source for already-found PM edges and compounding research.

## Preserved Edge Sources

- Keep `.rumbling-hedge/state/prediction-edge-intake.latest.json` and `.rumbling-hedge/runtime/prediction/fills.jsonl` as the first-class custody trail for prediction-market edge and execution attempts.
- Keep OpenClaw retired Bill memories under `/Users/brain/.openclaw.retired-2026-05-12/workspace-bill/memory`; the current canonical intake card is `.rumbling-hedge/research/openclaw-retired/intake-card.latest.md`.
- Keep retired OpenClaw prediction snapshots under `/Users/brain/.openclaw.retired-2026-05-12/bases/hedge/data/prediction` until canonical PM ingestion explicitly references them.
- Treat Discord channels as context/memory, not as a runtime control surface; agents should post only when required by blockers, approvals, or concise status.
- Quarantine retired OpenClaw scripts that contain hard-coded social/Postiz credentials or live-ish profit claims. They are negative memory only; do not import or execute them. Examples include retired `connect-all.js`, `fix_postiz_redirects.js`, `execute-14percent-edge.js`, and “READY FOR LAUNCH” style live-execution notes.

## Runtime Fixes Applied

- Bill wrappers now resolve missing `data/free/*.csv` paths to the Seagate futures cold-data root when a matching filename exists.
- Bill wrappers now default `BILL_PREDICTION_MARKET_ANALYSIS_DATA_ROOT` to the Seagate prediction-market cold-data root when the secure env does not set it.
- Hermes `daily_oos_rolling`, `hourly_health`, and `bill-demo-eod-execution` have been converted from noisy prompt-style cron commands into local deterministic scripts that stay silent unless blockers are detected.
- Secure Bill env now points strategy-lab 30d/90d datasets at the quoted Seagate paths and restores `BILL_STRATEGY_LAB_FULL_EVERY_NTH_RUN=4` so full factory runs are staggered instead of burning the heavy slot every cycle.
- Secure Bill env now marks prediction-market live routing as a founder-approved micro-sandbox, capped at `BILL_PREDICTION_LIVE_MAX_STAKE=2`, while full live-readiness remains blocked by OOS/paper gates.
- ProjectX demo routing no longer performs a duplicate order-search request before sibling cleanup; the demo-order test now reflects market entry plus separate stop/take-profit protective orders.
- Tracked small `data/free` fixtures were restored into canonical Git working tree so source truth is no longer dirty from accidental fixture deletion.
- Researcher scheduler now falls back to canonical `config/researcher-targets.bill.json` and `config/researcher-policy.bill.json` when retired OpenClaw workspace files are missing, so Bill’s research lane does not fail just because OpenClaw was migrated.

## Next Harvest Order

1. Import or reject goal-live diffs one subsystem at a time, starting with `edgeForensics`, `walkforwardMatrix`, `riskPolicyGuard`, and `strategyResearchContracts`.
2. Add a compact OpenClaw retired-memory intake card so old validated/failed strategy notes are searchable without making retired OpenClaw the runtime.
3. Add a prediction-market edge custody board section that separates human/imported edges from scanner-generated paper candidates.
4. Keep Topstep demo and prediction micro-live gated by explicit risk limits; do not broaden strategy count until OOS/paper/demo evidence improves.
5. Build native Rust/C++ strategy core only after source/data custody is stable; native speed will not fix weak edge by itself.
