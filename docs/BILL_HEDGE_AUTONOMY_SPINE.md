# Bill/Hedge Autonomy Spine

Bill/Hedge v1 autonomy is paper-only by design. It can research, distill forked repositories, turn transcript/repo insight into strategy hypotheses, run strategy-factory gates, and stage paper candidates only after promotion evidence is ready. Live routing stays disabled until explicit founder approval changes the environment.

## Runtime Commands

- `npm run bill:fork-intake` distills the fork manifest into compact repo cards under `.rumbling-hedge/research/forks/`.
- `npm run bill:strategy-factory` runs walk-forward, rolling OOS, live-readiness stress, research-feed, and paper-only gate checks.
- `npm run bill:autonomy-status` writes `.rumbling-hedge/state/autonomy-status.latest.json`.
- `npm run bill:dashboard` refreshes autonomy status and the OpenJarvis founder board.

## Operating Rules

- Keep `BILL_MAX_HEAVY_JOBS=1` on the 16GB Mac Mini.
- Keep `BILL_PREDICTION_LIVE_EXECUTION_ENABLED=false` and `BILL_ENABLE_FUTURES_DEMO_EXECUTION=false` for v1 autonomy.
- Do not clone or vendor forked repos into the hot runtime. Use fork intake cards as the ingestion boundary.
- Keep `.rumbling-hedge/`, logs, journals, snapshots, and large CSV/corpus data out of Git.
- Use the HDD only after it is writable; keep hot normalized files, runtime state, and launchd logs on SSD.

## Promotion Logic

Strategy candidates remain blocked unless all of these pass:

- walk-forward report is deployable,
- rolling OOS evaluates at least four windows,
- every required OOS window is deployable,
- stressed live-readiness remains deployable,
- a fresh research strategy feed supports the lane,
- live execution flags remain off.

