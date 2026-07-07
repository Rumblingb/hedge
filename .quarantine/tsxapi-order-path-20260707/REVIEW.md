# Quarantined: tsxapipy order-execution path (2026-07-07)

Files: `tsxapi_order_bridge.py` (order place/cancel/status via tsxapipy OrderPlacer),
`tsxapiAdapter.ts` (TS ExecutionAdapter calling the bridge as a subprocess).

Why quarantined (Claude cofounder review):
1. This is a NEW order-execution path that appeared uncommitted in the worktree —
   execution-lane code must enter through the guarded-lane review (firewall
   verification + operator approval), not a working-tree drop.
2. Its sibling change (`fetch_tsxapi_v2` in realtime_data_bridge.py) opens its own
   auth session instead of the shared topstep_auth_cache — the same pattern that
   trips Topstep multiple-session warnings. Session safety was re-paused 2026-07-06.
   The v2 hop is now gated behind `BILL_TSXAPI_V2_ENABLED=true` (default off).

Path out of quarantine:
- Rework both to reuse the shared machine-wide token cache (one login per ~20h).
- Run `npm run bill:verify-execution-quarantine` + demo-bridge firewall verification.
- Operator approval per daily-plan token flow before any wiring into demoExecution.
