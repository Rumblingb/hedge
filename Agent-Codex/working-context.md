# Working Context

- Mode: research-only, execution locked unless daily plan + deterministic gates remain green at action time
- Safety flags: BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false BILL_TOPSTEP_BROKER_TOUCH_PAUSED=true
- TopstepX polling: **paused 2026-07-06** — realtime-bridge launchd Disabled=true; shadow-six-markets no longer runs bar archive; session-safety engaged via `npm run bill:pause-topstep-polling`
- SearXNG: live at http://127.0.0.1:8888; research_collector + premarketBrief use env-driven SearXNG with Firecrawl fallback
- Primary blockers: futures-demo-not-cleared, prediction-paper-not-cleared, source-hygiene-not-cleared
- Storage: Seagate **mounted** at `/Volumes/Seagate Expansion Drive` (~87GB free); SSD ~18GB free — CLOB capture unblocked
- Offline research wins (2026-07-06): CFTC TFF refreshed (2026-06-23); Yahoo futures CSV refresh PASS; Seagate NQ parity OK; vol-regime 15m OOS still reject (PF 0.57); PM CLOB 120s smoke OK
- Next actions (zero Topstep):
  - `npm run bill:external-alpha-data-audit` → Seagate NQ session-structure OOS
  - AI Scientist one-variable queue (wq_vol_regime / orb+HA / news-reversion)
  - Standing CLOB capture to Seagate during macro/geo headlines
  - `npm run bill:source-packet-review` + goal-completion-audit
- Re-enable broker read-only only after operator clears TopstepX browser session → `BILL_OPERATOR_CONFIRM_TOPSTEP_CLEARED=true npm run bill:resume-topstep-polling`
