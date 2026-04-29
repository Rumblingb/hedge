# OpenJarvis Control Plane

OpenJarvis is the single founder-facing ingress for the machine.

## Locked architecture

These invariants are locked unless the founder explicitly approves a change:

- `open-jarvis` is the only founder-facing ingress.
- `hermes` is the control plane, orchestrator, and runtime supervisor.
- `hedge` is Bill's market runtime.
- `agency-os` is the company runtime for AgentPay, ACE, and RCM execution.
- `openclaw` is the bounded fixer/implementation lane Hermes can call when the machine needs changes.
- `researcher` is the ingestion and knowledge-enrichment lane.
- Specialist lanes do not become new public founder interfaces just because they exist.

## Routing rule

OpenJarvis accepts the founder request, classifies it, and routes ownership:

- markets, demo execution, prediction, futures, options, crypto -> `bill`
- product, growth, sales, marketing, launch work -> `agency-os`
- architecture drift, runtime drift, trust boundary, ops fixes, stale loops, orchestration decisions -> `hermes`
- content ingestion, crawling, evals, corpus work -> `researcher`

Hermes then decides whether to:

- run the action directly,
- assign it to Bill / Agency OS / Researcher,
- or hand a bounded fix task to `openclaw`.

## Command surfaces

- `npm run openjarvis`
- `npm run openjarvis-status`
- `npm run bill:openjarvis`

The default `openjarvis` wrapper prints the merged founder-facing board:

- Bill opportunity posture
- Agency OS operating state
- runtime health and stale-state warnings
- founder next action
- routing owner
- whether approval is needed

The founder-facing board must stay freshness-aware:

- stale or missing scheduled artifacts should degrade the reported posture instead of being treated as current,
- `bill-health.latest.json` and recent cycle failures should feed Hermes/control-plane routing,
- founder attention should prefer “stabilize the machine” over “keep executing” when the loops themselves are degraded.

## Worker policy

- OpenJarvis should stay free and local-first.
- Hermes should run only a bounded number of worker agents in parallel.
- Bill and Agency OS should keep making progress every cycle.
- Researcher and OpenClaw should rotate through spare capacity instead of all lanes running simultaneously.
- Paid models belong to the working agents, not the founder ingress.

## Anti-drift rule

No other LLM should:

- rename the founder ingress away from OpenJarvis
- move market logic out of `hedge`
- move company runtime out of `agency-os`
- turn specialists into parallel founder-facing bots
- weaken guardrails to make the system feel more active
