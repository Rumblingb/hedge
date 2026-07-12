# Bill Fund OS Phase 2 — Research Library, Data Truth, Execution Isolation

## Founder Vision

The vision in Obsidian is consistent:

- Build a cashflow-oriented autonomous fund system, not a toy strategy bot.
- Use free/local/deterministic workflows unless paid data materially improves quality.
- Keep Bill/Hedge separate from AgentPay product work.
- Prove one month on Topstep demo before live/funded scaling.
- Let agents research, test, summarize, and maintain memory; do not let prose bypass gates.

The critical correction is that the fund cannot trust agent confidence. It can only trust reproducible artifacts with data lineage, out-of-sample validation, broker reconciliation, and explicit promotion status.

## Canonical Roots

Use these as the working map:

- Live repo: `/Users/brain/hedge`
- Canonical runtime state: `/Users/brain/hedge/.rumbling-hedge/state`
- Research artifacts: `/Users/brain/hedge/docs/research`
- Obsidian founder/agent memory: `/Users/brain/Documents/memorybrain`
- Topstep operating log: `/Users/brain/Documents/memorybrain/Trading/Topstep-100K`
- HDD cold data and archives: `/Volumes/Seagate Expansion Drive/hedge-data`
- HDD old runtime archives: `/Volumes/Seagate Expansion Drive/rumbling-hedge`

Avoid writing new fund-critical state to `/Users/brain/.rumbling-hedge/state`. That tree is legacy/shadow and has already produced misleading cron output.

## Corpus Map

Generated:

- JSON: `/Users/brain/hedge/.rumbling-hedge/state/bill-corpus-audit.latest.json`
- Markdown: `/Users/brain/hedge/docs/research/bill-corpus-audit-2026-05-26.md`

Indexed 3,168 relevant artifacts:

- 393 notes
- 478 code files
- 49 evidence/backtest artifacts
- 88 strategy/signal artifacts
- 92 datasets
- 100 automation artifacts
- 6 directly relevant PDFs in Downloads
- 318 risk/proxy/stale artifacts

This is now the starting point for weaker agents. They should search the corpus audit first, then open the underlying file.

## Data Truth

Current checks:

- `ALL-6MARKETS-60m-60d-normalized.csv`: fresh and internally complete through `2026-05-26T15:00:00Z`.
- `ALL-6MARKETS-15m-60d-normalized.csv`: refreshed and normalized after the audit; data-quality passed through `2026-05-26T16:30:00Z`.

Implication:

- 60m research and demo candidate work is currently safer.
- 15m research can run again, but 15m signals are still not promoted for execution.
- Backtests may remain useful historically, but live/demo decisions need wall-clock freshness checks.

## Suspicious Cron Audit

These jobs are not fake in the sense of fabricated output, but their output was over-authoritative:

- `dom-proxy-ohlcv`: OHLCV CLV proxy, not true DOM, not bid/ask depth, not tape.
- `kalman-pairs`: pair-trade diagnostic, not valid confirmation for single-leg Topstep MNQ orders.
- `whale-flow-signal`: currently `fallback_no_data`; no live unusual-options, COT, 13F, insider, or CME block-trade feed is wired.
- `rolling-window-optimizer`: research parameter suggestion, previously emitted `nan` scores.

Actions taken:

- Patched repo and Hermes copies to write to canonical repo state.
- Marked these outputs `promoted_for_execution=false`.
- Marked proxy/no-live-data artifacts as `tradable_signal=false`.
- Patched `master_bridge.py`, `new_arsenal_gate.py`, and `signal_arbitration.py` so shadow/proxy signals cannot size or confirm execution.
- Fixed rolling-window NaN scoring.
- Patched legacy LucidFlex/PickMyTrade bridges so they default to shadow-only unless an explicit execution env flag is set.
- Patched the Hermes master bridge copy to delegate to the canonical repo bridge.

## Research Agent Quality

The research agents are finding the right broad areas:

- ORB/prop futures execution
- volatility regime and trend momentum
- market microstructure/OFI/LOB
- statistical arbitrage/pairs
- options/gamma/expiry flow
- prediction markets and Gengar
- Kronos/TimesFM forecasting

But the quality loop is incomplete:

- Too many notes say "implement" before a dataset and one-variable test exists.
- Some sources are future-dated or not locally verified as downloaded papers.
- YouTube/ICT/SMC ideas are useful hypothesis generators, not evidence.
- Agent reports often conflate "interesting" with "tradable."
- The system needs an evidence ledger before any research output can affect trading.

## Contrary Side

The strongest contrary evidence in the local corpus:

- OHLCV-only MNQ/NQ strategies are structurally limited after costs, especially lower-timeframe ORB.
- DOM proxy from OHLCV is not order flow; it can create false confidence.
- Pairs/stat-arb notes repeatedly say classical OU/cointegration is fragile and two-stage models underperform.
- Prop-firm constraints make high-R backtests less relevant if consistency, trailing drawdown, and daily loss rules fail.
- ORB is currently contradictory: Rust time-exit sweeps like it; Backtrader stop/target replay does not.

Use contrary evidence as a promotion gate, not as discouragement. A strategy is stronger only after it survives its best opposing argument.

## If I Were Building The Fund From This Base

1. **Execution lane**
   - Keep only Topstep demo max 1 MNQ.
   - Route only from `master_bridge.py`.
   - Require broker position/order reconciliation before every route.
   - Ignore all unpromoted proxy signals.

2. **Research lane**
   - Convert every idea into an evidence card: source, hypothesis, one variable, dataset, command, output, OOS result, decision.
   - Use Rust for large sweeps.
   - Use Backtrader for broker-style stop/target replay.
   - Use TS gates for promotion.

3. **Data lane**
   - Keep 60m current.
   - Keep 15m fresh before any 15m strategy matters.
   - Move cold data to HDD.
   - Treat Seagate external alpha as cataloged feature store, not a pile to grep every run.

4. **Agent lane**
   - Hermes researches and summarizes.
   - n8n schedules low-variance monitoring and dashboards.
   - Agents cannot promote or route execution.

5. **Portfolio lane**
   - Primary: `wq-vol-regime-60m`.
   - Secondary research: `wq-trend-mom-30m`, ORB only after contradiction is resolved.
   - Shadow: Kalman/pairs, DOM/OFI, whale flow, Kronos/TimesFM, prediction-to-futures bridge.

## Current Completion Audit

Generated:

- JSON: `/Users/brain/hedge/.rumbling-hedge/state/bill-fund-os-completion-audit.latest.json`
- Markdown: `/Users/brain/hedge/docs/research/bill-fund-os-completion-audit-2026-05-26.md`

Current result: `HANDOFF_COMPLETE_TRADING_BLOCKED`.

The trading blocker is intentional: live/demo expansion is still red because the refreshed walk-forward matrix rejects the current profiles, rolling OOS has 0/3 deployable windows, stressed live-readiness is not deployable, and the source tree is dirty. This is not an organization failure; it is the fund OS correctly refusing promotion.

Fresh evidence:

- `npm run bill:walkforward-matrix -- data/free/ALL-6MARKETS-60m-60d-normalized.csv .rumbling-hedge/state/walkforward-matrix.latest.json 6` returned `status=reject`.
- `npm run live-readiness -- data/free/ALL-6MARKETS-60m-60d-normalized.csv 3` returned profitable-but-not-deployable due thin OOS trade count and failed deflated expectancy.
- `npm run bill:live-readiness-gate` remains `readyForLive=false` and `readyForDemoExpansion=false`.

## Promotion Rule

A signal can affect demo/live execution only if all are true:

- `promoted_for_execution=true`
- `tradable_signal=true`
- data-quality passes with wall-clock freshness
- TS live-readiness gate passes
- walk-forward and rolling OOS pass
- Topstep guardrail monitor has no hard blockers
- broker reconciliation says flat or protected
- the promotion artifact links to the exact backtest/replay command and output

Everything else is research.
