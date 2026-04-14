# Bill Cost Policy

Bill should be cheap by default and expensive only when expected value is clear.

## Runtime order

1. Native Bill jobs first
- health
- prediction scan
- prediction report
- paper/demo loops
- live-readiness checks

2. Local light model second
- classify
- summarize
- route
- narrow search plans
- cheap critique

3. Local heavy model third
- coding
- strategy synthesis
- architecture changes
- promotion-board style reviews

4. Cloud review last
- only for bounded, high-value questions
- promotion readiness
- contradictory evidence review
- difficult code/risk critiques

## Default model stack

- local light: `ollama/qwen2.5-coder:7b`
- local heavy: `ollama/qwen2.5-coder:14b`
- cloud review: `openai/gpt-5.4-mini`
- deep cloud review: `openai/gpt-5.4`

## Cost rules

- Do not burn a heavy model for recurring health or report jobs.
- Do not run overlapping scheduled LLM loops when native jobs already produce the needed artifact.
- Keep one active cashflow wedge at a time.
- Keep one heavy reasoning lane at a time.
- Use cloud review only when the decision can change capital, risk posture, or architecture.

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
