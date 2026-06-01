# Bill Fund OS Completion Audit — 2026-05-26

Overall status: `HANDOFF_COMPLETE_TRADING_BLOCKED`
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
| dom-proxy-signal.latest.json cannot affect execution unless promoted | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/dom-proxy-signal.latest.json promoted=False tradable=False evidence=proxy_shadow_only` |  |
| kalman-pairs-signal.latest.json cannot affect execution unless promoted | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/kalman-pairs-signal.latest.json promoted=False tradable=False evidence=research_shadow_only` |  |
| whale-flow-signal.latest.json cannot affect execution unless promoted | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/whale-flow-signal.latest.json promoted=False tradable=False evidence=weekly_cot_shadow_only` |  |
| Rolling optimizer is shadow-only and finite | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/rolling-window-params.latest.json promoted=False` |  |
| 60m data is fresh enough for research evaluation | `PASS` | `latest=2026-05-29T20:00:00.000Z age_minutes=2827.986933333333 closed_market_bar_ok=True` |  |
| 15m data is fresh enough for research evaluation | `PASS` | `latest=2026-05-29T20:45:00.000Z age_minutes=2782.9869370166666 closed_market_bar_ok=True` |  |
| Realtime data preflight exists and is read-only | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/realtime-data-preflight.latest.json readyForExecutionData=False decision=block-execution-data blockers=['source=none is not marked execution-grade', 'data freshness gate is STALE (expected until open-session proof; Databento smoke reports market closed)']` |  |
| Realtime execution data remains blocked | `WARN` | `decision=block-execution-data blockers=['source=none is not marked execution-grade', 'data freshness gate is STALE (expected until open-session proof; Databento smoke reports market closed)']` | Do not route futures demo/live orders until realtime preflight is green from execution-grade data. |
| Databento realtime smoke artifact exists and is research-only | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/databento-realtime-smoke.latest.json status=NO_QUOTES_MARKET_CLOSED readyForExecutionDataProof=False writesRealtimeQuoteState=False session=Sunday before the usual 18:00 ET Globex open` |  |
| Databento live quote proof remains unavailable | `WARN` | `status=NO_QUOTES_MARKET_CLOSED reason=Databento did not produce both NQ/ES quotes inside the smoke timeout; market likely closed: Sunday before the usual 18:00 ET Globex open.` | Retry the smoke during an active CME Globex session before attempting a canonical Databento realtime bridge write. |
| Databento realtime bridge is explicit and default-off | `PASS` | `/Users/brain/hedge/scripts/realtime_data_bridge.py` |  |
| Prediction funding helpers fail closed unless explicitly approved | `PASS` | `scripts=5 verifier=/Users/brain/hedge/scripts/verify_prediction_funding_firewall.py` |  |
| Futures evidence triage artifact exists | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/futures-evidence-triage.latest.json decision=research-only; no futures strategy is currently demo-expandable` |  |
| Futures strategy lane remains research-only | `WARN` | `decision=research-only; no futures strategy is currently demo-expandable liveBlockers=['source tree has uncommitted source changes', 'OpenJarvis board is stale (19948s old)', 'futures realtime data is not execution-grade: verdict=BLOCK action=block_all_trades', 'futures cost/slippage gate is not deployable: backtrader survivors=12 volOos survivors=0'] +4 more` | Do not promote full-sample survivors; require OOS, walk-forward, stress, cost/slippage, and live-readiness gates. |
| Prediction-market evidence triage artifact exists | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/prediction-evidence-triage.latest.json decision=research-only; no prediction-market candidate is paper-ready` |  |
| Prediction-market lane remains research-only | `WARN` | `decision=research-only; no prediction-market candidate is paper-ready clobStatus=REJECT_NO_EDGE watchCount=3 readyForPaper=False` | Keep prediction execution in paper/skipped mode until market-specific resolved-history and calibration gates pass. |
| Kalshi fillability snapshot is present and research-only | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/kalshi-fillability-snapshot.latest.json marketsInspected=416 executablePublicQuotes=31 bucketCounts={'too-wide': 47, 'usable': 18, 'no-two-sided-book': 251, 'wide': 87, 'tight': 13}` |  |
| Futures no-edge memory is present | `PASS` | `path=/Users/brain/hedge/.rumbling-hedge/research/futures-no-edge-ledger/latest.json count=5 noEdgeCount=4 needsNewFeatureCount=1 promotableCount=0` |  |
| Prediction no-edge memory is present | `PASS` | `path=/Users/brain/hedge/.rumbling-hedge/research/prediction-no-edge-ledger/latest.json count=14 noEdgeCount=10 needsMoreDataCount=4 promotableCount=0` |  |
| Research loop separates LLM research from deterministic execution | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/bill-research-closed-loop-contract.latest.json readyForExecution=False researchOnly=True deterministicCodeRoutes=True llmMayRoute=False` |  |
| CFTC TFF positioning intake is fresh and research-only | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/cftc-tff-positioning.latest.json freshForWeeklyResearch=True latestReportDate=2026-05-26 markets=['ES', 'NQ', 'ZN'] tradable=False` |  |
| Worktree consolidation artifact exists | `PASS` | `posture=organized-blocked-for-live-money sourceCleanBlockers=['canonical source root has 350 dirty files', 'canonical source root has 27 dirty execution/live files', '1 dirty sibling worktree(s) remain quarantine/selective-intake only']` |  |
| Source tree remains too dirty for live-money clearance | `WARN` | `canonicalDirtyFiles=350 categories={'governance-risk': 27, 'strategy-research': 169, 'data': 17, 'execution-live': 27, 'external-vendor': 1, 'generated-cache': 0, 'ops-docs': 107, 'dependencies': 2, 'unknown': 0} blockers=['canonical source root has 350 dirty files', 'canonical source root has 27 dirty execution/live files', '1 dirty sibling worktree(s) remain quarantine/selective-intake only']` | Finish, verify, and intentionally commit/stage bounded source changes before any live-money clearance. |
| Hermes runtime storage audit exists and is manifest-only | `PASS` | `/Users/brain/hedge/.rumbling-hedge/state/hermes-storage-audit.latest.json totalSize=19.7GB archiveCandidateSize=13.3GB movesFiles=False deletesFiles=False` |  |
| Hermes runtime has archive candidates but cleanup is not executed | `WARN` | `archiveCandidateSize=13.3GB topCandidates=[{'action': 'inspect-profile-subdirs-before-archive', 'bytes': 11146728295, 'exists': True, 'name': 'profiles', 'path': '/Users/brain/.hermes/profiles', 'reason': 'Large agent/model profile root; individual profiles may be active or cold.', 'size': '10.4GB', 'tier': 'warm-profile-cache'}, {'action': 'archive-with-checksum-before-delete', 'bytes': 2165531844, 'exists': True, 'name': 'state-snapshots', 'path': '/Users/brain/.hermes/state-snapshots', 'reason': 'Rollback snapshots are large and usually cold, but deletion requires verified archive copy.', 'size': '2.0GB', 'tier': 'cold-snapshot-candidate'}, {'action': 'archive-old-files-only', 'bytes': 884357492, 'exists': True, 'name': 'sessions', 'path': '/Users/brain/.hermes/sessions', 'reason': 'Useful recent history; only rotate/archive old files after retention policy is chosen.', 'size': '843.4MB', 'tier': 'warm-rotating-history'}, {'action': 'archive-old-files-only', 'bytes': 56804710, 'exists': True, 'name': 'logs', 'path': '/Users/brain/.hermes/logs', 'reason': 'Useful recent history; only rotate/archive old files after retention policy is chosen.', 'size': '54.2MB', 'tier': 'warm-rotating-history'}] +1 more` | Only archive/delete after operator approval, inactive-profile review, and verified Seagate copy/checksum. |
| Master bridge reads canonical state and ignores unpromoted overlays | `PASS` | `/Users/brain/hedge/scripts/master_bridge.py` |  |
| Hermes master bridge delegates to canonical repo bridge | `PASS` | `/Users/brain/.hermes/scripts/master_bridge.py` |  |
| Legacy LucidFlex bridge defaults to shadow-only | `PASS` | `repo and Hermes 60m_exec_bridge.py` |  |
| Agentic fund cycle defaults to shadow-only and canonical state | `PASS` | `repo and Hermes agentic_fund.sh` |  |
| Hermes cron state is validator-cleared or prompts describe shadow/guarded execution posture | `PASS` | `validatorCleared=True blockingIssueCount=0 activeDirtyExecutionLiveScriptReferenceCount=0 quarantinedScriptReferenceCount=0 enabledExecutionAdjacent=3` |  |
| n8n has no hidden active Bill execution workflow | `PASS` | `workflows=[{'id': '33D58D54-EE64-441E-9D9D-8F5CB8765F4E', 'name': 'Bill Trading Day Premarket Brief', 'active': 0}, {'id': '70LrkgnIRJ4A1d6v', 'name': 'LinkedIn Daily Post — AgentPay', 'active': 0}, {'id': 'linkedin-daily-post-agentpay', 'name': 'LinkedIn Daily Post — AgentPay', 'active': 1}]` |  |
| Trading expansion gate evaluated and remains red | `WARN` | `/Users/brain/hedge/.rumbling-hedge/state/live-readiness-gate.latest.json readyForLive=False readyForDemoExpansion=False blockers=['source tree has uncommitted source changes', 'OpenJarvis board is stale (19948s old)', 'futures realtime data is not execution-grade: verdict=BLOCK action=block_all_trades', 'futures cost/slippage gate is not deployable: backtrader survivors=12 volOos survivors=0', 'walk-forward gate is not deployable', 'rolling OOS deployable windows 0/3 across 4 evaluated', 'stressed live-readiness is not deployable', 'futures demo routing is outside safe envelope']` | Do not increase size, accounts, or autonomy until live-readiness blockers clear. |
| Fund expansion ladder is explicit and execution-locked | `PASS` | `decision=fund-promotion-contract-research-only-execution-locked readyForDemoExpansion=False readyForPaper=False stages=['l0-research-only-control-plane', 'l1-futures-topstep-demo', 'l2-prediction-paper', 'l3-prediction-trader', 'l4-copy-trading-and-brokerage', 'l5-options-expansion']` |  |

## Hermes Cron Risk

- Jobs file: `/Users/brain/.hermes/cron/jobs.json`
- Enabled jobs: `39`
- Enabled execution-adjacent jobs: `3`

- `discord-cli-bridge` (`22da58026d80`): keep quiet unless bridge failsKeep quiet unless bridge fails. This is messaging only; trading requires the guarded Topstep demo bridge and Obsidian approval.
- `agent-bridge-cron` (`bbf619dff56d`): Keep quiet unless bridge fails. This is monitoring/notification only; trading requires the guarded Topstep demo bridge and Obsidian approval.
- `gateway-tail-bridge` (`8b672b3ac905`): Run the gateway tail script to bridge CLI and Discord gateway.

## Fund Promotion Contract

- Decision: `fund-promotion-contract-research-only-execution-locked`
- Current stage: `research-only-control-plane`
- Next stage: `clear-futures-demo-gates`
- Ready for demo expansion: `False`
- Ready for prediction paper: `False`

- `l0-research-only-control-plane` — `pass`: Research agents may propose one-variable tests; deterministic gates own promotion and execution.
- `l1-futures-topstep-demo` — `blocked`: Only after source hygiene, current/broker parity, execution-grade data, live-readiness, and daily approval all pass.
- `l2-prediction-paper` — `blocked`: Only after no-lookahead event windows, clean mapping, fillability, resolved labels, and post-spread edge pass.
- `l3-prediction-trader` — `blocked`: Only after paper evidence clears and execution/funding firewalls are intentionally approved.
- `l4-copy-trading-and-brokerage` — `blocked`: Only after a profitable month, clean fills, payout discipline, source hygiene, and copy/broker approvals.
- `l5-options-expansion` — `blocked`: Options remain a risk/regime overlay until futures, prediction, copy, and brokerage operations are proven.

## n8n State

- DB: `/Users/brain/.n8n/database.sqlite`
- Workflows: `[{"id": "33D58D54-EE64-441E-9D9D-8F5CB8765F4E", "name": "Bill Trading Day Premarket Brief", "active": 0}, {"id": "70LrkgnIRJ4A1d6v", "name": "LinkedIn Daily Post \u2014 AgentPay", "active": 0}, {"id": "linkedin-daily-post-agentpay", "name": "LinkedIn Daily Post \u2014 AgentPay", "active": 1}]`

## Missing/Blocked

- None.

## Warnings

- `Realtime execution data remains blocked` — Do not route futures demo/live orders until realtime preflight is green from execution-grade data.
- `Databento live quote proof remains unavailable` — Retry the smoke during an active CME Globex session before attempting a canonical Databento realtime bridge write.
- `Futures strategy lane remains research-only` — Do not promote full-sample survivors; require OOS, walk-forward, stress, cost/slippage, and live-readiness gates.
- `Prediction-market lane remains research-only` — Keep prediction execution in paper/skipped mode until market-specific resolved-history and calibration gates pass.
- `Source tree remains too dirty for live-money clearance` — Finish, verify, and intentionally commit/stage bounded source changes before any live-money clearance.
- `Hermes runtime has archive candidates but cleanup is not executed` — Only archive/delete after operator approval, inactive-profile review, and verified Seagate copy/checksum.
- `Trading expansion gate evaluated and remains red` — Do not increase size, accounts, or autonomy until live-readiness blockers clear.
