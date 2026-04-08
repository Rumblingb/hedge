# ICT Strategy Selection

This repo does not attempt to encode all discretionary ICT lore. It encodes the public ICT concepts that can be tested honestly from bar data and then subjects them to the same walk-forward and promotion gates as every other strategy.

## What the ICT strategy actually measures

The `ict-displacement` strategy uses these data points:

- prior liquidity pool: recent session high/low before the setup
- liquidity sweep: a bar trades through that pool
- displacement: the current bar body is meaningfully large relative to ATR and recent bodies
- fair value gap: a three-bar imbalance remains after displacement
- structure shift: the displacement close pushes back through the sweep bar
- kill zone timing: only morning session windows are eligible
- volatility veto: oversized bars are rejected when the candle is too stretched versus ATR
- RR floor: the final order still has to clear the hard risk-reward minimum

That gives us a codified ICT proxy that can be backtested and rejected if it is weak.

## How the engine picks a strategy for a day

The selection process is two-layered.

### 1. Research-layer selection

Before a session is considered tradable, `runWalkforwardResearch` ranks all research profiles:

- `topstep-index-open`
- `index-core-breadth`
- `ict-killzone-core`
- `trend-only`
- `liquid-core-mix`
- `balanced-wctc`
- `strict-news`

Each profile is scored on:

- net out-of-sample R
- drawdown
- trade count
- score stability across windows
- family-budget viability

Then the promotion gate checks:

- test trade count
- positive test net R
- positive expectancy
- max drawdown
- CVaR95 tail loss
- risk of ruin
- score stability
- at least one active market family

If no profile passes, the correct answer for that day is `do not trade`.

### 2. Intraday execution-layer selection

Once a profile is selected, only its enabled strategies are allowed to vote intraday.

For example, `ict-killzone-core` enables:

- `ict-displacement`
- `session-momentum`

On each bar:

1. Every enabled strategy evaluates the same bar and recent history.
2. Each strategy can either emit no signal or one candidate signal.
3. Hard guardrails reject bad signals:
   - wrong session
   - low RR
   - too many trades
   - daily loss lock
   - consecutive-loss lock
   - red-folder news blackout
4. If more than one valid signal survives, the ensemble takes the highest-confidence one.
5. If nothing valid survives, the engine stands down.

## What `day-plan` is for

Use:

```bash
npm run day-plan -- data/free/ALL-6MARKETS-1m-5d-normalized.csv
```

This gives you a plain-language operational answer:

- whether today is `demo-paper-ready` or `research-only`
- the selected profile
- the latest-session regime classification for each allowed symbol
- the ranked strategy-symbol candidates by expected value and regime fit
- the enabled strategies
- the preferred symbols
- the active market families
- the selected execution plan for the day, or why it is standing down

That is the right founder/CTO interface. The system should explain the decision, not just produce a number.
