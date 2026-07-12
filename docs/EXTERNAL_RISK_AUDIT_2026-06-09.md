# Bill/Hedge Trading System — External/Operational Risk Audit

**Date**: 2026-06-09  
**Auditor**: Hermes Agent (system-wide codebase audit)  
**Scope**: All external-facing components, market data paths, broker API interaction, operational edge cases, and failure modes  
**Status**: Demo-only, master-strategy-bridge PAUSED, TopstepX demo account active

---

## Risk Ranking Summary

| Severity | Count | Must-fix before any live money |
|----------|-------|-------------------------------|
| CRITICAL | 4 | Catastrophic financial loss scenarios |
| HIGH     | 8 | Significant loss potential, rule violations |
| MEDIUM   | 9 | Operational degradation, moderate risk |
| LOW      | 6 | Informational, best practice gaps |

---

# CRITICAL RISKS

## C-01: No Position Reconciliation on Restart
**Severity: CRITICAL**

The system has **zero mechanism** to discover open positions after any restart cycle. The trade journal (`trade-count-today.json`) is a simple daily counter. If the master bridge, Topstep bridge, or host restarts between order submission and execution/fill:

- The bridge re-runs, sees no "pending" signal, and may place a **duplicate order**
- The bridge re-runs, sees the old pending state (stale), and **skips** — but the first order already filled
- If the topstep_demo_bridge.py crashed after placing an entry but before placing the OCO stop/target, the position is **unprotected**

**Specific scenario**: Bridge submits 1 MNQ long entry at 19,500. Host crashes (or bridge times out at 30s). On restart, master_bridge finds `master-signal.latest.json` with status `topstep_demo_submitted` or a stale pending state. If it treats this as "already submitted" → skips, the position is on and unmonitored. If it treats as "not submitted" → places a second identical order → **double position**.

**No `GET /positions` or reconciliation call exists anywhere in the codebase.**

---

## C-02: No Partial Fill Handling
**Severity: CRITICAL**

Bracket OCO orders (entry, stop, target) are submitted as a single atomic bracket in `topstep_demo_bridge.py`. However:

- **No code processes partial fills**. If the entry fills only 2 of 5 contracts, the system has no awareness.
- **No code adjusts stop/target on partial fill**. The remaining 3 contracts are left with no OCO protection.
- **No fill confirmation loop**. The bridge submits and exits — there is no polling for execution status.

**Specific scenario**: Aggressive sweep on NQ. Entry at 19,500 fills 1 of 1 MNQ (OK). But if the system ever trades multiple contracts (the code computes `topstep_contracts = max(1, min(contracts, max_demo_contracts))`), partial fills silently create unhedged residual risk.

---

## C-03: Garbage-In/Garbage-Out: CSV Data Quality Is Unknown
**Severity: CRITICAL**

The master bridge and all strategy computations use **Yahoo Finance CSV data** as their primary input. Key issues:

1. **Multiple CSV files are days to weeks stale** (found files from May 14, May 17, May 24 — current date June 9)
2. **Volume confirmation logic** (`volume > avg_vol * 1.2`) relies on Yahoo volume data, which is known to be unreliable for futures
3. **Backtests run on same Yahoo CSV data** — backtest win rates (e.g., orb-breakout 68%) are likely **overfitted to Yahoo's specific data quirks** (settlement prices, missing intraday gaps, adjusted closes)
4. **CSV-to-live data mismatch**: Master bridge computes strategy signals on 60m/15m/5m Yahoo CSV bars (interpolated from 1m or tick data), but the actual broker executes against CME real-time prices
5. **No parity check between broker bars and local CSV bars** exists in production code

**Specific scenario**: A strategy shows 68% win rate in backtest on Yahoo data. It fires a live entry signal. But the actual CME market structure at that exact bar differs from Yahoo's representation (Yahoo uses settlement/interpolated prices). The trade loses because the live candle close ≠ CSV close. The strategy's edge is an artifact of Yahoo's data construction, not actual market inefficiency.

---

## C-04: No Intraday Risk Monitoring Loop
**Severity: CRITICAL**

The system operates as **fire-and-forget submission**. The flow is:

1. master_bridge.py runs (cron every ~5-30 min)
2. Computes signals, picks best, validates through 4+ gates
3. Calls topstep_demo_bridge.py
4. topstep_demo_bridge.py submits OCO bracket to TopstepX API
5. **Exit** — no background process monitors the position

There is:
- **No trailing stop management daemon** (the PickMyTrade path had `trailing_stop` and `breakeven` params, but the Topstep path doesn't implement trailing)
- **No EOD reconciliation** to verify positions flat
- **No profit/loss monitoring** of open positions
- **No automatic flatten on kill switch** — the kill-switch.json exists (`triggered: false`) but no cron or daemon reads it and flattens positions

**Specific scenario**: Market gaps overnight. MNQ opens 200 points lower. The OCO stop-loss that was placed at market entry (1.5 ATR = ~30 points) was at a specific price level. On gap open, the stop might execute at a substantially worse price (slippage beyond stop). The system has no circuit breaker to detect this and stop further trading.

---

# HIGH RISKS

## H-01: TopstepX API is a Complete Black Box
**Severity: HIGH**

The `topstep_demo_bridge.py` (external to hedge repo at `~/.hermes/scripts/`) handles all broker interaction. The hedge repo codebase has:

- **No TopstepX API documentation or rate limits** defined
- **No auth expiry handling** — if the API key rotates or expires, the bridge fails silently
- **No connection health monitoring**
- **No error classification** (temporary vs permanent, recoverable vs fatal)
- **No retry logic with backoff**
- **No HTTP status code handling beyond checking returncode == 0**

The `TopstepLiveAdapter` in `dist/src/adapters/topstep/topstepAdapter.js` is explicitly a **stub** — `submit()` throws "Live submit is intentionally not implemented in v0.1."

**Specific scenario**: TopstepX rate-limits the demo account at 10 requests/minute. Multiple cron jobs fire simultaneously (45 crons). The bridge call gets HTTP 429. The bridge returns non-zero. Master bridge interprets as "submission failed" and writes state. Next cron cycle retries → same rate limit → infinite retry loop, burning through API quota.

---

## H-02: No Duplicate Order Detection at Broker Level
**Severity: HIGH**

The duplicate detection in `master_bridge.py` (lines 708-723) checks:

```python
sig_key = f"{best['side']}@{best['strategy']}"
already_routed = last_sig.get("submitted") is True or pending_is_fresh
if last_sig.get("signal") == sig_key and already_routed:
```

This is **state-file-only deduplication** — it has no interaction with the broker's open orders/positions. If the state file is deleted, corrupted, or from a different session, the same signal can be submitted again.

**Failure modes**:
- Manual state file deletion → re-submits same signal
- Two cron jobs overlapping (race condition) → both pass duplicate check before either writes
- State file JSON parse error → empty dict, bypasses check

**No distributed lock or transaction boundary** protects order submission.

---

## H-03: Backtest-to-Live Data Mismatch (Yahoo → CME)
**Severity: HIGH**

All strategy win rates cited in `master_bridge.py` header (orb-breakout 68%, wq-trend-mom 61.5%, wq-vol-regime 57.1%, wq-alpha-001 58.2%) were computed on **Yahoo Finance CSV data**.

Known Yahoo Finance issues for futures:
- **Delayed data**: 2-15 minute delay
- **Settlement prices**: Closing prices are settlement, not last trade
- **Volume**: For NQ/ES, Yahoo volume is notoriously unreliable (often 0 or NaN)
- **Bar construction**: 5m bars are interpolated from tick data, not true exchange bars
- **Adjustments**: Symbol rollover at expiry creates artificial gaps

The Real-time data bridge tries to upgrade to TradingView WebSocket (~600ms delay), but the **strategy computation still uses CSV data** — only the freshness gate uses real-time prices.

**Expected outcome on live**: True win rates will be **significantly below backtest estimates** due to data quality differences alone, before accounting for slippage and execution.

---

## H-04: Session Gate Has No CME Holiday Awareness
**Severity: HIGH**

`session_gate.py` blocks:
- Weekends (Saturday, Sunday before 18:00 UTC)
- Premarket, postmarket, closed sessions
- First 5 minutes of NY open
- After 14:00 ET

But it has **17 CME holiday early-closures** and **full-day closures** that are **not handled**:
- MLK Day (Jan 19) — full electronic trading, normal hours
- Presidents Day (Feb 16) — early close
- Good Friday (Apr 3) — CLOSED
- Memorial Day (May 25) — early close  
- Juneteenth (Jun 19)
- Independence Day (Jul 4) — early close
- Labor Day (Sep 7) — early close
- Thanksgiving (Nov 26) — early close
- Christmas (Dec 25) — CLOSED
- New Year's Day (Jan 1) — CLOSED

**Specific scenario**: July 4th, early close at 13:00 ET (not the default 16:00 ET). Session gate allows trading until 14:00 ET (coded). The system submits a trade at 13:15 ET when the market is already closed. Order is rejected or, worse, queued for the next session.

---

## H-05: Concurrency — 45 Cron Jobs, No Distributed Locking
**Severity: HIGH**

The system runs 45 cron jobs. Multiple jobs can fire within the same second or minute. There is **no distributed mutex, no file locking, no database transaction** protecting shared state.

**Manifested risks**:
1. **Two master_bridge instances overlap**: Both run `pick_best()`, both get same signal, both check duplicate state before either writes → both submit → **double order**
2. **Trade counter race**: `read_trade_count()` then `increment_trade_count()` is a classic TOCTOU race. Two processes both read count=0, both increment to 1 → actual trades = 2 but count = 1 (or 2 but both think they're the 1st)
3. **State file corruption**: Multiple processes writing `master-signal.latest.json` simultaneously → truncated/invalid JSON

**TopstepX likely has its own rate limits that prevent some abuses, but the system depends on this for safety instead of its own enforcement.**

---

## H-06: No High-Impact News Handling Beyond Hardcoded Dates
**Severity: HIGH**

The system handles:
- **FOMC days**: Hardcoded 2026 date list (covers 17 dates) — blocks ALL trading
- **Macro events**: `Macro Context Engine` (`macro_context.py`) has a hardcoded MACRO_EVENTS_2026 dict with ~40 dates

**Problems**:
1. **Unscheduled events** (emergency FOMC, surprise rate decisions, geopolitical black swans) — **zero protection**
2. **Expired hardcoded list after 2026** — system silently goes unprotected
3. **NFP/CPI**: macro_context.py logs them but only the `assess()` function can block — there's no automatic trade suppression for NFP releases 5 minutes before/after
4. **FOMC day 2**: Only FOMC announcements at 14:00 ET on Day 2 are checked, not the full 2-day risk
5. **Macro context check is advisory, not enforced** — the gate can return `REDUCED` instead of `NO_TRADE`, and the master bridge just applies a confidence modifier

**No automatic trade halt 30 min before / 15 min after known high-impact events.**

---

## H-07: Topstep Compliance Violation Risks
**Severity: HIGH**

The `topstepCompliance.js` enforces Topstep's combine rules (consistency ratio, trailing drawdown, max contracts, profit target) **in local state only** — it has no connection to the broker.

**Violation scenarios**:
1. **Multiple cron submissions bypass local compliance**: 45 cron jobs each call submit independently. topstepCompliance's state is in-memory only (resets on restart → loss of drawdown tracking)
2. **Best-day consistency rule**: Topstep requires best day ≤ 50% of total profit. The system trades 3 sessions (NY/London/Asia) with different sizing. If London session makes 60% of total profit, the consistency rule is **violated** and the combine fails.
3. **Trailing drawdown**: Measured EOD by Topstep, but the system has multiple independent submission paths that don't share drawdown state.

**The demo account (100KTC-V2-DLL) has $3,000 max trailing drawdown. If the system hits this in demo, the combine account is lost — but the system has no local fail-fast to prevent it.**

---

## H-08: Position Sizing Assumes Fixed $2/pt for MNQ — Wrong for NQ
**Severity: HIGH**

`calc_position()` in `master_bridge.py` (line 467):
```python
risk_per_contract = stop_dist * 2  # MNQ = $2/point
```

This assumes MNQ ($2/pt) for ALL instruments, but strategies also run on ES (which is $5/pt for MES or $50/pt for ES full). The `60m_exec_bridge.py` and `pre_trade_check.py` have proper `POINT_VALUES` dictionaries but the master bridge's primary sizing function **always uses $2/pt**.

**Specific scenario**: Strategy fires an ES signal. `calc_position()` computes risk as 1/25th of actual (assuming MNQ $2/pt vs MES $5/pt or ES $50/pt). If ES signal goes to Topstep demo with MES, position is 2.5x larger than intended.

Note: The `pre_trade_check.py` has a proper `POINT_VALUES` dict but the master bridge doesn't use it.

---

# MEDIUM RISKS

## M-01: TradingView WebSocket Is Single Point of Failure for Data Freshness
**Severity: MEDIUM**

The data freshness gate (`data_freshness_gate.py`) requires `realtime-quote.latest.json` to be < 60 seconds old with an execution-grade source (tradingview_pro, tradingview_ws, broker_realtime, topstep_realtime, databento_realtime).

**Failure cascades**:
1. TV WebSocket disconnects → realtime data stops updating → age > 60s → **ALL trading blocked**
2. Fallback to Yahoo (300s max age) — but Yahoo data is automatically classified as non-execution-grade, so it still **blocks trading**
3. Databento is available but `BILL_DATABENTO_REALTIME_ENABLED=false` by default
4. There is **no degraded-mode trading** with smaller size — it's all-or-nothing

**Result**: A brief WebSocket reconnect (common — TV WS reconnects every few hours) halts the entire trading system for at least 61 seconds.

---

## M-02: FOMC Date List Is Hardcoded and Will Expire
**Severity: MEDIUM**

`master_bridge.py` (lines 174-184) has FOMC_DATES hardcoded for 2026:
```python
FOMC_DATES = {
    date(2026, 1, 28), date(2026, 1, 29),
    date(2026, 3, 17), date(2026, 3, 18),
    ...
}
```

`macro_context.py` has a separate MACRO_EVENTS_2026 dict that overlaps but is inconsistent with FOMC_DATES.

**Problems**:
- After Dec 16, 2026 → **zero FOMC protection**
- No calendar refresh mechanism
- No web-based Fed calendar lookup
- If FOMC adds an unscheduled meeting (e.g., 2020-style emergency cut) → **no protection**

---

## M-03: Chicago Timezone Approximation Is Brittle
**Severity: MEDIUM**

`dailyLock.js` (lines 31-35):
```javascript
const month = now.getUTCMonth(); // 0-indexed
const isDST = month >= 2 && month <= 10; // rough: Mar-Nov
const offset = isDST ? 5 : 6;
```

This is a **simplistic DST heuristic** that:
- Misses the exact DST transition dates (2nd Sunday March → 1st Sunday November in US)
- Is wrong during the 1-2 week DST transition periods
- Could misclassify session windows by 1 hour during transition weeks

**Impact**: Session gate blocking/allow decisions off by 1 hour during DST transitions, potentially allowing trades during the wrong session or blocking during prime hours.

---

## M-04: Risk State Is Single JSON File — No Write Atomicity
**Severity: MEDIUM**

`risk-state.json`, `master-signal.latest.json`, `trade-count-today.json` and other state files are written as single `json.dumps()` + `write_text()` operations.

**Failure modes**:
1. Crash during write → **truncated/corrupt JSON** → next read fails → `{}` → **all safety bypassed** (risk.blocked = False, trade_count = 0, daily_loss = 0)
2. Multiple processes writing simultaneously → **cross-corruption**
3. No backup/versioned state → no rollback capability

**There is no atomic write pattern** (write to temp file, fsync, rename) anywhere in the Python state management.

---

## M-05: No Early Close / Late Open Handling for Half Days
**Severity: MEDIUM**

CME has scheduled early closes and late opens for many holidays. The session gate uses fixed times:
- `NO_NEW_TRADES_AFTER_ET = time(14, 0)` (default)
- `FRIDAY_EARLY_CLOSE_ET = time(15, 30)` (Friday)

**Half-day scenarios not handled**:
- Day before Thanksgiving (early close at 13:00 ET) → system trades until 14:00 ET including 1 hour after market close
- Christmas Eve (early close at 13:00 ET)
- New Year's Eve (early close at 13:00 ET)
- Late opens (winter weather, technical issues) — system trades when market is still closed

---

## M-06: Signal Arbitration Has No Conflict Resolution for Opposite Directions
**Severity: MEDIUM**

The system runs 60m, 30m, 15m, and 5m strategies simultaneously. Each can produce signals in opposite directions. The "pick best" function (`pick_best()`) just selects highest confidence — it **does not check for directional conflicts**.

**Scenario**: 60m orb-breakout says LONG (confidence: 0.65). 5m wq-trend-mom says SHORT (confidence: 0.58). Both are positive signals. The system picks 60m LONG. But the 5m signal indicates immediate-term weakness. No guard checks whether the higher-timeframe and lower-timeframe signals agree.

The new arsenal gate and macro context provide some conflict resolution but they check the selected signal against external context, not against other signals from different timeframes.

---

## M-07: `run_strategy()` Has Inconsistent Min Bars and Max Age
**Severity: MEDIUM**

Each strategy call in `master_bridge.py` has varying `min_bars` and `max_age_hours` parameters:

```python
# NQ 60m: min_bars=12 (default=30), max_age=8 (default)
# NQ 30m: min_bars=12 (default=30), max_age=8 (default)
# NQ 15m: min_bars=30 (default=30), max_age=8 (default)
# NQ 5m:  min_bars=60 (default=30), max_age=8 (default)
# ES 60m: min_bars=16 (default=30), max_age=8 (default)
```

The `max_age_hours=8` default means a 60m bar from **8 hours ago** is considered fresh enough to trade on. In a fast-moving market, 8 hours of data for a 60m strategy means the signal is computed on bars that could be from **yesterday's session**. This is especially dangerous in: Asia session (trading on stale prior-close data), Monday morning (trading on Friday close data), and post-holiday sessions.

---

## M-08: Pre-Trade Check Has `--force` Override
**Severity: MEDIUM**

`pre_trade_check.py` has a `--force` flag that bypasses:
- Stale data warnings
- Market closed checks
- Session phase restrictions

If automation or a cron job ever calls `pre_trade_check.py --force`, all data freshness and session gates are bypassed. This is a single flag away from uncontrolled trading.

---

## M-09: Duplicate Cron References to Execution Files
**Severity: MEDIUM**

The execution intake manifest (`bill_execution_intake_manifest.py`) already identified: "Active cron references to dirty execution-live files require operator review." Multiple crons reference the same execution-adjacent scripts, increasing the risk of concurrent execution and state corruption.

---

# LOW RISKS

## L-01: PickMyTrade Webhook Credentials in Environment
**Severity: LOW**

The `send_signal()` function in `master_bridge.py` reads `BILL_PICKMYTRADE_WEBHOOKS_JSON` from environment, which contains API tokens. If an error occurs, stack traces could leak credentials. The credential file `bill.env` is parsed by multiple scripts.

## L-02: `breakeven` and `trail` Parameters Hardcoded in PickMyTrade Path
**Severity: LOW**

The legacy PickMyTrade path hardcodes `breakeven_offset: 1`, `trail_freq: 1`, `pyramid: True`. The `pyramid: True` flag is especially dangerous — it allows position pyramiding on the same symbol. The Topstep path doesn't use these but if the flag is ever exported to Topstep, it could cause unintended position accumulation.

## L-03: Market Hours Comment Mismatch
**Severity: LOW**

`pipeline_monitor.py` comments: `MARKET_OPEN_HOUR = 13   # 09:30 ET`. But 09:30 ET = 13:30 UTC during EDT (summer). The comment is off by 30 minutes. This doesn't affect logic (the constant 13 is used for refresh timing decisions) but causes confusion.

## L-04: No ReadTimeout on urllib Requests
**Severity: LOW**

The only timeout in the master bridge is on `urllib.request.urlopen(req, timeout=15)`. There's no connection timeout separate from read timeout. If the PickMyTrade webhook URL hangs before connecting, the entire bridge could wait up to 15 seconds per webhook call.

## L-05: `macro_context.py` Imports `sys.path.insert(0, ...)` Pattern
**Severity: LOW**

`master_bridge.py` line 138: `sys.path.insert(0, str(Path(__file__).parent))` — this overrides system paths at runtime. In production with multiple Python versions and environments, this can import wrong modules.

## L-06: No Test Coverage for Risk-Edge Scenarios
**Severity: LOW**

The test suite (`dist/tests/*.test.js`) has 50+ test files testing individual components, but there are **no end-to-end tests** covering:
- Bridge restart with open position
- Dual cron race submission
- Partial fill handling
- API rate limit recovery
- State file corruption recovery
- Holiday boundary trading
- Data source switch (Yahoo→TV→Broker)

---

# MARKET CONDITION SPECIFIC SCENARIOS

## Flash Crash (May 6, 2010-style)
**Impact**: CRITICAL

- OCO stop-losses placed at 1.5 ATR (~30 NQ points) would be **gap-through** — stop executes 100+ points lower
- The system has **no limit-move detection** or temporary trading halt awareness
- No circuit breaker to stop new trades after the crash starts
- The `cumulative_loss >= $2000` block is the only protection — but it checks AFTER the damage is done

## Low-Liquidity Periods (Lunch, Pre-FOMC, Summer doldrums)
**Impact**: HIGH

- Session gate allows trading during lunch (12:00-13:30 ET) — spreads widen, stops get picked
- No minimum spread/volume check before entry
- WQ strategies' volume confirmation (`volume > avg_vol * 1.2`) won't trigger during low volume → fewer trades (partially protective)
- Slippage on 5m strategy entries during low liquidity: 2-5 points vs normal 0.5-1

## Consecutive Losing Days / Drawdown Spiral
**Impact**: HIGH

- Risk state tracks cumulative loss with $2,000 hard cap
- But: if restart during drawdown → risk.json is reset (new day, cumulative_loss from old day carried forward only if risk.json still readable)
- If risk.json gets corrupted during a drawdown (crash while writing) → cumulative_loss resets to 0 → **drawdown protection wiped**
- No cooling-off period after a losing day

## Sudden Volatility Expansion (NFP beat, FOMC surprise)
**Impact**: HIGH

- NFP: macro_context.py notes NFP date but doesn't block trading within 1 hour of release
- If a 15m or 5m strategy fires 20 minutes after NFP numbers, the ATR-based stop (1.5 ATR calc'd on pre-NFP volatility) is **too tight**
- Hardcoded FOMC dates block all trading — this is protective but overly broad (trading may be fine during the morning before the 14:00 announcement)

---

# FIREWALL EFFECTIVENESS ASSESSMENT

The system has a commendable multi-layer firewall architecture. Assessment of each gate:

| Gate | Effectiveness | Gap |
|------|--------------|-----|
| `execution_firewall_decision()` | Strong — checks env flags, daily plan, monitor, live readiness | Daily plan file is user-editable markdown; machine parse is fragile |
| `data_freshness_gate` | Good — blocks on stale data | Single point of failure on TV WS; no degraded mode |
| `session_gate` | Good — blocks outside hours | Missing CME holidays, early closes |
| `macro_context` | Weak — advisory only | Returns `REDUCED` not `NO_TRADE` for most events |
| `new_arsenal_gate` | Moderate — reads 8+ signal types | Can be contradictory; no hard override |
| `kill_switch.json` | Exists but **unused** | No code reads this file to flatten positions |
| `topstepCompliance` | Local-only, no enforcement | No broker sync, resets on restart |

---

# RECOMMENDATIONS (Priority Order)

1. **[CRITICAL] Implement position reconciliation**: On each startup, query TopstepX for open positions and orders. Reject duplicate orders. Restore OCO brackets for any unprotected open positions.

2. **[CRITICAL] Add atomic state writes**: Use write-to-temp-then-rename pattern for all state JSON files. Add file locking for concurrent cron access.

3. **[CRITICAL] Add intraday position monitoring**: Daemon process that checks position status every 30s, updates trailing stops, monitors P&L, and flattens on conditions (kill switch triggered, daily loss limit hit, circuit breaker).

4. **[CRITICAL] Implement CSV→live data parity verification**: Run a daily comparison of CSV bar data vs broker real-time data. Flag discrepancies. Don't trade strategies on symbols where parity is broken.

5. **[HIGH] Add CME holiday calendar**: Import CME holiday schedule. Block trading on full-close days. Adjust close times for early-close days.

6. **[HIGH] Implement distributed cron locking**: Use file-based or Redis-based mutex for all state-mutating cron jobs. Add minimum inter-execution delays.

7. **[HIGH] Fix position sizing for ES**: Use `POINT_VALUES` dict from `pre_trade_check.py` in master bridge's `calc_position()`.

8. **[HIGH] Add auto-trade-halt around high-impact events**: 30 min before / 15 min after NFP, CPI, FOMC, etc.

9. **[MEDIUM] Add degraded-mode trading**: When data freshness is borderline, allow 0.5x sized trades instead of blocking entirely.

10. **[MEDIUM] Replace hardcoded date lists**: Implement web-based lookup for FOMC and macro calendar.

11. **[MEDIUM] Add partial fill handler**: After order submission, poll for fill status. Adjust or cancel unfilled legs.

---

*End of External/Operational Risk Audit*
