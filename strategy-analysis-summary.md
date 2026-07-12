# Hedge Trading System - Strategy Performance Analysis
## Based on checks from /Users/brain/hedge

### 1. Strategy Factory Latest Run (.rumbling-hedge/state/strategy-factory.latest.json)
- **Status**: BLOCKED
- **Reason**: Walkforward not deployable (0/3 rolling OOS deployable windows, need 3/3)
- **Selected Profile**: opec-fade-index
- **Tested Strategies**: opec-fade, eia-inventory
- **Supported Strategies**: 40+ strategies listed (including ICT, WorldQuant alphas, proprietary scalps, etc.)

### 2. No-Edge Ledger (.rumbling-hedge/research/no-edge-ledger/latest.json)
- **Total Profiles Evaluated**: 37
- **Promotable**: 0
- **No-Edge (Failed)**: 12
- **Needs More Data**: 25
- **Blocked**: 0

**No-Edge Strategies** (failed OOS testing):
- cross-sectional-momentum
- ict-displacement
- ict-displacement-5m
- ict-narrative
- ict-sweep-reversion
- ict-breakout
- liquidity-reversion
- session-momentum
- structural-flows
- vwap-reversion
- ret-30-momentum
- wq-alpha-001, wq-alpha-002, wq-alpha-003, wq-alpha-006, wq-alpha-007, wq-alpha-008
- wq-alpha-020, wq-alpha-024, wq-alpha-033, wq-alpha-044, wq-alpha-053, wq-alpha-054
- wq-alpha-057, wq-alpha-065, wq-alpha-101
- wq-alpha-001-rust, wq-alpha-009-rust, wq-alpha-012-rust

### 3. Strategy Classification Map (src/domain.ts)
**SOURCE OF TRUTH FOR STRATEGY CLASSIFICATIONS**

#### 🔴 QUARANTINED (Tested, Failed OOS - No-Edge Ledger Confirmed)
These strategies have been tested and failed - they should not be traded:
```
ict-displacement, ict-displacement-5m, liquidity-reversion, session-momentum,
structural-flows, ret-30-momentum, vwap-reversion, cross-sectional-momentum,
wq-alpha-001, wq-alpha-002, wq-alpha-003, wq-alpha-006, wq-alpha-007, wq-alpha-008,
wq-alpha-020, wq-alpha-024, wq-alpha-033, wq-alpha-044, wq-alpha-053, wq-alpha-054,
wq-alpha-057, wq-alpha-065, wq-alpha-101, wq-alpha-009, wq-alpha-012, wq-alpha-021,
wq-alpha-049, wq-alpha-083, opening-range-reversal
```

#### 🟠 BRONZE (Implemented, Builds Signals, Never Through Backtest/OOS/Demo)
These strategies exist but have not been validated through testing:
```
short-term-reversal, opening-stop-hunt, ict-narrative, ict-sweep-reversion,
ict-breakout, expiry-flow, pairs-trading, volatility-regime, bollinger-squeeze,
donchian-breakout, prop-fvg-scalp, prop-liq-grab, prop-orb-scalp, prop-vwap-bounce,
prop-momentum-scalp, tick-scalp, zscore-mean-rev, open-drive-fade, time-based-exit,
range-bound-scalp, drift-regime-csm, hmm-pairs-arb, gamma-stability,
llm-momentum-gate, two-level-uncertainty, llm-ga-evolutionary,
drawdown-momentum, push-response-anomaly, intraday-momentum, optimal-cost-pairs,
network-momentum, vol-targeted-momentum, capitulation-score, event-spike-fade,
post-news-settlement, options-selling-framework, kronos-direction, gap-fade-regime,
monthly-seasonality, regime-locked-momentum, rsi2-mean-reversion, vol-risk-premium,
cot-positioning, vix-term-structure, cpi-reaction, opec-fade, eia-inventory,
gamma-pin, wq-alpha-009-rust, wq-alpha-001-rust, wq-alpha-012-rust
```

#### ⚪ GOLD / SILVER
**NONE** - No strategies have achieved GOLD (proven edge with ≥20 demo trades) or SILVER (backtest profit factor >1.2, OOS passed) status.

### 4. Promotion Status (npm run bill:promotion-status --silent)
- **Current Stage**: research
- **Recommended Stage**: research
- **Blockers**: 
  - no-watch-candidates
  - no-paper-candidates
  - lead-candidate-not-paper-trade
- **Notes**: Keep lane in research mode. Improve cross-venue normalization or narrow source universe.

### 5. All Registered Strategy IDs (src/domain.ts SUPPORTED_STRATEGY_IDS)
Total: 95 strategies registered, including:
- ICT strategies (displacement, narrative, sweep-reversion, breakout, etc.)
- WorldQuant 101 Alphas (wq-alpha-001 through wq-alpha-101)
- Proprietary scalps (prop-fvg-scalp, prop-liq-grab, prop-orb-scalp, prop-vwap-bounce, prop-momentum-scalp)
- Traditional strategies (session-momentum, opening-range-reversal, liquidity-reversion, etc.)
- Momentum/mean-reversion strategies (ret-30-momentum, vwap-reversion, bollinger-squeeze, etc.)
- Macro/regime strategies (volatility-regime, drift-regime-csm, hmm-pairs-arb, gamma-stability)
- LLM/AI strategies (llm-momentum-gate, two-level-uncertainty, llm-ga-evolutionary)
- Alternative data strategies (capitulation-score, cot-positioning, vix-term-structure, cpi-reaction, opec-fade, eia-inventory, gamma-pin)
- Rust implementations (wq-alpha-009-rust, wq-alpha-001-rust, wq-alpha-012-rust)

### 6. Futures Demo Samples (.rumbling-hedge/logs/futures-demo-samples.jsonl)
The file contains demo process logs but no individual trade executions in the expected format. Entries show:
- Demo overnight commands
- Data refresh status
- Preflight checks
- No actual trade signals or executions visible in the tail

## SUMMARY: CURRENT STRATEGY PERFORMANCE STATE

| Classification | Count | Strategies |
|----------------|-------|------------|
| **🔴 QUARANTINED** (Failed OOS) | 26 | ict-displacement, ict-displacement-5m, liquidity-reversion, session-momentum, structural-flows, ret-30-momentum, vwap-reversion, cross-sectional-momentum, wq-alpha-001-008, wq-alpha-020, wq-alpha-024, wq-alpha-033, wq-alpha-044, wq-alpha-053, wq-alpha-054, wq-alpha-057, wq-alpha-065, wq-alpha-101, wq-alpha-009, wq-alpha-012, wq-alpha-021, wq-alpha-049, wq-alpha-083, opening-range-reversal |
| **🟠 BRONZE** (Unverified) | 69 | All other registered strategies including: short-term-reversal, opening-stop-hunt, ict-narrative, ict-sweep-reversion, ict-breakout, expiry-flow, pairs-trading, volatility-regime, bollinger-squeeze, donchian-breakout, prop-* scalps, tick-scalp, zscore-mean-rev, open-drive-fade, time-based-exit, range-bound-scalp, drift-regime-csm, hmm-pairs-arb, gamma-stability, llm-* strategies, drawdown-momentum, push-response-anomaly, intraday-momentum, optimal-cost-pairs, network-momentum, vol-targeted-momentum, capitulation-score, event-spike-fade, post-news-settlement, options-selling-framework, kronos-direction, gap-fade-regime, monthly-seasonality, regime-locked-momentum, rsi2-mean-reversion, vol-risk-premium, cot-positioning, vix-term-structure, cpi-reaction, opec-fade, eia-inventory, gamma-pin, wq-alpha-009-rust, wq-alpha-001-rust, wq-alpha-012-rust |
| **⚪️ GOLD** (Proven Edge) | 0 | None |
| **⚪️ SILVER** (Backtest Validated) | 0 | None |

## KEY FINDINGS:
1. **NO STRATEGIES ARE CURRENTLY TRADABLE** - All strategies are either QUARANTINED (failed) or BRONZE (unverified)
2. **STRATEGY FACTORY IS BLOCKED** - Cannot promote strategies due to insufficient OOS walkforward windows (0/3 deployable, need 3/3)
3. **RESEARCH MODE ONLY** - Promotion system recommends staying in research mode with no paper or watch candidates available
4. **EXTENSIVE STRATEGY LIBRARY** - 95 total strategies registered across multiple methodologies (ICT, quant, proprietary, macro, AI/LLM)
5. **NO VALIDATED EDGE** - Despite large strategy library, none have demonstrated sufficient statistical edge for promotion to paper/live trading

## RECOMMENDATION:
Focus research efforts on improving the BRONZE strategies through:
1. Better data quality and frequency
2. More robust walk-forward validation
3. Improved risk management and transaction cost modeling
4. Ensemble approaches combining multiple weak signals
5. Deeper investigation into why quant strategies (WQ alphas) are failing in current regime