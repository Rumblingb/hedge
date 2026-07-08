# Working Context

- Mode: research-only, execution locked unless daily plan + deterministic gates remain green at action time
- Safety flags: BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false BILL_TOPSTEP_BROKER_TOUCH_PAUSED=true
- TopstepX polling: **paused 2026-07-06** — realtime-bridge launchd Disabled=true; session-safety engaged via `npm run bill:pause-topstep-polling`
- SearXNG: live at http://127.0.0.1:8888; command center http://127.0.0.1:8766 (health 200)
- Primary blockers: futures-demo-not-cleared, prediction-paper-not-cleared, source-hygiene-not-cleared
- Storage: Seagate mounted at `/Volumes/Seagate Expansion Drive` (~87 GiB free); SSD headroom improved post-sprint
- External-alpha audit: **PASS** (2026-07-07) — merged-export local parity 5102 rows; `npm run bill:sync-seagate-nq-local-parity`
- PM CLOB capture 2026-07-06: 4237 messages on Seagate; displacement scanner sketch wired (`bill:prediction-five-min-displacement-scanner`)
- AI Scientist Seagate runs (2026-07-07): 5m ORB reject PF=0.34; 60m news-reversion 0 OOS trades — research-only
- Best futures research candidate: `nq-orb-3m-vt16` (NY session); not demo-cleared
- Obsidian: [[cofounder-execution-2026-07-07]], [[BILL-COMPOUND-LADDER-2026-07-07]]
- Re-enable broker read-only only after operator clears TopstepX browser session → `BILL_OPERATOR_CONFIRM_TOPSTEP_CLEARED=true npm run bill:resume-topstep-polling`
