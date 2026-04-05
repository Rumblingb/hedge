# Founder Inputs

Rumbling Hedge is set up so the CTO lane can keep iterating with very little founder overhead.

## What I Need From You

Only send these if you want to override the defaults:

- account path
  - default: Topstep Practice / demo only
- allowed market universe
  - default: `NQ`, `ES`, `CL`, `GC`, `6E`
- demo risk budget
  - default: `1%` per trade cap, `2R` daily stop, `max 3` trades per day
- promotion threshold
  - default: do not promote a profile unless it stays positive after costs, keeps drawdown contained, and behaves consistently across walk-forward splits
- hard no-go windows or instruments
  - default: no overnight holds, no prohibited session windows, no unsupported or illiquid contracts
- research bias
  - default: index-led session momentum first, then selective cross-asset expansion

## What I Will Assume If You Stay Hands-Off

- We stay demo-first.
- We optimize for survivability and repeatability, not headline returns.
- We treat agents as research and review infrastructure, not autonomous risk owners.
- We only widen scope after evidence improves.

## What I Will Keep Doing

- run research, build, and verification in separate worktree lanes
- keep the trunk stable
- verify every promotion with typecheck, tests, research, and sim
- tighten guardrails when evidence says a strategy is noisy
- report back when something is materially better, materially worse, or needs a founder decision

## When I Actually Need You

- when you want to change the market universe
- when you want to relax or tighten risk appetite
- when a profile is strong enough to justify moving from demo research toward a live-capable paper routing path
- when policy or platform constraints change

## Recheck Triggers

Pause promotion and run the context drift checklist if:

- the market universe changes
- guardrails change
- a new source changes the thesis
- a research profile starts winning for the wrong reasons
- the repo gets harder to explain in one minute
