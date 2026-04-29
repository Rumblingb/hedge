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

- hosted free: `openrouter/inclusionai/ling-2.6-flash:free`
- hosted coding/reasoning free: `openrouter/qwen/qwen3-coder:free`
- hosted budget review: `openrouter/deepseek/deepseek-v3.2`
- hosted deeper review: `openrouter/deepseek/deepseek-v3.2-speciale`
- local fallback light: `ollama/qwen2.5-coder:7b`
- local fallback heavy: `ollama/qwen2.5-coder:14b`

## Cost rules

- Do not burn a paid model for recurring health or report jobs when a free hosted model will do.
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
