# Risk Guardrails

These are the non-negotiable rails in v0.1:

- Allowed symbols must be on the Topstep-permitted list encoded in code
- New entries allowed only between `08:30 CT` and `11:30 CT`
- All positions must be flat by `15:10 CT`
- Minimum RR must be at least `2.5`
- Maximum contracts per trade must be `2`
- Maximum trades per day must be `3`
- Maximum hold time must be `30 minutes`
- Maximum daily realized drawdown must be `-2R`
- Maximum consecutive losses must be `2`
- High-impact news can veto a setup if confidence is below threshold or direction disagrees

## Evolution rules

Evolution proposals must stay inside these hard bounds and are allowed only to tighten or disable behavior.

Approved proposal types:

- raise `minRr`
- lower `maxTradesPerDay`
- lower `maxHoldMinutes`
- raise `newsProbabilityThreshold`
- disable a weak strategy

Rejected proposal types:

- increase contracts
- widen time windows
- relax drawdown limits
- bypass the news gate
- apply changes without review
