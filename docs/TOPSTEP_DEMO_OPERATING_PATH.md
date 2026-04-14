# Topstep Demo Operating Path

This lane is demo-first.

## Current posture

- market focus: `NQ` rehab, with `ES` kept as comparison truth for the index family
- research focus: `ict-killzone-core` and `trend-only` comparison, not blind NQ commitment
- strategy set: `ict-displacement`, `session-momentum`, with research-only standing as a valid outcome
- account path: Topstep practice / demo first
- live posture: keep `demo-only` and `read-only` until shadow behavior is reviewed
- escalation rule: no broader live path until real payouts exist

## Multi-account demo split

If you have four or more Topstep demo accounts, Bill should treat them as parallel test lanes, not one pooled bucket.

- configure all ids in `RH_TOPSTEP_ALLOWED_ACCOUNT_IDS`
- configure matching labels in `RH_TOPSTEP_ALLOWED_ACCOUNT_LABELS`
- keep `RH_TOPSTEP_ACCOUNT_ID` empty unless you want to pin one specific account
- keep `RH_TOPSTEP_READ_ONLY=true` until the ProjectX/Topstep execution client is fully reviewed

Bill will then map one primary strategy lane per account in the doctor, dashboard, and demo-tomorrow outputs:

- account 1 -> `opening-range-reversal`
- account 2 -> `session-momentum`
- account 3 -> `liquidity-reversion`
- account 4 -> `ict-displacement`
- any additional accounts -> repeat the strongest benchmark lanes so comparisons stay account-aware instead of pooled

## What tomorrow means

Tomorrow is a controlled Topstep demo session, not a shortcut to live routing.

Use the session to:

- validate whether the NQ rehab lane is improving, not whether it can be forced live
- capture every candidate, rejection, and regime read
- confirm guardrail behavior under live market pacing
- collect material for the next daily research pass
- keep futures as an equal-first execution wedge next to prediction, even while the adapter remains read-only

If the promotion gate is still failing, the correct behavior is shadow-only or stand-down, not discretionary forcing.

## Operating sequence

### 1) Demo

Goal:
- run shadow-only rehab sessions on the selected index profile and preserve every blocker, rejection, and regime read

Requirements:
- data-quality pass
- risk rails intact
- full session journal captured
- review of rejected signals and regime classification

### 2) Challenge

Goal:
- use only profiles that have cleared the promotion gate and then trade the prop challenge conservatively

Requirements:
- `promotionGate.ready`
- consecutive green challenge reports
- stable walk-forward behavior, not one lucky window

### 3) Funded

Goal:
- preserve consistency and payout survivability under tighter limits

Requirements:
- switch to funded-default tighter posture
- protect drawdown first
- no expansion of complexity unless funded evidence stays stable

### 4) Payout

Goal:
- prove the system can actually extract payouts, not just pass an evaluation

Requirements:
- real payout receipts
- continued stability after costs and under funded constraints
- daily review loop still intact

### 5) Only then live

Goal:
- consider any fuller live path only after payout proof exists

Requirements:
- explicit approval
- documented payout track record
- reviewed execution path with demo-only account lock principles preserved until intentionally changed

## Rajiv blockers only if still missing

These are the only items that truly need founder input for tomorrow's lane:

- the four exact Topstep practice account ids to lock with `RH_TOPSTEP_ALLOWED_ACCOUNT_IDS`
- approval if and when `read-only` should ever be lifted later, after shadow review
- any change to the conservative demo-first progression above

Everything else should stay inside hedge and be learned through the daily loop.
