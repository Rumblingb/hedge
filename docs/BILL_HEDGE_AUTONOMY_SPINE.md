# Bill/Hedge Autonomy Spine

Bill/Hedge v1 autonomy is paper-only by design. It can research, distill forked repositories, turn transcript/repo insight into strategy hypotheses, run strategy-factory gates, and stage paper candidates only after promotion evidence is ready. Live routing stays disabled until explicit founder approval changes the environment.

## Runtime Commands

- `npm run bill:fork-intake` distills the fork manifest into compact repo cards under `.rumbling-hedge/research/forks/`.
- `npm run bill:strategy-factory` runs walk-forward, rolling OOS, live-readiness stress, research-feed, and paper-only gate checks.
- `npm run bill:quant-autonomy` runs the machine-first quant loop and only executes stale fork/research/strategy tasks unless `--force` is passed.
- `npm run bill:autonomy-status` writes `.rumbling-hedge/state/autonomy-status.latest.json`.
- `npm run bill:dashboard` refreshes autonomy status and the OpenJarvis founder board.

## Operating Rules

- Keep `BILL_MAX_HEAVY_JOBS=1` on the 16GB Mac Mini.
- Keep `BILL_PREDICTION_LIVE_EXECUTION_ENABLED=false` and `BILL_ENABLE_FUTURES_DEMO_EXECUTION=false` for v1 autonomy.
- Do not clone or vendor forked repos into the hot runtime. Use fork intake cards as the ingestion boundary.
- Keep `.rumbling-hedge/`, logs, journals, snapshots, and large CSV/corpus data out of Git.
- Put compact red-folder/news events at `BILL_RED_FOLDER_EVENTS_PATH`; strategy lab uses them as blackout/risk context, not standalone alpha.
- Put trader/founder notes in `BILL_TRADER_INTUITION_PATHS`; intuition can bias research focus but cannot bypass OOS/paper gates.
- Use the HDD only after it is writable; keep hot normalized files, runtime state, and launchd logs on SSD.

## Promotion Logic

Strategy candidates remain blocked unless all of these pass:

- walk-forward report is deployable,
- rolling OOS evaluates at least four windows,
- every required OOS window is deployable,
- every supported strategy family has at least one research profile,
- in-sample and OOS datasets meet the minimum bar count,
- stressed live-readiness remains deployable,
- a fresh research strategy feed supports the lane,
- live execution flags remain off.

## Machine-First Quant Loop

`bill:quant-autonomy` holds the shared heavy-job slot, checks artifact freshness, and lets the Mac Mini do the expensive work locally:

- Fork intake defaults stale after 7 days.
- Researcher defaults stale after 3 hours.
- Strategy lab defaults stale after 8 hours.
- Paper/demo sampling is off by default; enable with `BILL_QUANT_AUTONOMY_RUN_PAPER_LOOP=true` only after paper gates are ready.
- Dashboard/status refresh after machine work.

Use `npm run bill:quant-autonomy -- --dry-run` to see due tasks without executing them, or `npm run bill:quant-autonomy -- --force` to run the quant loop immediately.
