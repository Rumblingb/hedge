# Bill/Hedge Strategy Inventory — Source of Truth
Generated: 2026-05-13
Canonical: `/Users/brain/hedge`

## Classification Standard
| Tag | Meaning | Requirement |
|-----|---------|-------------|
| **GOLD** | Proven edge, live trades | ≥20 demo trades, positive expectancy, OOS passed |
| **SILVER** | Backtest edge, no demo | Backtest profit factor >1.2, OOS passed |
| **BRONZE** | Implemented, untested | File exists, builds signals, never backtested |
| **SKELETON** | Name only | No implementation file, or stub with no real logic |
| **QUARANTINED** | Tested, no edge | Failed OOS, no-edge ledger entry exists |

---

## Gold Strategies (4 in Rust, 0 in TS pipeline)

| ID | File | Lines | Logic | Status | Classification |
|----|------|-------|-------|--------|---------------|
| lw_donchian_breakout | bill-core/src/gold_strategies.rs | 107 total | Donchian(20) breakout | ✅ Real, calls existing helper | **GOLD-stub** (proven in Rust, not wired to TS pipeline) |
| gapper_edge | bill-core/src/gold_strategies.rs | — | Gap >2% heuristic | ✅ Real, simple logic | **BRONZE** (no backtest, no demo) |
| polymarket_edge_detector | bill-core/src/gold_strategies.rs | — | Returns Signal::default() | ❌ STUB — empty placeholder | **SKELETON** |
| order_flow_80_20 | bill-core/src/gold_strategies.rs | — | References non-existent `order_flow_signal` | ❌ BROKEN — won't compile | **SKELETON** |

**Reality**: 2 of 4 gold strategies have real logic. 0 are wired into the TS demo pipeline. The gold-auto-implementation skill exists but never ran end-to-end.

---

## Implemented Strategies (76 files in src/strategies/)

### Quarantined (24 — no-edge ledger confirmed)
These have been tested and failed OOS:
`cross-sectional-momentum`, `ict-displacement-5m`, `ict-displacement`, `liquidity-reversion`, `session-momentum`, `short-term-reversal`, `structural-flows`, `opening-range-reversal`, `vwap-reversion`, `wq-alpha-033`, `wq-alpha-057`, `wq-alpha-065`, `wq-alpha-001`, `wq-alpha-006`, `wq-alpha-020`, `wq-alpha-053`, `wq-alpha-054`, `wq-alpha-101`, `wq-alpha-002`, `wq-alpha-003`, `wq-alpha-007`, `wq-alpha-008`, `wq-alpha-024`, `wq-alpha-044`

**All classification: QUARANTINED** — no-edge ledger evidence, 0 demo trades.

2026-05-13 correction: `short-term-reversal` and `ret-30-momentum` are **BRONZE**, not SILVER, until they pass canonical walk-forward, rolling OOS, stressed live-readiness, and paper/demo fill evidence. Ad-hoc Python profit-factor runs are research hints only.

### Implemented but Never Tested (52 files)
These files exist and produce signals, but have NEVER been through backtest/OOS/demo:

| File | Lines | Has buildSignal | Domain ID? | Classification |
|------|-------|-----------------|------------|---------------|
| advancedPatterns | 101 | ✅ | No (advanced-patterns not in domain) | BRONZE → SKELETON (orphan file) |
| adxDonchian | 42 | ✅ | No | BRONZE → SKELETON (orphan) |
| bollingerSqueeze | 37 | ✅ | ✅ bollinger-squeeze | BRONZE |
| capitulationScore | 172 | ✅ | ✅ capitulation-score | BRONZE |
| carryTrade | 118 | ✅ | ✅ carry-trade | BRONZE |
| chartPatterns | 97 | ✅ | No | BRONZE → SKELETON (orphan) |
| commodsCorrelation | 97 | ✅ | No | BRONZE → SKELETON (orphan) |
| deltaDivergence | 29 | ✅ | ✅ delta-divergence | BRONZE |
| drawdownMomentum | 155 | ✅ | ✅ drawdown-momentum | BRONZE |
| driftRegimeCSM | 220 | ✅ | ✅ drift-regime-csm | BRONZE |
| enhancedOrb | 212 | ✅ | No | BRONZE → SKELETON (orphan) |
| eventDriven | 91 | ✅ | ✅ event-driven | BRONZE |
| eventSpikeFade | 126 | Minimal | ✅ event-spike-fade | BRONZE |
| eventStrategies | 58 | ✅ | No | BRONZE → SKELETON (orphan) |
| expiryFlow | 239 | ✅ | ✅ expiry-flow | BRONZE |
| finalFour | 55 | ✅ | No | BRONZE → SKELETON (orphan) |
| flowMacro | 84 | ✅ | No | BRONZE → SKELETON (orphan) |
| gammaStability | 239 | Minimal | ✅ gamma-stability | BRONZE |
| gapFade | 72 | ✅ | ✅ gap-fade | BRONZE |
| gapFadeRegime | 219 | ✅ | ✅ gap-fade-regime | BRONZE |
| hmmPairsArb | 254 | Minimal | ✅ hmm-pairs-arb | BRONZE |
| ichimoku | 40 | ✅ | ✅ ichimoku | BRONZE |
| ictBreakout | 129 | Minimal | ✅ ict-breakout | BRONZE |
| ictNarrative | 121 | Minimal | ✅ ict-narrative | BRONZE |
| ictSweepReversion | 144 | Minimal | ✅ ict-sweep-reversion | BRONZE |
| intradayMomentum | 154 | ✅ | ✅ intraday-momentum | BRONZE |
| kronosDirection | 106 | ✅ | ✅ kronos-direction | BRONZE |
| llmGaEvolutionary | 430 | Minimal | ✅ llm-ga-evolutionary | BRONZE |
| llmMomentumGate | 195 | ✅ | ✅ llm-momentum-gate | BRONZE |
| macdKeltner | 55 | ✅ | No | BRONZE → SKELETON (orphan) |
| macroEvents | 64 | ✅ | No | BRONZE → SKELETON (orphan) |
| macroFlow | 51 | ✅ | No | BRONZE → SKELETON (orphan) |
| marketMicrostructure | 100 | ✅ | No | BRONZE → SKELETON (orphan) |
| marketOpenDrive | 81 | ✅ | ✅ market-open-drive | BRONZE |
| marketProfile | 39 | ✅ | ✅ market-profile | BRONZE |
| monthlySeasonality | 166 | ✅ | ✅ monthly-seasonality | BRONZE |
| networkMomentum | 156 | Minimal | ✅ network-momentum | BRONZE |
| newsSpikeFade | 78 | ✅ | ✅ news-spike-fade | BRONZE |
| novelML | 78 | ✅ | No | BRONZE → SKELETON (orphan) |
| openingStopHunt | 146 | ✅ | ✅ opening-stop-hunt | BRONZE |
| optimalCostPairs | 143 | Minimal | ✅ optimal-cost-pairs | BRONZE |
| optionsSellingFramework | 316 | ✅ | ✅ options-selling-framework | BRONZE |
| optionsVolRenko | 64 | ✅ | No | BRONZE → SKELETON (orphan) |
| oscillatorPatterns | 68 | ✅ | No | BRONZE → SKELETON (orphan) |
| overnightHold | 78 | ✅ | ✅ overnight-hold | BRONZE |
| pairsTrading | 142 | ✅ | ✅ pairs-trading | BRONZE |
| postNewsSettlement | 126 | Minimal | ✅ post-news-settlement | BRONZE |
| powerHour | 89 | ✅ | ✅ power-hour | BRONZE |
| pricePatterns | 61 | ✅ | No | BRONZE → SKELETON (orphan) |
| propEdgeStrategies | 68 | ✅ | No | BRONZE → SKELETON (orphan) |
| propOptimized | 67 | ✅ | No | BRONZE → SKELETON (orphan) |
| pushResponseAnomaly | 127 | Minimal | ✅ push-response-anomaly | BRONZE |
| quantitativeStrategies | 106 | ✅ | No | BRONZE → SKELETON (orphan) |
| regimeLockedMomentum | 169 | ✅ | ✅ regime-locked-momentum | BRONZE |
| rsi2MeanReversion | 150 | ✅ | ✅ rsi2-mean-reversion | BRONZE |
| rsiDivergence | 30 | ✅ | ✅ rsi-divergence | BRONZE |
| scalping | 76 | ✅ | ✅ scalping | BRONZE |
| seasonality | 32 | ✅ | ✅ seasonality | BRONZE |
| sessionFlow | 60 | ✅ | No | BRONZE → SKELETON (orphan) |
| shortTermReversal | 170 | ✅ | ✅ short-term-reversal | QUARANTINED |
| supplyDemand | 106 | ✅ | ✅ supply-demand | BRONZE |
| twoLevelUncertainty | 268 | ✅ | ✅ two-level-uncertainty | BRONZE |
| volatilityRegime | 191 | ✅ | ✅ volatility-regime | BRONZE |
| volRiskPremium | 193 | ✅ | ✅ vol-risk-premium | BRONZE |
| volTargetedMomentum | 180 | ✅ | ✅ vol-targeted-momentum | BRONZE |
| vwapReversion | 21 | ✅ | ✅ vwap-reversion | QUARANTINED |
| wctcEnsemble | 154 | Minimal | No | BRONZE → SKELETON (orphan) |
| worldquantAlphas | 344 | ✅ | No | BRONZE → SKELETON (orphan) |
| worldquantAlphas2 | 176 | ✅ | No | BRONZE → SKELETON (orphan) |

---

## Registered Names Without Implementation (108 SKELETONS)

These exist ONLY as strings in `SUPPORTED_STRATEGY_IDS` in `domain.ts`. No file, no code, no logic:

`adx-trend`, `algo-execution`, `auction-imbalance`, `block-trade-fade`, `breakout-retest`, `btc-correlation`, `closing-auction`, `copper-gold-ratio`, `correlation-switch`, `cot-positioning`, `cpi-reaction`, `credit-spread`, `cross-asset-rotation`, `cross-venue-arb`, `dark-pool-print`, `dispersion-trading`, `dollar-smile`, `donchian-breakout`, `double-top-bottom`, `econ-surprise`, `eia-inventory`, `engulfing-pattern`, `ensemble-meta`, `event-arbitrage`, `false-breakout`, `fed-put-strategy`, `flag-pennant`, `gamma-pin`, `gamma-scalp`, `gold-silver-ratio`, `harnet-vol`, `hawkes-process`, `head-shoulders`, `heikin-ashi`, `implied-correlation`, `inflation-breakeven`, `initial-balance`, `inside-bar`, `keltner-channel`, `liquidity-cascade`, `macd-crossover`, `market-structure`, `momentum-crash`, `momentum-ignition`, `multi-timeframe`, `natgas-seasonality`, `nfp-reaction`, `oil-crack-spread`, `opec-fade`, `open-drive-fade`, `opening-auction`, `optimal-execution`, `order-flow-imbalance`, `overnight-drift`, `pairs-convergence`, `pin-bar`, `post-fomc-fade`, `pre-fomc-drift`, `pre-market-reversal`, `prop-fvg-scalp`, `prop-liq-grab`, `prop-momentum-scalp`, `prop-orb-scalp`, `prop-vwap-bounce`, `put-call-signal`, `range-bound-scalp`, `regime-probability`, `renko-momentum`, `risk-parity-rebalance`, `rl-inspired`, `stochastic`, `tail-risk`, `tick-scalp`, `time-based-exit`, `trendline-break`, `uncertainty-sizing`, `value-area-rotation`, `vix-term-structure`, `vol-premium`, `vol-skew`, `volatility-of-vol`, `volume-spike`, `wedge-breakout`, `wq-alpha-009`, `wq-alpha-012`, `wq-alpha-021`, `wq-alpha-049`, `wq-alpha-083`, `yield-curve-steepen`, `zero-dte-flow`, `zscore-mean-rev`

**Classification: SKELETON** — names only, no code, zero trades.

---

## Orphan Files (25 — not registered in domain.ts)

`advancedPatterns`, `adxDonchian`, `chartPatterns`, `commodsCorrelation`, `enhancedOrb`, `eventStrategies`, `finalFour`, `flowMacro`, `ictDisplacement5m`, `macdKeltner`, `macroEvents`, `macroFlow`, `marketMicrostructure`, `novelML`, `optionsVolRenko`, `oscillatorPatterns`, `pricePatterns`, `propEdgeStrategies`, `propOptimized`, `quantitativeStrategies`, `sessionFlow`, `wctcEnsemble`, `worldquantAlphas`, `worldquantAlphas2`, `driftRegimeCSM`

**Immediate action**: Either register them or remove. These files exist but the pipeline doesn't know about them.

---

## Actual Edge Evidence (ALL sources)

### Prediction Markets
- **94 fills total**: 89 dry-run, 5 real
- **Real fills**: 3 unknown (no marketSlug data), 2 FAILED ("us-recession-by-end-of-2026", $0.92 each)
- **Dry-run edges**: NBA MVP (1.43x), GTA VI (1.43x), Next Leader (1.42x), Fed Decision (1.37x), Seoul Mayor (1.1x), EPL (0.7x), MicroStrategy BTC (0.7x), House 2026 (0.5x)
- **Wallet**: $10.17 USDC on Polygon, NOT deposited on Polymarket CLOB
- **Real fills since**: May 6, 2026 (none since)

### Futures Demo (Topstep)
- **0 trades ever** — NQ challenge: $0 PnL, 0 trades, all setup journals empty
- **8 demo sample runs**: all show `action=stand-down`, `deployable=false`, 0 candidates with score >0
- **Demo override**: Force-enabled via env var (not pipeline-approved)

### Gold Strategies (Rust)
- 2 real functions, 1 stub, 1 broken
- None wired into TS pipeline
- Gold auto-implementation skill: exists, never ran

### Overall
- **0 strategies have ever produced a demo or live trade with positive expectancy**
- **110 strategy IDs** → 76 files → ~52 real implementations → 24 quarantined → 0 with demo trades
- **Pipeline produces zero executable trade signals**
