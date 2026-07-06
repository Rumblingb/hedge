# Working Context

- Mode: research-only, execution locked unless daily plan + deterministic gates remain green at action time
- Safety flags: BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false
- SearXNG: live at http://127.0.0.1:8888; hardened env-driven fallback behavior across research collectors
- Primary blockers: futures-demo-not-cleared, prediction-paper-not-cleared, source-hygiene-not-cleared
- Storage blocker: Seagate absent at /Volumes/Seagate Expansion Drive (forward CLOB capture requires storage preflight)
- Next actions:
  - Run read-only evidence commands for futures data depth/parity and prediction forward capture preflight
  - Execute one-variable AI Scientist queue (3 runs) and keep outputs research-only
  - Clear source hygiene backlog items before any demo-expansion discussion
