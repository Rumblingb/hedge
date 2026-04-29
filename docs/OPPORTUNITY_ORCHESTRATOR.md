# Opportunity Orchestrator

The Opportunity Orchestrator now produces a multi-track, actionable board that aligns prediction markets, copy-demo, futures demo lanes, options research, and the researcher corpus pipeline in one JSON response.

It reads the scheduled-state artifacts under `.rumbling-hedge/state`, the research catalog under `.rumbling-hedge/research`, and the researcher outbox under `.rumbling-hedge/research/researcher`, then composes a structured snapshot:

- Prediction posture, candidate counts, recommendation, and blockers from `prediction-review.latest.json`. The report also surfaces the current watch/paper/promotion status and recurring-candidate history so the quant/CEO can see whether to keep waiting or act.
- Copy-demo leader status, actionable vs watch-only idea counts, and founder-approved constraint failures from `prediction-copy-demo.latest.json`.
- Futures demo sampling state, lane strategy mapping, and nightly samples from `futures-demo.latest.json` plus `.rumbling-hedge/logs/futures-demo-samples.jsonl`.
- Researcher run metadata, quality scores, and ingestion stats from `latest-run.json` plus the live corpus/embedding artifacts.
- Options/crypto/macro research cues (artifact freshness, tracked symbols, setup debt, and attention flags) aggregated from the opportunity conductor so you can see what is collecting cleanly and what still needs wiring.

The resulting board highlights for each track whether it is `actionable`, `shadow`, `collecting`, `setup-debt`, or `idle`, explains the dominant blockers, and surfaces the highest-priority next action across the machine. Run it via `npm run bill:opportunity-snapshot` (or `tsx src/cli.ts opportunity-snapshot`). The CLI prints a JSON object plus an `attention` list that flags the most important gaps or newly eligible tracks.

The board is now freshness-aware rather than artifact-presence-aware:

- prediction, copy-demo, futures, and researcher summaries carry freshness metadata,
- stale futures datasets or stale review artifacts degrade the reported posture instead of masquerading as live readiness,
- Bill runtime warnings from `bill-health.latest.json` are folded into the board so observability is part of orchestration.

The orchestrator is read-only: it never mutates the prediction cycle or execution paths. Treat it as the automation-ready summary that Hermes reads before deciding what Bill, Agency OS, Researcher, or OpenClaw should do next.
