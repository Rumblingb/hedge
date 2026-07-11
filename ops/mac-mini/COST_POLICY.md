# Bill Cost Policy

Bill should be cheap by default and expensive only when expected value is clear.

## Runtime order

1. Native Bill jobs first
- health
- prediction scan
- prediction report
- paper/demo loops
- live-readiness checks

2. Hosted free or budget model second
- classify
- summarize
- route
- narrow search plans
- cheap critique

3. Hosted stronger budget model third
- coding
- strategy synthesis
- architecture changes
- promotion-board style reviews

4. Local Ollama fallback last
- only for degraded mode, background repair work, or offline continuity
- not the primary founder or worker brain

## Default model stack

- OpenRouter hosted free: `inclusionai/ling-2.6-flash:free`
- OpenRouter coding/reasoning free: `qwen/qwen3-coder:free`
- OpenRouter budget review: `deepseek/deepseek-v3.2`
- OpenRouter deeper review: `deepseek/deepseek-v3.2-speciale`
- Current NVIDIA fallback after smoke test: `qwen/qwen3-coder-480b-a35b-instruct` for routine review and `deepseek-ai/deepseek-v4-flash` for deeper review.
- local fallback light: `ollama/qwen2.5-coder:7b`
- local fallback heavy: `ollama/qwen2.5-coder:14b`

## Cost rules

- Do not burn a paid model for recurring health or report jobs when a free hosted model will do.
- Keep Bill's secure env on OpenRouter when funded; `npm run bill:nim-smoke` must pass through the same secure env wrapper before model changes are trusted.
- Use a bounded default budget of 40 hosted calls and 1.2M hosted tokens per day; raise it only when a research/promotion run has a concrete expected value.
- Disable hosted reasoning by default for short automation calls unless a specific deep-review task needs it; this avoids empty-content responses from reasoning-heavy preview routes.
- Do not run overlapping scheduled LLM loops when native jobs already produce the needed artifact.
- Keep one active cashflow wedge at a time.
- Keep one paid deep-reasoning lane at a time.
- Keep paid hosted output below `$1.50 / 1M` unless the founder explicitly widens that boundary.

## Quant box interpretation

There is no separate local runtime named `quant box` in the current machine state.

For this system, Bill's quant box is the `hedge` repo plus its guarded runtime:
- research
- backtest
- OOS
- paper/demo
- reporting
- promotion gating
- kill switch

If a future standalone quant service is added, it should plug into Bill as infrastructure, not become a second autonomous brain.
