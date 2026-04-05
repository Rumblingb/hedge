# Agentic Stack 2026

## Founder stance

If the goal is systematic profit research on a startup budget, the right 2026 agentic stack is not a fully autonomous trading organism.

It is a cheap, open-source research stack that helps us:

- summarize credible sources
- generate small experiment ideas
- enforce typed outputs
- critique strategy changes before they hit trunk
- keep a human in the promotion loop

The live risk owner remains the quant engine plus hard guardrails in code.

## Recommended stack

### 1. Ollama

Use `Ollama` as the low-cost local model runtime.

Why:

- runs locally
- cheap or free once installed
- easy REST API
- works well for summarization, tagging, classification, and memo drafting

Use it for:

- news/event labeling
- market-regime notes
- research memo generation
- offline reflection on journal output

Do not use it as the final authority for order placement.

### 2. LangGraph

Use `LangGraph` as the orchestration layer when we need durable state and human checkpoints.

Why:

- stateful graphs are better than ad hoc prompt chains
- easier to reason about review points
- strong fit for long-running research workflows

Use it for:

- planner -> coder -> reviewer research loops
- human approval before a config promotion
- memo + experiment generation

### 3. AutoGen

Use `AutoGen` only for bounded critique or debate.

Why:

- useful when we want a bull/bear/risk discussion around a research idea
- open-source and flexible

Use it for:

- red-team review of a proposed strategy
- risk critique of a parameter change

Do not let an AutoGen swarm own execution.

### 4. PydanticAI

Use `PydanticAI` whenever an agent needs to emit structured outputs.

Why:

- typed outputs reduce slop
- easier to validate before anything touches config or reports

Use it for:

- strategy proposal schemas
- news classification schemas
- experiment result summaries

### 5. Qlib

Use `Qlib` as the quant research spine when we expand beyond the current TypeScript lab.

Why:

- built for quantitative research workflows
- supports data, modeling, backtest, and analysis
- credible fit for a systematic research program

Use it for:

- larger factor or signal research
- model experiments
- more formal market-universe studies

### 6. RD-Agent

Use `RD-Agent` as inspiration or tooling for automated research loops, not live trading.

Why:

- designed around research-and-development automation
- fits the "propose -> implement -> evaluate" loop better than a generic chatbot

Use it for:

- code-generation support in research branches
- repeated experiment scaffolding
- controlled research iteration

## What stays out of bounds

- no VPS-based live routing for Topstep
- no mid-session self-modifying execution
- no agent can widen risk limits
- no autonomous promotion from research into live behavior

## Cheap-first rollout

1. `Ollama` locally for inference.
2. Current TypeScript lab for guardrails, backtest, and walk-forward checks.
3. `LangGraph` only when we need durable research workflows.
4. `PydanticAI` for typed outputs once agent-generated configs enter the loop.
5. `Qlib` or `RD-Agent` only when our real-data pipeline is stable enough to justify the added surface area.

## Source anchors

- LangGraph: https://github.com/langchain-ai/langgraph
- AutoGen: https://github.com/microsoft/autogen
- PydanticAI: https://github.com/pydantic/pydantic-ai
- Qlib: https://github.com/microsoft/qlib
- RD-Agent: https://github.com/microsoft/RD-Agent
- Ollama: https://github.com/ollama/ollama
- Topstep API access: https://help.topstep.com/en/articles/11187768-topstepx-api-access
- Topstep prohibited strategies: https://help.topstep.com/en/articles/10305426-prohibited-trading-strategies-at-topstep
- WCTC standings: https://www.worldcupchampionships.com/world-cup-trading-championship-standings
- Man Group on AI agents and trend: https://www.man.com/insights/ai-agents-trend
