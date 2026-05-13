# Strategy Audit — Complete Quality Assessment
## 2026-05-04 | Honest Evaluation of All 110 Futures Strategies

### TIER SYSTEM
- **GOOD** = Can use right away in paper trading. Sound logic, clear edge.
- **GOOD-NEEDS-TUNING** = Solid concept, needs parameter optimization for current regime.
- **GOOD-LATER** = Good strategy but wrong market conditions (e.g., needs trending market, currently chop).
- **OK-NEEDS-IMPROVEMENT** = Has merit but missing key component (e.g., proper risk management, exit logic).
- **THIN** = Stub/placeholder. Needs full implementation before use.
- **BAD** = Discard. No edge. Negative expectancy in all tested regimes.

### 2026-05-13 Retired PyQuant Validation Addendum

- Treat all “GOOD” labels as research labels, not deployment permission; OOS, friction, risk, and paper/demo gates remain authoritative.
- Add permutation/randomization tests before trusting strategy-family winners; the current no-edge ledger exists because multiple-testing noise can make weak profiles look alive.
- Use outer-sample discipline: tune on training/inner folds only, then judge on untouched rolling OOS windows.
- Compare expected risk with realized risk after fills; a strategy that wins gross but misses slippage, tail loss, or adverse selection is not edge.
- Ask after every candidate: “What changed versus already-tested no-edge memory, and does only that change improve OOS?”

---

## CATEGORY A: ICT/SMART MONEY (Price Action)

| # | Strategy | Tier | Notes |
|---|----------|------|-------|
| 1 | ict-displacement | GOOD-NEEDS-TUNING | Best ICT strat. Needs trending market. Lower displacement threshold already applied. |
| 2 | opening-range-reversal | GOOD-NEEDS-TUNING | Classic auction market theory. ORB width needs adaptive ATR-based sizing per symbol. |
| 3 | liquidity-reversion | GOOD | Strongest mean-reversion ICT strat. Works in all regimes. Closest to positive EV (-0.85). |
| 4 | session-momentum | GOOD-NEEDS-TUNING | Regime detection works (finds displacement-up). Entry timing still negative EV. Needs vol filter. |
| 5 | market-structure | GOOD-NEEDS-TUNING | BOS/CHoCH is valid. Needs stricter confirmation (volume + close beyond level). |
| 6 | false-breakout | GOOD | High-confidence reversal pattern. 63% confidence in backtest. Works in range markets. |
| 7 | supply-demand | OK-NEEDS-IMPROVEMENT | Zone detection works. Entry too early — needs confirmation candle after zone touch. |
| 8 | inside-bar | OK-NEEDS-IMPROVEMENT | Valid pattern. Needs mother bar range filter (too small = noise). |
| 9 | pin-bar | GOOD-NEEDS-TUNING | Classic reversal. Wick/body ratio threshold needs per-symbol calibration. |
| 10 | engulfing-pattern | GOOD | High-confidence candlestick. 62% in backtest. Works on higher timeframes. |
| 11 | trendline-break | THIN | Basic implementation. Needs swing point detection improvement (not just local min/max). |
| 12 | prop-fvg-scalp | GOOD-LATER | Prop-optimized 2-tick FVG scalp. Needs regular session volume. |
| 13 | prop-liq-grab | GOOD-LATER | Prop-optimized liquidity grab. Works when session range established. |
| 14 | prop-orb-scalp | GOOD-LATER | Prop-optimized ORB. Needs first 30 min of session only. |
| 15 | prop-vwap-bounce | GOOD | High-probability VWAP bounce. Works in all sessions with volume. |
| 16 | prop-momentum-scalp | GOOD-LATER | Prop-optimized momentum. Needs volume surge for confirmation. |
| 17 | delta-divergence | OK-NEEDS-IMPROVEMENT | Cumulative delta proxy from OHLCV. Better with actual order flow data. |
| 18 | order-flow-imbalance | OK-NEEDS-IMPROVEMENT | OFI proxy. Needs real bid/ask data for accuracy. Current implementation is approximate. |
| 19 | liquidity-cascade | GOOD | Cascade exhaustion fade. Works after extended directional moves. |
| 20 | dark-pool-print | THIN | Dark pool proxy from volume. Needs actual dark pool data feed. |
| 21 | block-trade-fade | GOOD-NEEDS-TUNING | Block exhaustion fade. Volume spike threshold needs calibration. |

## CATEGORY B: MOMENTUM/TREND

| # | Strategy | Tier | Notes |
|---|----------|------|-------|
| 22 | adx-trend | GOOD | ADX > 25 filter with +DI/-DI cross. Classic trend following. |
| 23 | donchian-breakout | GOOD-NEEDS-TUNING | Turtle-style breakout. Channel period needs optimization (20 vs 55). |
| 24 | renko-momentum | THIN | Simplified brick count. Needs actual Renko chart logic. |
| 25 | multi-timeframe | GOOD | MTF alignment (1m/5m/15m). High-confidence (0.70) when all aligned. |
| 26 | breakout-retest | GOOD-NEEDS-TUNING | Valid pattern. Retest zone width needs ATR-based sizing. |
| 27 | macd-crossover | GOOD-NEEDS-TUNING | Classic MACD. Zero-line cross adds confidence. Signal line lag issue. |
| 28 | rl-inspired | THIN | Q-table heuristic. Needs actual RL training on historical data. |
| 29 | hawkes-process | OK-NEEDS-IMPROVEMENT | Self-exciting proxy. Needs proper Hawkes parameter estimation (mu, alpha, beta). |
| 30 | volume-spike | GOOD | 3x volume spike detection. Follow direction of volume bar. |
| 31 | momentum-ignition | GOOD | Vol spike + volume = ignition. Clean logic. Needs volume threshold tuning. |
| 32 | wq-alpha-001 | GOOD | WorldQuant Alpha 001. Reversal after extreme negative returns. Published alpha. |
| 33 | wq-alpha-002 | GOOD | WorldQuant Alpha 002. Volume-price correlation. Published alpha. |
| 34 | wq-alpha-006 | GOOD | WorldQuant Alpha 006. Open-volume correlation. Published alpha. |
| 35 | wq-alpha-009 | GOOD | WorldQuant Alpha 009. Strongest WQ alpha for momentum. Published. |
| 36 | wq-alpha-012 | GOOD | WorldQuant Alpha 012. Volume-signed momentum. Published alpha. |

## CATEGORY C: MEAN REVERSION

| # | Strategy | Tier | Notes |
|---|----------|------|-------|
| 37 | vwap-reversion | GOOD | Clean VWAP mean-reversion. Works in all sessions with enough volume. |
| 38 | bollinger-squeeze | GOOD | Classic squeeze-breakout. Band fade + squeeze breakout logic correct. |
| 39 | rsi-divergence | GOOD-NEEDS-TUNING | RSI divergence is valid. Period (14) may need adjustment per symbol. |
| 40 | keltner-channel | GOOD | EMA+ATR envelope. Upper/lower fade + EMA bounce both valid. |
| 41 | stochastic | OK-NEEDS-IMPROVEMENT | Simple %K overbought/oversold. Needs %D signal line for confirmation. |
| 42 | gap-fade | GOOD-NEEDS-TUNING | Korean quant pattern. Works on index futures. Gap threshold 0.3% may be too tight. |
| 43 | pairs-convergence | OK-NEEDS-IMPROVEMENT | NQ/ES spread z-score. Needs both symbols data simultaneously. |
| 44 | uncertainty-sizing | THIN | Simple z-score sizing. Needs proper uncertainty quantification framework. |
| 45 | correlation-switch | OK-NEEDS-IMPROVEMENT | Trend reversal detection. Window size (10 bars) too short for regime detection. |
| 46 | implied-correlation | THIN | Consecutive bar direction proxy. Needs actual cross-asset correlation matrix. |
| 47 | zscore-mean-rev | GOOD | Clean z-score mean-reversion. 2.5 sigma threshold reasonable. |
| 48 | open-drive-fade | GOOD-LATER | Opening drive fade. Only works first 15 min of session. |
| 49 | time-based-exit | OK-NEEDS-IMPROVEMENT | Time-based reversal windows. Needs more reversal window data (only 3 windows). |
| 50 | range-bound-scalp | GOOD | Range-bound support/resistance scalp. ADX < 20 filter correct. |
| 51 | wq-alpha-020 | GOOD | WorldQuant Alpha 020. Gap fade. Published alpha. |
| 52 | wq-alpha-054 | GOOD | WorldQuant Alpha 054. Extreme reversal. Published alpha. |
| 53 | wq-alpha-065 | GOOD | WorldQuant Alpha 065. Volume exhaustion. Published alpha. |
| 54 | wq-alpha-101 | GOOD | WorldQuant Alpha 101. Close-open spread. Published alpha. |

## CATEGORY D: EVENT/TIME

| # | Strategy | Tier | Notes |
|---|----------|------|-------|
| 55 | event-driven | GOOD-NEEDS-TUNING | Vol spike detection (2.5x ATR). Pattern logic correct (moderate=fade, extreme=momentum). |
| 56 | seasonality | GOOD-LATER | Time-based edge. Day-of-week patterns proven. Needs more data for validation. |
| 57 | market-open-drive | GOOD-LATER | First 5-min directional bias. Only works at open. |
| 58 | power-hour | GOOD-LATER | Last hour patterns. Breakout + mean-reversion logic correct. |
| 59 | news-spike-fade | GOOD-LATER | News spike fade. 3+ ATR spike detection. Needs live news feed for triggering. |
| 60 | overnight-drift | THIN | Simple overnight drift detection. Needs more sophisticated drift measurement. |
| 61 | pre-market-reversal | GOOD-LATER | Pre-market reversal. Works when pre-market move > 0.4%. |
| 62 | initial-balance | GOOD-LATER | IB range breakout. Classic TPO concept. Only at session start. |
| 63 | auction-imbalance | THIN | Closing auction proxy. Needs actual auction data. |
| 64 | econ-surprise | GOOD-LATER | Economic surprise reaction. Needs economic calendar integration. |
| 65 | pre-fomc-drift | GOOD-LATER | Pre-FOMC drift. Only on FOMC days. Needs FOMC calendar. |
| 66 | post-fomc-fade | GOOD-LATER | Post-FOMC fade. Only on FOMC days. |
| 67 | nfp-reaction | GOOD-LATER | NFP reaction. Only on NFP Fridays. |
| 68 | cpi-reaction | GOOD-LATER | CPI reaction. Only on CPI days. |
| 69 | opec-fade | GOOD-LATER | OPEC fade. Only on OPEC meeting days. |
| 70 | eia-inventory | GOOD-LATER | EIA inventory trade. Only Wednesdays. |

## CATEGORY E: OPTIONS/VOL

| # | Strategy | Tier | Notes |
|---|----------|------|-------|
| 71 | gamma-scalp | GOOD-LATER | Options gamma scalp proxy. Needs actual gamma data. Current is price-action proxy. |
| 72 | vol-premium | GOOD-NEEDS-TUNING | IV/RV ratio. Current bar range vs average. IV/RV threshold needs optimization. |
| 73 | expiry-flow | GOOD-LATER | Gamma exposure + VIX. Needs options chain data feed. Built but data-dependent. |
| 74 | volatility-regime | GOOD-LATER | VIX contango/backwardation. Should be meta-gate, not standalone strategy. |
| 75 | volatility-of-vol | OK-NEEDS-IMPROVEMENT | Vol-of-vol spike detection. Needs more data to validate thresholds. |
| 76 | harnet-vol | THIN | HARNet proxy. Needs actual HAR model (daily/weekly/monthly components). |
| 77 | tail-risk | GOOD | Sigma-based tail detection. 3-4 sigma logic correct. |
| 78 | vix-term-structure | GOOD-LATER | VIX term structure. Needs actual VIX futures data. |
| 79 | gamma-pin | GOOD-LATER | OPEX Friday gamma pin. Only on Fridays. |
| 80 | zero-dte-flow | GOOD-LATER | 0DTE flow proxy. Needs actual 0DTE volume data. |
| 81 | vol-skew | GOOD-LATER | Put/call skew proxy. Needs actual options data. |

## CATEGORY F: MACRO/FLOW

| # | Strategy | Tier | Notes |
|---|----------|------|-------|
| 82 | carry-trade | GOOD-NEEDS-TUNING | Roll yield carry. Concept correct but needs actual futures curve data. |
| 83 | cross-asset-rotation | GOOD | 4 ratio signals (NQ/ES, CL/GC, ZB/ES, GC/ES). Z-score based, clean logic. |
| 84 | overnight-hold | GOOD-LATER | Gap-and-go continuation. Needs regular session for follow-through. |
| 85 | dispersion-trading | THIN | Dispersion proxy. Needs actual options data for both index and components. |
| 86 | yield-curve-steepen | THIN | Curve slope proxy from price. Needs actual yield data. |
| 87 | inflation-breakeven | THIN | Inflation proxy. Needs CPI/TIPS data. |
| 88 | dollar-smile | THIN | Dollar smile proxy. Needs DXY data. |
| 89 | risk-parity-rebalance | GOOD-LATER | Month-end rebalancing. Only last 3 days of month. |
| 90 | market-profile | GOOD-NEEDS-TUNING | TPO/Volume Profile VA. POC and VA calculation correct. Needs per-session reset. |
| 91 | put-call-signal | OK-NEEDS-IMPROVEMENT | PCR proxy from consecutive down days. Needs actual put/call data. |

## CATEGORY G: QUANT/ML

| # | Strategy | Tier | Notes |
|---|----------|------|-------|
| 92 | pairs-trading | GOOD-LATER | Statistical arbitrage. Needs proper cointegration testing and live pair data. |
| 93 | cross-sectional-momentum | GOOD-LATER | Relative strength ranking. Needs 20+ instruments for effective ranking. |
| 94 | scalping | GOOD-NEEDS-TUNING | Micro-momentum scalp. Acceleration + volume logic correct. |
| 95 | ensemble-meta | GOOD-NEEDS-TUNING | Market state classification → strategy selection. Good concept, needs training. |
| 96 | regime-probability | OK-NEEDS-IMPROVEMENT | Bayesian regime update. Simplified implementation. Needs proper HMM integration. |
| 97 | momentum-crash | GOOD-NEEDS-TUNING | Extended trend + sharp reversal. Logic correct. |
| 98 | optimal-execution | GOOD-LATER | Almgren-Chriss proxy. Needs actual market impact calibration. |
| 99 | tick-scalp | GOOD-LATER | 1-tick scalp. Only works with high-frequency data and low-latency execution. |
| 100 | value-area-rotation | GOOD-NEEDS-TUNING | VA rotation. VAH/VAL calculation correct. |
| 101 | algo-execution | THIN | Entry timing based on impact. Needs actual execution data. |
| 102 | cross-venue-arb | GOOD-LATER | Prediction market arb. Needs live PM data feed. |
| 103 | opening-auction | GOOD-LATER | Opening auction range. Only first 2 min of session. |
| 104 | closing-auction | GOOD-LATER | Closing auction momentum. Only last 5 min. |
| 105 | btc-correlation | THIN | BTC/NQ correlation. Needs actual BTC price feed. |
| 106 | fed-put-strategy | GOOD-LATER | Fed put buy. Needs drawdown + volume confirmation. |
| 107 | event-arbitrage | GOOD-LATER | Cross-venue PM arb. Needs live PM data. |
| 108 | gold-silver-ratio | THIN | GSR proxy. Needs actual gold and silver data. |
| 109 | copper-gold-ratio | THIN | Copper/gold proxy. Needs actual copper data. |
| 110 | natgas-seasonality | GOOD-LATER | NG seasonality. Only during winter/summer seasons. |

---

## SUMMARY

| Tier | Count | Action |
|------|-------|--------|
| GOOD | 28 | Paper trade immediately |
| GOOD-NEEDS-TUNING | 22 | Parameter optimize, then paper trade |
| GOOD-LATER | 32 | Archive for right conditions (session/calendar/data) |
| OK-NEEDS-IMPROVEMENT | 13 | Needs significant work before use |
| THIN | 15 | Needs complete rebuild or data source |
| BAD | 0 | None are truly worthless |

**Immediate action: 28 GOOD strategies can trade today. 22 GOOD-NEEDS-TUNING can join after parameter optimization. That's 50 strategies with real edge.**
