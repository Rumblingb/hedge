# Bill launchd Templates

These templates are the first macOS-native control layer for Bill.

## Intended jobs

- `com.agentpay.bill.health` - recurring structured health snapshots
- `com.agentpay.bill.paper-loop` - recurring demo/paper loop execution
- `com.agentpay.bill.prediction-cycle` - recurring locked collect -> scan -> report execution
- `com.agentpay.bill.research-collect` - recurring research catalog collection

## Notes

- The wrappers source secrets from `~/Library/Application Support/AgentPay/bill/bill.env`, not from plist environment variables.
- Keep Bill jobs separate from Agency OS jobs.
- `com.agentpay.bill.paper-loop` is safe to load early because it exits unless `BILL_ENABLE_PAPER_LOOP=true`.
- `com.agentpay.bill.prediction-cycle` is the scheduler of truth. It runs every 5 minutes, acquires a lock, and performs collect -> scan -> report as one Bill iteration.
- `com.agentpay.bill.research-collect` runs every 30 minutes and refreshes the Bill research catalog without touching live execution.
- the prediction-report scheduled wrapper also writes a dated native summary into Bill workspace memory
- Keep first live execution approval-gated. These templates do not change that policy.
