# Mac Mini Local Brain

This machine should behave like one system with one founder-facing brain, not like a pile of unrelated bots.

## Control shape

- `OpenJarvis` is the only founder-facing ingress.
- Founder communication should stay on `Telegram` for now.
- `Discord` is the right place for agent-to-agent and team-room style coordination, not for adding another founder ingress.
- `Hermes` owns orchestration, freshness checks, bounded parallelism, and runtime correction.
- `Bill` owns markets, execution posture, and track prioritization.
- `Agency OS` owns company execution for the AgentPay team.
- `Researcher` owns ingestion, corpus building, and source enrichment.
- `OpenClaw` is the fixer lane Hermes can call for bounded implementation work.
- External heavyweight CLIs stay as escalation tools, not the default brain.

## Local-first runtime

For a base Mac Mini M4 with 16 GB RAM, the practical posture is:

- Keep Ollama local and always on.
- Keep `nomic-embed-text` as the default embedder.
- Keep `qwen2.5-coder:14b` as the currently-working heavy specialist for coding, review, and longer local passes.
- Keep `qwen3:8b` or similar as the lower-latency always-on orchestrator and routing model.
- Treat Gemma 3 4B as a secondary fallback for lighter general chat if you want another small local option.
- Do not make Gemma 4 13B or 27B the default on this box. They are a worse fit for a 16 GB always-on agent machine than a strong 8B Qwen routing model.
- Keep OpenJarvis free and local-first. Paid API spend belongs to the working agents only after the control plane is stable.

## Escalation rule

Local-first does not mean local-only. Use the local brain by default, and escalate only when one of these is true:

- the diff is large enough that local latency is slowing the whole machine down,
- the task needs stronger long-form coding or review than the local specialist can do cleanly,
- the system is blocked on a bug or architectural step that benefits from a second opinion.

That is when `Codex CLI`, `Claude CLI`, or `Gemini CLI` should be called in as specialists.

## Bill iteration order

Current order of work:

1. `prediction`: stay in collection and review mode until the top pair is structurally comparable and stakeable.
2. `futures-core`: keep demo lanes shadowing and compare lane outcomes before promotion.
3. `agency-os`: keep the AgentPay operating lanes shipping concrete packets and execution artifacts.
4. `researcher`: keep feeding the corpus and source catalog so the machine gets better context, not just more chatter.
5. `options-us`: treat as setup debt until the data path is real.
6. `crypto-liquid` and `macro-rates`: keep collecting context for training and regime labels.

## Bounded parallelism

- Hermes should cap simultaneous worker agents instead of running every lane at once.
- Keep Bill and Agency OS on every rotation.
- Rotate Researcher and OpenClaw through the remaining capacity.
- Default posture on this Mac Mini: 3 parallel workers max.

## Mission Control guidance

Mission Control is a visibility layer, not a second brain.

Use it to expose:

- task board,
- scheduled tasks / cron visibility,
- project board,
- memory viewer,
- docs viewer,
- team map,
- office / live-activity view.

Do not let the dashboard become the architecture. The architecture is still OpenJarvis -> Hermes -> Bill / Agency OS / Researcher / OpenClaw.
