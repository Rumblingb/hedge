# Context Drift Checklist

This is the safeguard for autonomous iteration.

Run it when the project has been moving for a while, before promotions, and any time the thesis starts to feel fuzzy.

## What We Are Watching

- thesis drift
- guardrail drift
- market universe drift
- source quality drift
- repo shape drift

## 10-Minute Check

### 1. Thesis drift

- Are we still optimizing a liquid-futures, demo-first research lab?
- Is the current work still about repeatable edges, or has it become "agentic" for its own sake?
- Does the newest evidence still support the current market mix and strategy bias?

If the answer is unclear, freeze promotion and re-state the thesis in one sentence.

### 2. Guardrail drift

- Did anything loosen `minRr`, `maxContracts`, `maxTradesPerDay`, `maxHoldMinutes`, or the flat cutoff?
- Did any new code path bypass the hard guardrails?
- Did a change introduce a live path, remote runtime, or unreviewed execution seam?

If yes, stop and restore the boundary before any further iteration.

### 3. Market universe drift

- Are the allowed symbols still the ones we can defend with liquidity and Topstep compatibility?
- Did a new symbol get added without a clear reason?
- Did we silently expand from one market family into many?

If yes, separate the new universe into its own research profile and measure it independently.

### 4. Source quality drift

- Are we still using primary or credible sources for claims that affect the lab?
- Did any blog, social post, or anecdote start carrying the weight of a rule?
- Can we point to a source for the claim, or is it just a story we like?

If a claim matters to guardrails, market selection, or execution, treat it as unproven until sourced.

### 5. Repo shape drift

- Is trunk still stable and easy to explain?
- Are the changes still one idea per lane?
- Did research, execution, and docs start mixing together?
- Can a new engineer still tell what the lab does in 60 seconds?

If not, simplify before adding more capability.

## Cadence

- Daily: run this checklist mentally before the first substantial change.
- Weekly: run `npm run context-drift` and review the output with `npm run verify`.
- After any universe or guardrail change: re-check the checklist before merge.
- Before any promotion: the checklist must be green and explainable in plain language.

## Stop-The-Line Signals

- a strategy wins only on one symbol or one regime
- a source changes the thesis more than the data does
- a guardrail is widened to rescue a weak idea
- the repo starts accumulating "temporary" exceptions
- a new agentic tool is added without a clear research job

## Reset Rule

If drift is detected, do not keep optimizing around it.

Freeze the lane, restate the thesis, re-run verification, and only then continue.
