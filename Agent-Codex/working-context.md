# Working Context

- Mode: research-only, execution locked unless daily plan + deterministic gates remain green at action time
- Safety flags: BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false BILL_TOPSTEP_BROKER_TOUCH_PAUSED=true
- TopstepX polling: **paused 2026-07-06** — realtime-bridge launchd Disabled=true; shadow-six-markets no longer runs bar archive; session-safety engaged via `npm run bill:pause-topstep-polling`
- SearXNG: live at http://127.0.0.1:8888; research_collector + premarketBrief use env-driven SearXNG with Firecrawl fallback
- Primary blockers: futures-demo-not-cleared, prediction-paper-not-cleared, source-hygiene-not-cleared
- Storage blocker: Seagate absent at /Volumes/Seagate Expansion Drive (forward CLOB capture requires storage preflight)
- Next actions:
  - Operator clears TopstepX "multiple sessions" in browser, then `BILL_OPERATOR_CONFIRM_TOPSTEP_CLEARED=true npm run bill:resume-topstep-polling` if read-only proofs needed
  - Run read-only evidence commands for futures data depth/parity and prediction forward capture preflight
  - Execute one-variable AI Scientist queue (3 runs) and keep outputs research-only
  - Clear source hygiene backlog items before any demo-expansion discussion
