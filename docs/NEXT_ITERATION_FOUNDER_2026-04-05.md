# Founder Iteration Plan 2026-04-05

## Objective

Move from a strategy sandbox to a disciplined demo trading lab that can graduate to a local-device TopstepX execution path only after robust risk and out-of-sample evidence.

## What We Borrowed From External References

- NVIDIA quantitative portfolio optimization blueprint:
  - Scenario-driven risk modeling and optimization loop (Mean-CVaR orientation)
  - Faster iteration framing: data science -> optimization -> backtest refinement
- QuantStats:
  - Rich risk/performance diagnostics beyond win rate and total return
  - Focus on drawdown, distribution, and risk-of-ruin style diagnostics
- KX documentation:
  - Production mindset for market data and execution telemetry systems
  - Event-driven, low-latency architecture direction for future live path
- World Cup / Robbins-style winner study posture:
  - Keep strategy complexity low, selectivity high, and strict risk rails
  - Prefer stable repeatability over one-regime optimization

## This Iteration (Implemented)

1. Added trade-quality analytics to research output:
   - expectancyR
   - payoffRatio
   - avgWinR / avgLossR
   - maxConsecutiveWins / maxConsecutiveLosses
   - sharpePerTrade / sortinoPerTrade
   - ulcerIndexR
   - cvar95TradeR
   - riskOfRuinProb (bootstrap Monte Carlo)
2. Added safer Topstep adapter seam:
   - validated bracket order specification builder
   - hard checks for minimum RR and max contracts before order handoff

## Next Two Founder Lanes

### Lane A: Data and Backtest Fidelity

- Source alternatives to Yahoo-minute slices:
  - CME DataMine exports
  - Topstep-compatible feed exports
  - broker/platform exports with clear session and rollover handling
- Add continuous contract handling and rollover diagnostics
- Add spread/slippage stress by session regime (open, midday, close)

### Lane B: Portfolio/Risk Layer

- Add simple family-level budget optimizer using constrained risk budget:
  - objective: maximize expected net R under drawdown and concentration caps
  - constraints: per-family max weight, turnover cap, minimum evidence count
- Add rolling walk-forward windows (multiple splits) instead of one split
- Promote only if profile and family rank persistence are stable across windows

## TopstepX / ProjectX Readiness Gates

- Gate 1: Data quality green across 30+ recent sessions
- Gate 2: Net-positive test performance across multiple walk-forward windows
- Gate 3: Drawdown and risk-of-ruin below founder thresholds
- Gate 4: Full audit logging + kill switch + local-device compliance
- Gate 5: Small-size paper shadow run before any funded-account deployment

## Profitability Expectation

No honest system can guarantee profitability.

What we can guarantee is process quality:
- strict risk limits
- reproducible research outputs
- measurable model degradation detection
- controlled deployment gates

If this process remains green over enough out-of-sample data, profitability probability improves. If it does not, we prune and iterate.
