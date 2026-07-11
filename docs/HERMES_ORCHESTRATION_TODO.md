# Hermes Orchestration TODO

This is the concrete stabilization and autonomy backlog for the Mac Mini control plane.

## Locked architecture

- OpenJarvis is the only founder-facing ingress.
- Hermes is the orchestrator and runtime supervisor.
- Bill owns market execution and market research lanes.
- Agency OS owns AgentPay team execution.
- Researcher owns ingestion and memory enrichment.
- OpenClaw is the bounded fixer lane Hermes can call for implementation tasks.
- OpenJarvis stays free and local-first.

## Active now

1. Make Hermes the real task supervisor, not just the status narrator.
   - Persist a structured task queue with `active`, `queued`, `paused`, `needs-approval`, and `done`.
   - Store worker heartbeats and founder control state as structured artifacts.
   - Let Hermes choose which workers run each cycle under bounded parallelism.

2. Keep bounded parallelism on the Mac Mini.
   - Default to 3 worker slots.
   - Pin Bill and Agency OS into every rotation.
   - Rotate Researcher and OpenClaw through spare capacity.
   - Keep heavy paid models off until the queue and guardrails are trustworthy.

3. Keep OpenJarvis free.
   - Use local routing and summarization first.
   - Route browser/web tasks through tooling rather than paid chat by default.
   - Only let worker agents consume paid APIs when Hermes decides a task actually needs them.

## Bill fine tuning

1. Fix `bill:live-readiness`.
   - Default it to the current normalized dataset instead of requiring a manual csv path.
   - Make Hermes able to call it safely as a health primitive.

2. Prediction lane: resolve the policy mismatch.
   - Align `scanPolicy` and committee logic so high-edge thin-size candidates can enter a bounded micro-paper review state.
   - Keep explicit approval on any widening from watch to paper.
   - Add a counterfactual summary artifact Hermes can read directly.

3. Futures lane: harden data and evidence.
   - Add symbol-specific fallback and degraded-symbol handling for CL/GC failures.
   - Separate “dataset degraded” from “lane blocked” in artifacts.
   - Tighten OOS evidence thresholds and stabilize ranking before widening strategies.
   - Keep demo routing fail-closed until evidence is good enough.

4. Researcher lane: improve yield.
   - Loosen filters or refresh targets until runs keep durable chunks again.
   - Bias targets toward static-friendly sources whenever Firecrawl or heavier crawling is unavailable.
   - Write retained-corpus quality summaries Hermes can reason over.

5. Options / crypto / macro lanes: make the board honest.
   - Keep options marked as setup debt until the collection path is fully validated.
   - Keep crypto and macro in collect-only mode until they produce stable, useful training context.
   - Stop implying execution readiness where only source cataloging exists.

6. Cleanup model config drift.
   - Remove dead review model ids from Hedge env and helper scripts.
   - Keep paid worker defaults in the Kimi / DeepSeek budget band.
   - Keep free models as the preflight default while the system is still stabilizing.

## Hermes backlog

1. Done: persist the Hermes queue artifact under `.rumbling-hedge/state/hermes-supervisor.json`.
2. Done: add approval and pause/resume control state plus CLI commands:
   - `npm run hermes-supervisor-status`
   - `npm run hermes-supervisor-approve -- <taskId> [note]`
   - `npm run hermes-supervisor-pause -- <taskId> [note]`
   - `npm run hermes-supervisor-resume -- <taskId> [note]`
   - `npm run hermes-supervisor-complete -- <taskId> [note]`
   - `npm run hermes-supervisor-why -- <taskId>`
3. Add a “safe retry” policy for failed loops.
4. Add phone-safe founder commands in OpenJarvis that map onto the supervisor controls.
5. Add web-grounded worker tasks so Hermes can delegate browser/search work like a low-cost Manus/Perplexity style flow.
6. Add cost accounting so Hermes can keep OpenJarvis free while spending only where workers need real compute.

## OpenClaw work Hermes should be able to assign

1. Fix broken wrappers and launchd scripts.
2. Patch Bill fine-tuning logic with bounded diffs.
3. Repair researcher filters and target files.
4. Update docs and structured manifests when ownership changes.

## Success condition

- OpenJarvis remains one free founder ingress.
- Hermes decides what runs.
- Bill and Agency OS always have active work.
- Researcher and OpenClaw rotate without overwhelming the box.
- The machine fails closed when stale or degraded.
- Paid API spend only turns on when the control plane is stable enough to deserve it.
