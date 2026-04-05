# Worktree Plan

## Why Worktrees

Worktrees let us keep one stable repo root while running separate lanes in parallel.

That matters here because we want:

- one lane for research
- one lane for implementation
- one lane for verification
- one lane for docs and operating model updates

## Branch Lanes

Recommended lane structure:

- `main`
  - stable trunk only
- `research/*`
  - data, profiling, walk-forward work
- `feature/*`
  - strategy or engine changes
- `ops/*`
  - scripts, CI, runbooks, verification tooling
- `docs/*`
  - operating model and memo updates

## Worktree Pattern

Use one worktree per lane:

- `rumbling-hedge`
  - trunk and final merges
- `rumbling-hedge-research`
  - experiments and market studies
- `rumbling-hedge-feature`
  - strategy and engine implementation
- `rumbling-hedge-ops`
  - scripts and verification helpers

## What Goes Where

- Research lane:
  - market data inspection
  - WCTC pattern analysis
  - walk-forward ranking
  - cost and regime testing
- Feature lane:
  - new strategy modules
  - sizing logic
  - execution-aware backtest changes
  - news gating improvements
- Ops lane:
  - verification scripts
  - worktree helpers
  - run commands
  - environment templates
- Docs lane:
  - operating model
  - risk notes
  - research memos
  - decision logs

## Promotion Rule

A lane can merge back only when:

1. It is scoped to one idea.
2. It passes local verification.
3. Its output is understandable in plain language.
4. It does not weaken any guardrail.
5. It has a clear reason to exist after the merge.

## Verification Checklist

Before merging anything from a worktree:

- typecheck passes
- tests pass
- research runner passes on the current sample set
- sim output is reviewed
- the change is still defensible after a quick red-team read

## How I Will Use It

I will treat the repo like a small trading desk:

- keep the trunk calm
- let worktrees absorb parallel exploration
- keep research separate from implementation
- only promote changes that improve demo survivability

That gives us speed without letting the project get noisy or self-contradictory.
