# Bill/Hermes Financial Markets Audit — 2026-05-26

## Current Posture

Bill/Hermes is not one system; it is three lanes that must stay isolated:

1. **Research lane** — Hermes researcher, Obsidian notes, YouTube/scholar/web targets, Rust sweeps, TS strategy factory, Backtrader research loop.
2. **Validation lane** — TS live-readiness gate, strategy zoo audit, prop-firm matrix, guardrails, broker/account reconciliation.
3. **Execution lane** — `scripts/master_bridge.py` emits one vetted signal; `/Users/brain/.hermes/scripts/topstep_demo_bridge.py` routes only to the Topstep demo account with atomic OCO brackets.

The separation rule is now explicit: research can write hypotheses and artifacts, but only the execution lane can submit orders, and only after guardrails and demo-account checks pass.

## Storage Actions Taken

The SSD was effectively full, which caused Hermes session writes to fail.

Moved to `/Volumes/Seagate Expansion Drive/hedge-data/local-archives/2026-05-26`:

- `/Users/brain/.hermes/state-snapshots` cold snapshots, 4.3 GB.
- `/Users/brain/hedge/data/external` duplicate external-alpha copy, 2.1 GB. Canonical paths already live in `/Users/brain/hedge/config/external_alpha_catalog.yaml`.
- `/Users/brain/.cache/huggingface`, 2.1 GB, replaced with a symlink to HDD so model research can still resolve cache paths.
- `/Users/brain/hedge/research-repos`, 856 MB, replaced with a symlink to HDD.

Removed:

- `/Users/brain/hedge/node_modules.broken`, 94 MB.

Current policy:

- SSD keeps hot source, hot state, small normalized CSVs, current logs, active venvs.
- HDD keeps raw external datasets, cloned reference repos, old state snapshots, cold archives, large model caches.
- Do not delete `/Users/brain/.hermes/state.db`; it is large but active state.

## Backtrader Research Lane

Added:

- `/Users/brain/hedge/scripts/backtrader_research_loop.py`
- `npm run bill:backtrader-research`

Backtrader is intentionally research-only:

- No broker credentials.
- No Topstep imports.
- No execution webhooks.
- Writes only to `.rumbling-hedge/state`, `.rumbling-hedge/backtrader/feeds`, and `.rumbling-hedge/backtrader/results`.

Default corpus:

- `ALL-6MARKETS-15m-60d-normalized.csv`
- `ALL-6MARKETS-30m-60d-normalized.csv`
- `ALL-6MARKETS-60m-60d-normalized.csv`

Default strategy coverage:

- `orb-breakout-15m`
- `orb-breakout-30m`
- `wq-trend-mom-30m`
- `wq-vol-regime-60m`

Current 108-row sweep:

- Command: `npm run bill:backtrader-research -- --contracts 1,2,3 --stop-points 12,16,20 --target-points 16,24,32`
- Output: `/Users/brain/hedge/.rumbling-hedge/state/backtrader-research.latest.json`
- Best research row: `wq-vol-regime-60m`, 1 contract, 16-point stop, 32-point target, 92 closed trades, 44.57% WR, +32.4406R normalized, max DD 1.41%.

Interpretation:

- This does not replace the Rust 685-row sweep. It is a second engine to catch broker-style stop/target behavior and one-variable changes.
- `wq-vol-regime-60m` remains the strongest candidate across engines.
- ORB became negative under this Backtrader OCO-style sweep, while Rust time-exit sweeps showed strong R. That is a useful contradiction, not a failure. ORB should not be expanded in demo until entry timing, session range definition, and stop/target model are reconciled.

## Keep

- **Topstep OCO bridge**: confirmed Stop+Limit bracket behavior; keep demo-only and max 1 MNQ until month-long evidence exists.
- **`wq-vol-regime-60m`**: keep as primary NY-session research candidate. It survived Rust sweeps and Backtrader stop/target research best, but still needs the OOS/live-readiness gates before demo routing.
- **Rust `bill-core` sweeps**: keep as fast canonical param exploration.
- **TS gates**: keep as promotion authority. Research claims cannot bypass `live-readiness-gate`, strategy zoo, and prop-firm matrix.
- **Hermes/Obsidian memory**: keep as narrative and decision log, but never as execution authority.
- **External alpha catalog on HDD**: keep; it is already the right contract for Gengar/Bill loaders.
- **Prediction market/Gengar lane**: keep separate from futures execution. Useful edge work, but not a prop-firm account router.

## Keep In Research Only

- ORB 15m/30m until Backtrader/Rust mismatch is explained.
- YouTube ICT/SMC/auction-market ideas until each hypothesis becomes a single-variable test with OOS evidence.
- DOM/order-flow concepts until real depth/tape fields are collected. Current OHLCV proxies are not order book evidence.
- TimesFM/Kronos forecasts until they improve a gate metric instead of just producing interesting forecasts.
- Prediction-market-to-futures bridge until latency, fillability, and causal direction are proven.

## Kill Or Quarantine

- Any strategy promoted only by prose notes without reproducible artifacts.
- Old Lucid/FundedNext/Topstep mixed-account routing assumptions.
- Mixed NQ/ES point-value backtests when R or dollars are compared directly.
- Lower-timeframe high-turnover strategies that fail prop drawdown or fee/slippage realism.
- Raw Polymarket websocket trade-side inference as a production signal without on-chain validation.
- Cold raw datasets and cloned repos on the SSD.

## Rebuild

- **Evidence ledger**: every research idea gets an ID, source, hypothesis, one changed variable, dataset, command, output artifact, OOS result, and promotion status.
- **Backtrader adapter**: extend the new harness so Hermes researcher can enqueue a hypothesis and receive a standardized JSON result.
- **n8n monitoring**: use n8n for dashboards, webhook status, and failure alerts, not strategy promotion.
- **Broker reconciliation**: fill checker must compare Topstep positions/orders against local state before master bridge can assume flat.
- **Demo dashboard**: show latest signal, account, active OCO, realized PnL, drawdown, last fill, and blocker state.
- **Storage tier job**: run a daily job that moves cold snapshots/results/cache to HDD before Hermes fails.

## Current Blockers

- `npm run bill:live-readiness-gate` is still blocked by uncommitted source changes and non-deployable OOS/live-readiness gates.
- Topstep monitor still warns about stale broker position state requiring confirmation.
- n8n has workflows but is not the real trading runtime; launchd/Hermes currently own most recurring work.
- ORB has a cross-engine contradiction that must be resolved before demo expansion.
- The SSD is no longer full, but still tight; long Rust builds or ML installs can refill it.

## Next Operating Rule

For the month-long Topstep demo:

1. Demo execution remains max 1 MNQ.
2. Only route from master bridge after guardrails pass.
3. Research may test any contract/stop/target combination, but those results cannot change live/demo sizing without a separate promotion artifact.
4. If Backtrader, Rust, and TS disagree, treat the strategy as research-only until the mismatch is explained.
