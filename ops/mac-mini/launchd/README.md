# Bill launchd Templates

These templates are the first macOS-native control layer for Bill.

## Intended jobs

- `com.agentpay.bill.health` - recurring structured health snapshots
- `com.agentpay.bill.paper-loop` - recurring demo/paper loop execution
- `com.agentpay.bill.prediction-scan` - recurring snapshot-driven prediction scan
- `com.agentpay.bill.prediction-report` - recurring prediction journal summary

## Notes

- The wrappers source secrets from `~/Library/Application Support/AgentPay/bill/bill.env`, not from plist environment variables.
- Keep Bill jobs separate from Agency OS jobs.
- `com.agentpay.bill.paper-loop` is safe to load early because it exits unless `BILL_ENABLE_PAPER_LOOP=true`.
- `com.agentpay.bill.prediction-scan` is safe to load early because it exits unless the feature flag is on and the snapshot path exists.
- Keep first live execution approval-gated. These templates do not change that policy.
