# Research Memo 2026

## Founder view

The shortest path to a credible Topstep demo edge is not a flashy autonomous hedge fund. It is a disciplined futures lab that combines:

- Topstep-compliant automation
- session-specific strategies
- liquid market focus
- evaluation-driven iteration
- human-reviewed promotion of changes

## What the latest sources suggest

### 1. Topstep wants realistic, local-device automation

Topstep currently allows automated strategies in Trading Combine and funded accounts, but explicitly pushes traders toward Practice first and disclaims responsibility for malfunctions. TopstepX API access also says activity must come from your own device and that VPS, VPNs, and remote servers are prohibited.

### 2. For chart-based futures work, RTH matters more than overnight noise

Topstep's own RTH/ETH guidance says regular trading hours have more institutional activity, better liquidity, and more stable price action. It also highlights gap trading, breakout trading, and volume-profile/supply-demand work as strategies that benefit from RTH filtering.

### 3. WCTC standings show real outliers, but exact reverse engineering remains inference

The official World Cup Trading Championship standings as of April 1, 2026 show very large returns for current futures leaders including Eugen Denisenko, Robert Galus, Inna Rosputnia, Thanh Nam Pham, and Pau Perdices Bellet. The 2025 futures winners include Tirutrade AG, Marci Silfrain, Andrea Marenda, Kaiqi Wu, and Ruben Martinez.

We do not have official code or audited rulesets for these traders. Any reverse engineering from public materials is inference, not fact.

### 4. Public champion-adjacent material still points to a usable pattern

Public mentor material around repeated WCTC names leans heavily toward:

- auction theory
- market microstructure
- structural imbalance
- order flow
- counter-trend entries at exhaustion
- patient swing or intraday-swing execution

That argues for a small number of high-selectivity setups rather than constant scalping.

### 5. Serious futures hedge funds still rely on boring, durable ideas

Recent Man AHL research is useful here. Their 2023 trend-following note says faster trend models can improve defensive properties, but execution costs matter. Their January 29, 2026 market-mix note says liquid futures and forwards remain highly attractive because they are liquid, transparent, operationally simple, and can capture major macro factors across markets.

For our use case, the direct translation is:

- keep the instrument set liquid
- prefer a few clean speeds instead of one
- volatility/risk scaling matters
- execution quality matters more than clever story-telling

### 6. The best agentic finance work is about research acceleration, not blind live autonomy

Man Group's October 15, 2025 note on "AI, Agents and Trend" is the cleanest framing: off-the-shelf LLM output is usually plausible but inactionable without proprietary context, testing protocols, cost models, and evaluation.

That is why Rumbling Hedge treats agents as research and gating infrastructure, not as unrestricted live traders.

The cheap/free stack I would actually use in 2026 is:

- `Ollama` for local, low-cost model calls and first-pass summaries
- `LangGraph` for controllable orchestration, long-running state, and human-in-the-loop checkpoints
- `AutoGen` for small critique or debate panels when we want a second opinion
- `PydanticAI` for typed agent outputs and strict schema validation
- `Qlib` for the quant research spine: data, model, backtest, analysis, and workflow management
- `RD-Agent` for automating research loops around factor and model proposal

The boundary matters more than the tools:

- agents can propose, compare, summarize, and critique
- the quant engine decides what survives backtest and walk-forward testing
- humans decide what is promoted

## What changed in code from this research

- Research profiles now compare `topstep-index-open`, `index-core-breadth`, `liquid-core-mix`, `trend-only`, `balanced-wctc`, and `strict-news`
- Synthetic research now builds bars from the union of all research universes instead of a single default slice
- Research summaries now include per-symbol contribution breakdowns, not just total profile score
- Index opening behavior remains separated from generic cross-asset momentum
- Reversion remains constrained to early-session index conditions
- The default config stays on `session-momentum` until real-data research validates a richer profile

## Current recommendation

Start demo-first with:

- `NQ`, `ES`, `CL`, `GC`, `6E`, then test `ZN` as the first rates add-on
- opening-range reversal for equity indexes
- delayed session momentum for all approved liquid symbols
- strict RTH focus
- offline promotion only after walk-forward validation

Do not start with:

- all Topstep markets at once
- full-day trading
- live self-modifying agents
- VPS-based automation
- news-chasing during major events with max size

## Next best build steps

1. Feed real minute-bar CSVs into `npm run research`.
2. Add per-symbol and market-family risk budgeting now that contribution data is visible.
3. Add a local-only Topstep adapter when the paper engine is stable on real data.
4. Add agentic research roles only where they improve evaluation, memoing, or news tagging.
5. Keep the live path human-controlled and local-device only if it ever becomes relevant.
