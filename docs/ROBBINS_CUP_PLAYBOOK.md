# Robbins Cup Winners Playbook (Implementation-Oriented)

Date: 2026-04-05

## What top competitors did right (patterns that repeat)

1. They aggressively managed risk first, returns second.
- Daily/monthly loss limiters.
- Regime kill-switches during abnormal volatility.
- Tight controls on leverage and sequence risk.

2. They focused on robust, testable rules.
- Simple rule sets that survive across periods.
- Walk-forward / OOS discipline before live scaling.
- Limited parameter tinkering to reduce curve fit.

3. They matched strategy style to regime.
- Trend and breakout behavior in directional tape.
- Mean-reversion behavior only when volatility microstructure supports it.
- Willingness to stand down when conditions degrade.

4. They treated adaptation as controlled iteration.
- Small changes, then re-test.
- Risk-first tuning when drawdown/ruin rises.
- No blind size increase from one strong window.

## Sources used in this pass

- World Cup official standings/historical pages for winner context and timelines.
- Kevin Davey (multiple-time real-money contest winner) risk-protection notes and examples.

## What we implemented now in this repo

1. Daily-bar compatibility fixes.
- Strategies now use cross-day history on coarse bars instead of session-only history.
- Guardrails now recognize coarse bars and do not apply intraday-only entry-window checks.

2. Adaptive sample-density loop action.
- Agentic loop can now apply limited easing (RR/trade-cap direction) when trade-count is the only major blocker and hard risk checks are not failing.

3. Winner-style volatility kill switch.
- Added ATR-based bar-range kill switch for momentum/reversion/opening-reversal strategies.
- New tuning field: `volatilityKillAtrMultiple` (default `2.5`).

## Next implementation queue

1. Add explicit regime classifier (trend/chop/high-vol) and gate each strategy family by regime.
2. Add portfolio-level daily loss limiter in agentic loop decisions (not only per-strategy effects).
3. Add anti-overfit penalty in profile ranking for unstable parameter sensitivity.
4. Add robustness report section: per-window dispersion, worst-window loss, and parameter drift.
