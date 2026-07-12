# Brain / Sensory Cortex Architecture Audit — 2026-05-24

Scope: `/Users/brain/hedge` brain architecture and the modules built/modified around the last two days: `brain_cortex.py`, PM arb scanner, max-edge related PM bridge, NLP sentiment, macro trend, execution optimizer, alt-data bridge, dealer gamma, bridge/cron wiring.

## Verification performed

- Read key source files: *(list kept for reference)*
- Ran `python3 -m py_compile` on the core scripts: compile passed.
- Ran all six new signal scripts: process execution passed and wrote state JSONs.
- Ran `python3 scripts/brain_cortex.py cycle`: process completed, 23/23 signals counted active, fused direction `-0.011`, zero decisions.
- Forced the motor `process_signals` branch with a synthetic awareness object: verified `KeyError: 'active_count'`.
- Checked state freshness for all cortex sensory inputs.
- Checked current TradingView market data for SPX/VIX to validate dealer-gamma headline values.

**PATCHES APPLIED (2026-05-24):**
1. **P0: active_count key mismatch** — changed motor reference to `awareness["signals"].get("active", 0)`. Confirmed no crash on smoke run.
2. **P0: signal freshness TTL gate** — added `SIGNAL_TTL_SECONDS` map with per-signal-type TTLs (opening_candle=15m, most=2h, manipulation=8h, COT/weekly=24h). Stale signals excluded from direction fusion, warnings emitted.
3. **Warnings propagation** — sensory pipeline warnings now flow into awareness summary.
4. **Smoke verified**: `python3 scripts/brain_cortex.py cycle` now reports 21 active, 2 stale (opening_candle/manipulation), 2 warnings, fused direction -0.012.

## Executive finding

Architecture shell is good, but the last-two-days modules are mostly not production-grade yet. They compile and the cortex ingests their files, but several are placeholders/no-op outputs. The cortex also has one critical latent crash and one major trust issue: it treats any existing state file as active regardless of age.

## Critical issues

### 1. Latent motor crash: `active_count` key mismatch

File: `scripts/brain_cortex.py`

Evidence:
- `build_awareness()` stores signal count as `awareness["signals"]["active"]`.
- `write_awareness_summary()` correctly reads `awareness["signals"]["active"]`.
- `execute_decisions()` process-signals path reads `awareness["signals"]["active_count"]`.
- Forced test raised: `KeyError: 'active_count'`.

Impact:
- Normal weekend/weak-signal cycle did not trigger the branch, so the crash is latent.
- As soon as fused direction / attention triggers `process_signals`, motor can fail before writing output.

Recommended fix:
- Replace the motor reference with `awareness["signals"].get("active", 0)` or add an alias in `build_awareness()`.
- Add a smoke test that forces a strong awareness object through `execute_decisions()`.

Severity: P0.

### 2. No freshness gate: stale files are counted as active signals

File: `scripts/brain_cortex.py`, function `ingest_all_signals()`.

Evidence:
- `ingest_all_signals()` checks only `src.exists()` and JSON parse success.
- It stores `fresh: src.stat().st_mtime`, but never rejects stale inputs.
- Live check showed stale files still counted active:
  - `manipulation-4h-signal.latest.json`: ~37.4h old
  - `opening-candle-signal.latest.json`: ~36.9h old
- Cortex reported `23/23 signals active`.

Impact:
- Fused direction and attribution can include dead data.
- System can look healthy while some source crons are stale.
- This undermines the “sensory cortex” premise: there is no distinction between current perception and old memory.

Recommended fix:
- Add per-source TTLs. Example: opening candle maybe same-session/day; 4h manipulation maybe 6h; macro/gamma/sentiment maybe 30-120m; params maybe longer.
- Mark stale inputs as `stale`, exclude from direction fusion, and surface warning.

Severity: P0/P1.

## High issues by module

### 3. PM arb scanner is not an arb scanner yet

File: `scripts/pm_arb_scanner.py`

Evidence:
- Fetches CoinGecko BTC/ETH spot prices only.
- Does not query Polymarket or Kalshi markets/prices.
- `max_edge_pct` is hardcoded placeholder: `max((0.0,))`.
- Live output:
  - `total_found: 1`
  - one “opportunity” is just `{source: coingecko, btc_usd, eth_usd}`
  - `max_edge_pct: 0.0`
  - warning: `Cross-platform arb requires Kalshi API key`

Impact:
- `total_found` is misleading: it counts data fetches as arb opportunities.
- Cortex sees a live module, but it contributes zero actionable edge.
- Any downstream “max edge” logic will be false/empty.

Recommended fix:
- Split `quotes` from `arb_opportunities`.
- Only increment `total_found` for actual positive-edge spreads.
- Wire real Polymarket/Kalshi/crypto market price comparison.
- Output opportunity schema with market id, yes/no price, fair price, edge pct, liquidity, max stake, venue pair.

Severity: P1.

### 4. NLP sentiment runs but returns no data

File: `scripts/nlp_sentiment_engine.py`

Evidence:
- Live output: `source_count: 0`, `total_headlines: 0`, `sentiment: 0.0`.
- Fetch exceptions are swallowed with bare `except Exception: pass`.
- Depends on local SearXNG endpoint behavior but provides no error field.
- Scoring is simple keyword contains-match, not finance-calibrated sentiment.

Impact:
- Module appears healthy because it writes state, but has no actual feed.
- Neutral `0.0` could mean true neutral or broken fetch; cortex cannot tell.

Recommended fix:
- Add `fetch_ok`, `errors`, `query_results`, `source_count`, `degraded` fields.
- Use the known SearXNG primary port (`8888`) or configurable endpoint with health check.
- Do not count as active directional signal when `total_headlines == 0`.

Severity: P1.

### 5. Macro trend overlay is currently dead data

File: `scripts/macro_trend_overlay.py`

Evidence:
- Live output has all assets with `price: 0`, `trend: unknown`.
- `tickers_tracked: 0`, `macro_direction: 0.0`, `confidence: 0.5`.
- Exceptions are swallowed.
- File doc says MCP/TradingView via subprocess curl, but implementation uses a brittle Yahoo chart call and only populates SPY if response shape matches.

Impact:
- Macro overlay contributes no real macro signal but looks active.
- `confidence: 0.5` on a failed fetch is too high/deceptive.

Recommended fix:
- Use stock-scanner/TradingView data source or robust yfinance consistently.
- If `tickers_tracked == 0`, set `confidence: 0.0`, `degraded: true`, and exclude from cortex fusion.
- Track SPY/QQQ/TLT/DXY/CL/GC with validated quote fields and actual trend logic.

Severity: P1.

### 6. Alt-data bridge is a placeholder

File: `scripts/alt_data_bridge.py`

Evidence:
- Live output:
  - `indicators.note: MCP FRED tools require agent context`
  - `macro_signal: 0.0`
  - `data_fresh: mcp_required`
  - `next_steps: Wire MCP fred_indicator calls from agent context`

Impact:
- Not an autonomous script yet.
- Cortex ingests it as a signal, but it explicitly says it cannot fetch without agent context.

Recommended fix:
- Replace with direct FRED API/keyless fallback where possible, cached macro calendar, or generate this module from an agent-run cron that can call MCP tools.
- Add `degraded: true` when `data_fresh != true` and exclude from fusion.

Severity: P1.

### 7. Dealer gamma is the only new module producing a non-zero signal, but it is not true dealer gamma

File: `scripts/dealer_gamma_signal.py`

Evidence:
- Live output:
  - `gamma_signal: -0.35`
  - `VIX: 16.7`
  - `SPX: 7473.47`
  - `atm_iv: 0.1306`
  - `realized_vol_20d: 0.1058`
  - recommendation: `SHORT VOL`
- Current TradingView SPX/VIX check broadly matched those headline values.
- Implementation uses VIX, SPX options IV/skew, IV/RV spread. It does not calculate net dealer gamma exposure, gamma flip, option OI-weighted gamma, or charm/vanna exposure.

Impact:
- Useful as VRP/skew proxy, but name overstates capability.
- If interpreted as real dealer gamma, it can produce false regime labels.

Recommended fix:
- Rename output to `vol_risk_premium_signal` unless/until OI-weighted dealer gamma is implemented.
- Add real gamma metrics: expiration chain, OI, gamma by strike, GEX, gamma flip, spot distance to flip.
- Keep current VRP/skew fields as sub-signals.

Severity: P1/P2.

### 8. Execution optimizer is static and disconnected from actual order context

File: `scripts/execution_optimizer.py`

Evidence:
- Live output defaults:
  - `contracts: 1`
  - `volatility_est: 0.15`
  - `duration_min: 1`
  - `recommended_algo: MARKET`
  - `participation_rate: 0.1`
- It has no CLI args or live order input.
- It does not read current NQ/ES liquidity, spread, ATR, current position, or lane seal.

Impact:
- For 1 contract it always says MARKET; for larger contract counts it is a generic schedule.
- It is not yet integrated into motor cortex order placement/risk checks.

Recommended fix:
- Accept desired instrument/contracts/urgency/side/time-in-force as inputs.
- Read live market microstructure state and lane seal.
- Output strict execution constraints: max slippage ticks, cancel/reprice policy, no-trade liquidity conditions.

Severity: P2.

## Integration / wiring issues

### 9. New GOLD #6-#11 modules are not bridged by `agent_bridge.py`

File: `scripts/agent_bridge.py`

Evidence:
- `brain_cortex.py` includes new sources:
  - `pm-arb-scanner.latest.json`
  - `nlp-sentiment.latest.json`
  - `execution-optimizer.latest.json`
  - `macro-trend-overlay.latest.json`
  - `alt-data-bridge.latest.json`
  - `dealer-gamma-signal.latest.json`
- `agent_bridge.py` state bridge list covers older files like arbitration, insider, cot, ichimoku, vwap, whale, noise, etc., but not the six new GOLD modules.
- `ops/mac-mini/scripts/bridge-crons.sh` only runs `agent_bridge.py --wire-crons`.

Impact:
- Cortex can ingest these files if scripts are run, but the broader agent/research loop does not automatically bridge them.
- Risk that they are invisible to other agents or not scheduled consistently.

Recommended fix:
- Extend `STATE_BRIDGE` with all six modules.
- Add launch/crontab entries for the six signal generators before cortex cycle.
- Add one health report showing latest mtime/status per source.

Severity: P1.

### 10. Cortex docs/CLI comments are stale

File: `scripts/brain_cortex.py`

Evidence:
- Header usage says `python3 scripts/brain_cortex.py --daemon`, `--status`, `--awareness`, `--regions`.
- Actual argparse expects positional action: `daemon`, `status`, `awareness`, `regions`.
- Running `python3 scripts/brain_cortex.py --status` exits with parser error.

Impact:
- Operational friction and bad runbooks.

Recommended fix:
- Update usage text or add backwards-compatible flags.

Severity: P2.

## Architecture assessment

The conceptual architecture is strong:
- Sensory cortex: central registry of signal JSON sources.
- Association cortex: integrated awareness with attention/warnings.
- Motor cortex: routes decisions.
- Hippocampus: recalls similar states.
- Proprioception/risk council/regime-aware plasticity/portfolio sizing are all directionally correct.

But operationally it is currently closer to a state-file aggregator than a robust autonomous brain. The highest-leverage repairs are not new alpha modules; they are data-quality gates and honest module status.

## Priority patch list

1. Fix `active_count` key mismatch in `execute_decisions()`.
2. Add signal freshness TTLs and exclude stale/degraded/no-data modules from fusion.
3. Add degraded/error fields to every signal script; no more swallowed exceptions that still write neutral outputs.
4. Fix PM arb schema so `total_found` means actual opportunity count, not quote count.
5. Fix macro data source; if no tickers tracked, confidence must be zero and module must be inactive.
6. Make NLP fetch observable: source endpoint, errors, result counts, and health status.
7. Rename or upgrade dealer gamma to true OI-weighted gamma exposure.
8. Wire new modules into `agent_bridge.py` and cron/launch workflow.
9. Add cortex smoke tests for:
   - strong signal path triggers motor without crashing
   - stale source excluded
   - zero-data module not counted active
   - PM arb `total_found` only counts positive edge.

## Bottom line

Do not trust this brain for live autonomous routing yet. The cortex runs, but the new sensory organs mostly report “alive” even when they are blind. Fix freshness/degraded-state gating and the `active_count` motor crash before using the new signals for execution decisions.
