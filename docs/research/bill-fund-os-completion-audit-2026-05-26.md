# Bill Fund OS Completion Audit — 2026-05-26

Overall status: `NOT_COMPLETE`
Trading readiness status: `BLOCKED_BY_EVIDENCE`

This maps the founder request to concrete artifacts and gates. Handoff completion does not authorize trading; trading stays blocked whenever live-readiness gates are red.

## Completion Criteria

- Relevant repo, Hermes, Obsidian, Downloads, and Seagate roots are inventoried.
- Canonical research and handoff docs exist.
- A current clearance handoff exists for weaker agents and keeps execution locked.
- Current governance/firewall evidence is recorded by a non-executing verifier.
- Proxy/research signals are shadow-only unless explicitly promoted.
- Execution paths default to guarded/canonical routes and cannot use stale legacy state by accident.
- n8n/Hermes scheduler state is inspected and documented.
- Fresh data checks and contrary OOS evidence are recorded.
- Execution-grade realtime data is explicitly preflighted before demo/live use.
- Databento live quote smoke is recorded separately from canonical realtime quote state.
- Prediction-market funding helpers are fail-closed unless explicitly approved.
- Prediction-market fillability snapshots are public-data, read-only, and non-tradable.
- Futures and prediction no-edge ledgers prevent retesting stale ideas as if they were new alpha.
- Fresh CFTC TFF positioning is available only as a weekly research/regime feature.
- LLM research loops are separated from deterministic execution routes.
- Dirty source/worktree state is visible before live-money clearance.
- Hermes runtime storage pressure is manifest-only audited before cleanup.
- The futures/prediction/copy-trading/brokerage/options expansion ladder is explicit and execution-locked.
- Trading expansion remains blocked when gates fail.

## Prompt-To-Artifact Checklist

| Requirement | Status | Evidence | Action |
|---|---:|---|---|
| Canonical Phase 2 fund OS document exists | `PASS` | `/Users/brain/hedge/docs/BILL_FUND_OS_PHASE2_2026_05_26.md` |  |
| Research handoff README exists for weaker agents | `PASS` | `/Users/brain/hedge/docs/research/README.md` |  |
| Corpus inventory exists | `PASS` | `/Users/brain/hedge/docs/research/bill-corpus-audit-2026-05-26.md` |  |
| Corpus JSON exists for machine use | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/bill-corpus-audit.latest.json` |  |
| Obsidian pointer exists | `PASS` | `/Users/brain/Documents/memorybrain/Agent-Hermes/bill-fund-os-phase2-2026-05-26.md` |  |
| Current clearance handoff exists and keeps execution locked | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/bill-clearance-handoff.latest.json decision=KEEP_EXECUTION_LOCKED readyForExecution=False` |  |
| Current clearance evidence exists and is non-executing | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/bill-clearance-evidence.latest.json status=PASS allCommandsPassed=True failed=[]` |  |
| Corpus covers repo, Hermes, Obsidian, Downloads, and Seagate roots | `PASS` | `present=['downloads', 'hermes_cron', 'hermes_scripts', 'obsidian_hermes', 'obsidian_shared', 'obsidian_trading', 'repo_docs', 'repo_research', 'repo_scripts', 'repo_src', 'repo_state', 'seagate_alpha_manifests', 'seagate_features', 'seagate_local_archives', 'seagate_rumbling', 'seagate_rumbling_cold_archives', 'seagate_rumbling_cold_strategy']` |  |
| dom-proxy-signal.latest.json cannot affect execution unless promoted | `BLOCKED` | `/Users/brain/hedge/.rumbling-hedge/state/dom-proxy-signal.latest.json promoted=None tradable=None evidence=None` | Re-run the generator after patching it to emit shadow-only execution fields. |
| kalman-pairs-signal.latest.json cannot affect execution unless promoted | `BLOCKED` | `/Users/brain/hedge/.rumbling-hedge/state/kalman-pairs-signal.latest.json promoted=None tradable=None evidence=None` | Re-run the generator after patching it to emit shadow-only execution fields. |
| whale-flow-signal.latest.json cannot affect execution unless promoted | `BLOCKED` | `/Users/brain/hedge/.rumbling-hedge/state/whale-flow-signal.latest.json promoted=None tradable=None evidence=None` | Re-run the generator after patching it to emit shadow-only execution fields. |
| Rolling optimizer is shadow-only and finite | `BLOCKED` | `/Users/brain/hedge/.rumbling-hedge/state/rolling-window-params.latest.json promoted=None` | Re-run rolling_window_optimizer.py after NaN guard patch. |
| 60m data is fresh enough for research evaluation | `BLOCKED` | `latest=2026-06-24T08:00:00.000Z age_minutes=5871.5384995 closed_market_bar_ok=False` | Refresh 60m research data before any research run. |
| 15m data is fresh enough for research evaluation | `BLOCKED` | `latest=2026-06-24T08:00:00.000Z age_minutes=5871.538502766666 closed_market_bar_ok=False` | Refresh 15m research data before ORB/DOM-proxy/15m research matters. |
| Realtime data preflight exists and is read-only | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/realtime-data-preflight.latest.json readyForExecutionData=False decision=block-execution-data blockers=['source=none is not marked execution-grade', 'data freshness gate is BLOCK', 'TopstepX realtime proof is visible, but canonical realtime quote state/freshness is not yet promoted']` |  |
| Realtime execution data remains blocked | `WARN` | `decision=block-execution-data blockers=['source=none is not marked execution-grade', 'data freshness gate is BLOCK', 'TopstepX realtime proof is visible, but canonical realtime quote state/freshness is not yet promoted']` | Do not route futures demo/live orders until realtime preflight is green from execution-grade data. |
| Databento realtime smoke artifact exists and is research-only | `BLOCKED` | `/Users/brain/hedge/.rumbling-hedge/state/databento-realtime-smoke.latest.json status=None readyForExecutionDataProof=None writesRealtimeQuoteState=None session=None` | Run npm run bill:databento-realtime-smoke and keep it separate from realtime-quote.latest.json. |
| Databento realtime bridge is explicit and default-off | `PASS` | `/Users/brain/hedge/scripts/realtime_data_bridge.py` |  |
| Prediction funding helpers fail closed unless explicitly approved | `PASS` | `scripts=5 verifier=/Users/brain/hedge/scripts/verify_prediction_funding_firewall.py` |  |
| Futures evidence triage artifact exists | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/futures-evidence-triage.latest.json decision=research-only; no futures strategy is currently demo-expandable` |  |
| Futures strategy lane remains research-only | `WARN` | `decision=research-only; no futures strategy is currently demo-expandable liveBlockers=['source tree has uncommitted source changes', 'Topstep monitor artifact is missing', 'Topstep session-safety artifact is missing', 'futures cost/slippage gate is not deployable: backtrader survivors=0 volOos survivors=0'] +3 more` | Do not promote full-sample survivors; require OOS, walk-forward, stress, cost/slippage, and live-readiness gates. |
| Prediction-market evidence triage artifact exists | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/prediction-evidence-triage.latest.json decision=research-only; no prediction-market candidate is paper-ready` |  |
| Prediction-market lane remains research-only | `WARN` | `decision=research-only; no prediction-market candidate is paper-ready clobStatus=missing watchCount=0 readyForPaper=False` | Keep prediction execution in paper/skipped mode until market-specific resolved-history and calibration gates pass. |
| Kalshi fillability snapshot is present and research-only | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/kalshi-fillability-snapshot.latest.json marketsInspected=375 executablePublicQuotes=58 bucketCounts={'too-wide': 53, 'wide': 43, 'usable': 26, 'no-two-sided-book': 221, 'tight': 32}` |  |
| Futures no-edge memory is present | `PASS` | `path=/Users/brain/hedge/.rumbling-hedge/research/futures-no-edge-ledger/latest.json count=13 noEdgeCount=10 needsNewFeatureCount=3 promotableCount=0` |  |
| Prediction no-edge memory is present | `PASS` | `path=/Users/brain/hedge/.rumbling-hedge/research/prediction-no-edge-ledger/latest.json count=14 noEdgeCount=10 needsMoreDataCount=4 promotableCount=0` |  |
| Research loop separates LLM research from deterministic execution | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/bill-research-closed-loop-contract.latest.json readyForExecution=False researchOnly=True deterministicCodeRoutes=True llmMayRoute=False` |  |
| CFTC TFF positioning intake is fresh and research-only | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/cftc-tff-positioning.latest.json freshForWeeklyResearch=True latestReportDate=2026-06-23 markets=['ES', 'NQ', 'ZN'] tradable=False` |  |
| Worktree consolidation artifact exists | `PASS` | `posture=organized-blocked-for-live-money sourceCleanBlockers=['canonical source root has 2 dirty files']` |  |
| Source tree remains too dirty for live-money clearance | `WARN` | `canonicalDirtyFiles=2 categories={'governance-risk': 0, 'strategy-research': 0, 'data': 0, 'execution-live': 0, 'external-vendor': 0, 'generated-cache': 0, 'ops-docs': 2, 'dependencies': 0, 'unknown': 0} blockers=['canonical source root has 2 dirty files']` | Finish, verify, and intentionally commit/stage bounded source changes before any live-money clearance. |
| Hermes runtime storage audit exists and is manifest-only | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/hermes-storage-audit.latest.json totalSize=18.5GB archiveCandidateSize=10.9GB movesFiles=False deletesFiles=False` |  |
| Hermes runtime has archive candidates but cleanup is not executed | `WARN` | `archiveCandidateSize=10.9GB topCandidates=[{'action': 'inspect-profile-subdirs-before-archive', 'bytes': 10533640971, 'exists': True, 'name': 'profiles', 'path': '/Users/brain/.hermes/profiles', 'reason': 'Large agent/model profile root; individual profiles may be active or cold.', 'size': '9.8GB', 'tier': 'warm-profile-cache'}, {'action': 'archive-old-files-only', 'bytes': 900143149, 'exists': True, 'name': 'sessions', 'path': '/Users/brain/.hermes/sessions', 'reason': 'Useful recent history; only rotate/archive old files after retention policy is chosen.', 'size': '858.4MB', 'tier': 'warm-rotating-history'}, {'action': 'archive-old-files-only', 'bytes': 300728410, 'exists': True, 'name': 'logs', 'path': '/Users/brain/.hermes/logs', 'reason': 'Useful recent history; only rotate/archive old files after retention policy is chosen.', 'size': '286.8MB', 'tier': 'warm-rotating-history'}, {'action': 'archive-old-files-only', 'bytes': 30708, 'exists': True, 'name': 'checkpoints', 'path': '/Users/brain/.hermes/checkpoints', 'reason': 'Useful recent history; only rotate/archive old files after retention policy is chosen.', 'size': '30.0KB', 'tier': 'warm-rotating-history'}] +1 more` | Only archive/delete after operator approval, inactive-profile review, and verified Seagate copy/checksum. |
| Master bridge reads canonical state and ignores unpromoted overlays | `PASS` | `/Users/brain/hedge/scripts/master_bridge.py` |  |
| Hermes master bridge delegates to canonical repo bridge | `PASS` | `/Users/brain/.hermes/scripts/master_bridge.py` |  |
| Legacy LucidFlex bridge defaults to shadow-only | `PASS` | `repo and Hermes 60m_exec_bridge.py` |  |
| Agentic fund cycle defaults to shadow-only and canonical state | `PASS` | `repo and Hermes agentic_fund.sh` |  |
| Hermes cron state is validator-cleared or prompts describe shadow/guarded execution posture | `BLOCKED` | `validatorCleared=False missing=['shadow', 'guarded topstep demo bridge', 'bill_enable_lucidflex_execution=true', 'bill_enable_agentic_fund_execution=true'] stale=[] enabledExecutionAdjacent=0` | Run npm run bill:cron-state-validator or update ~/.hermes/cron/jobs.json prompts so agents do not inherit stale execution language. |
| n8n has no hidden active Bill execution workflow | `PASS` | `workflows=[{'id': 'TamyClnUY16TpMy5', 'name': 'App Idea → Build → Launch → Advertise', 'active': 0}, {'id': '33D58D54-EE64-441E-9D9D-8F5CB8765F4E', 'name': 'Bill Trading Day Premarket Brief', 'active': 0}, {'id': 'L5yAq4PKIChchogV', 'name': 'Blog Auto-Publisher', 'active': 0}, {'id': 'cofounder-orchestrator-status-sync', 'name': 'Cofounder Orchestrator Status Sync', 'active': 1}, {'id': 'AzEDluofoHW1NYZk', 'name': 'Content Calendar Orchestrator', 'active': 0}, {'id': 'aLYJsS6dx3fnfT6a', 'name': 'Cross-Platform Content Adapter', 'active': 0}, {'id': 'CJdWKLfj5Oa2pba7', 'name': 'Daily Briefing — Composite Summary', 'active': 1}, {'id': 'xRd8GGMtXs47NFG3', 'name': 'Discord → Postiz Multi-Platform Scheduler', 'active': 0}, {'id': '3W2dJKRSlHumL6T5', 'name': 'Founder Email Auto-Reply', 'active': 1}, {'id': 'iOthOKXW7RrLLjZy', 'name': 'GDrive Monitor — New File Alert', 'active': 1}, {'id': 'Ud2ejXJghwr61eZi', 'name': 'Gmail Agent — Inbox Monitor', 'active': 1}, {'id': 'hgD9a7JNDcjGCIlc', 'name': 'Hermes App Launch → Social Blast', 'active': 0}, {'id': '70LrkgnIRJ4A1d6v', 'name': 'LinkedIn Daily Post — AgentPay', 'active': 0}, {'id': 'linkedin-daily-post-agentpay', 'name': 'LinkedIn Daily Post — AgentPay', 'active': 0}, {'id': 'r2my7GeRVxxTdP73', 'name': 'MCP Gateway — Agent Tools', 'active': 1}, {'id': 'Q2H1Viq7wWMDIAeo', 'name': 'Master Social Orchestrator', 'active': 0}, {'id': 'NFABzuIvr1jxiADp', 'name': 'Outbound Email Campaign (AI + Human-in-Loop)', 'active': 1}, {'id': 'DnVosuFgA9KrLmAU', 'name': 'Personal Assistant — Inbox Triage', 'active': 1}, {'id': 'GqtoUWfmJDagbWZh', 'name': 'Reels & Short Video Campaign', 'active': 0}, {'id': 'Wmp8yJrjdJPXeEWT', 'name': 'Research → Draft Post (OpenClaw/Hermes trigger)', 'active': 0}, {'id': 'shortform-release-gate', 'name': 'Short-Form Intake and Release Gate', 'active': 1}, {'id': 'IwOhMcBswyCnN2Sz', 'name': 'Social Reply & Engagement Monitor', 'active': 1}]` |  |
| Trading expansion gate evaluated and remains red | `WARN` | `/Users/brain/hedge/.rumbling-hedge/state/live-readiness-gate.latest.json readyForLive=False readyForDemoExpansion=False blockers=['source tree has uncommitted source changes', 'Topstep monitor artifact is missing', 'Topstep session-safety artifact is missing', 'futures realtime data is not execution-grade: verdict=STALE action=block_all_trades', 'futures cost/slippage gate is not deployable: backtrader survivors=0 volOos survivors=0', 'walk-forward gate is not deployable', 'rolling OOS deployable windows 0/3 across 0 evaluated', 'stressed live-readiness is not deployable']` | Do not increase size, accounts, or autonomy until live-readiness blockers clear. |
| Fund expansion ladder is explicit and execution-locked | `PASS` | `decision=fund-promotion-contract-research-only-execution-locked readyForDemoExpansion=False readyForPaper=False stages=['l0-research-only-control-plane', 'l1-futures-topstep-demo', 'l2-prediction-paper', 'l3-prediction-trader', 'l4-copy-trading-and-brokerage', 'l5-options-expansion']` |  |

## Hermes Cron Risk

- Jobs file: `/Users/brain/.hermes/cron/jobs.json`
- Enabled jobs: `1`
- Enabled execution-adjacent jobs: `0`


## Fund Promotion Contract

- Decision: `fund-promotion-contract-research-only-execution-locked`
- Current stage: `research-only-control-plane`
- Next stage: `clear-futures-demo-gates`
- Ready for demo expansion: `False`
- Ready for prediction paper: `False`

- `l0-research-only-control-plane` — `blocked`: Research agents may propose one-variable tests; deterministic gates own promotion and execution.
- `l1-futures-topstep-demo` — `blocked`: Only after source hygiene, current/broker parity, execution-grade data, live-readiness, and daily approval all pass.
- `l2-prediction-paper` — `blocked`: Only after no-lookahead event windows, clean mapping, fillability, resolved labels, and post-spread edge pass.
- `l3-prediction-trader` — `blocked`: Only after paper evidence clears and execution/funding firewalls are intentionally approved.
- `l4-copy-trading-and-brokerage` — `blocked`: Only after a profitable month, clean fills, payout discipline, source hygiene, and copy/broker approvals.
- `l5-options-expansion` — `blocked`: Options remain a risk/regime overlay until futures, prediction, copy, and brokerage operations are proven.

## n8n State

- DB: `/Users/brain/.n8n/database.sqlite`
- Workflows: `[{"id": "TamyClnUY16TpMy5", "name": "App Idea \u2192 Build \u2192 Launch \u2192 Advertise", "active": 0}, {"id": "33D58D54-EE64-441E-9D9D-8F5CB8765F4E", "name": "Bill Trading Day Premarket Brief", "active": 0}, {"id": "L5yAq4PKIChchogV", "name": "Blog Auto-Publisher", "active": 0}, {"id": "cofounder-orchestrator-status-sync", "name": "Cofounder Orchestrator Status Sync", "active": 1}, {"id": "AzEDluofoHW1NYZk", "name": "Content Calendar Orchestrator", "active": 0}, {"id": "aLYJsS6dx3fnfT6a", "name": "Cross-Platform Content Adapter", "active": 0}, {"id": "CJdWKLfj5Oa2pba7", "name": "Daily Briefing \u2014 Composite Summary", "active": 1}, {"id": "xRd8GGMtXs47NFG3", "name": "Discord \u2192 Postiz Multi-Platform Scheduler", "active": 0}, {"id": "3W2dJKRSlHumL6T5", "name": "Founder Email Auto-Reply", "active": 1}, {"id": "iOthOKXW7RrLLjZy", "name": "GDrive Monitor \u2014 New File Alert", "active": 1}, {"id": "Ud2ejXJghwr61eZi", "name": "Gmail Agent \u2014 Inbox Monitor", "active": 1}, {"id": "hgD9a7JNDcjGCIlc", "name": "Hermes App Launch \u2192 Social Blast", "active": 0}, {"id": "70LrkgnIRJ4A1d6v", "name": "LinkedIn Daily Post \u2014 AgentPay", "active": 0}, {"id": "linkedin-daily-post-agentpay", "name": "LinkedIn Daily Post \u2014 AgentPay", "active": 0}, {"id": "r2my7GeRVxxTdP73", "name": "MCP Gateway \u2014 Agent Tools", "active": 1}, {"id": "Q2H1Viq7wWMDIAeo", "name": "Master Social Orchestrator", "active": 0}, {"id": "NFABzuIvr1jxiADp", "name": "Outbound Email Campaign (AI + Human-in-Loop)", "active": 1}, {"id": "DnVosuFgA9KrLmAU", "name": "Personal Assistant \u2014 Inbox Triage", "active": 1}, {"id": "GqtoUWfmJDagbWZh", "name": "Reels & Short Video Campaign", "active": 0}, {"id": "Wmp8yJrjdJPXeEWT", "name": "Research \u2192 Draft Post (OpenClaw/Hermes trigger)", "active": 0}, {"id": "shortform-release-gate", "name": "Short-Form Intake and Release Gate", "active": 1}, {"id": "IwOhMcBswyCnN2Sz", "name": "Social Reply & Engagement Monitor", "active": 1}]`

## Missing/Blocked

- `dom-proxy-signal.latest.json cannot affect execution unless promoted` — Re-run the generator after patching it to emit shadow-only execution fields.
- `kalman-pairs-signal.latest.json cannot affect execution unless promoted` — Re-run the generator after patching it to emit shadow-only execution fields.
- `whale-flow-signal.latest.json cannot affect execution unless promoted` — Re-run the generator after patching it to emit shadow-only execution fields.
- `Rolling optimizer is shadow-only and finite` — Re-run rolling_window_optimizer.py after NaN guard patch.
- `60m data is fresh enough for research evaluation` — Refresh 60m research data before any research run.
- `15m data is fresh enough for research evaluation` — Refresh 15m research data before ORB/DOM-proxy/15m research matters.
- `Databento realtime smoke artifact exists and is research-only` — Run npm run bill:databento-realtime-smoke and keep it separate from realtime-quote.latest.json.
- `Hermes cron state is validator-cleared or prompts describe shadow/guarded execution posture` — Run npm run bill:cron-state-validator or update ~/.hermes/cron/jobs.json prompts so agents do not inherit stale execution language.

## Warnings

- `Realtime execution data remains blocked` — Do not route futures demo/live orders until realtime preflight is green from execution-grade data.
- `Futures strategy lane remains research-only` — Do not promote full-sample survivors; require OOS, walk-forward, stress, cost/slippage, and live-readiness gates.
- `Prediction-market lane remains research-only` — Keep prediction execution in paper/skipped mode until market-specific resolved-history and calibration gates pass.
- `Source tree remains too dirty for live-money clearance` — Finish, verify, and intentionally commit/stage bounded source changes before any live-money clearance.
- `Hermes runtime has archive candidates but cleanup is not executed` — Only archive/delete after operator approval, inactive-profile review, and verified Seagate copy/checksum.
- `Trading expansion gate evaluated and remains red` — Do not increase size, accounts, or autonomy until live-readiness blockers clear.
