# Bill/Hedge Deep Dive Audit - 2026-05-06

Generated from local inspection of `/Users/brain/hedge`, `~/.hermes`, `~/.openclaw`, `/Users/brain/Documents/memorybrain`, the Mac launchd layer, and the mounted Seagate HDD.

This is a system audit, not a recommendation to trade. Current posture remains research, paper, shadow, and demo-only until hard gates pass and founder approvals are explicit.

## Executive Readout

Bill/Hedge is no longer just an idea. It has a real TypeScript codebase, a Mac-native launchd ops layer, runtime artifacts, prediction-market collectors/scanners, futures research, Topstep demo routing guards, Hermes supervision artifacts, OpenJarvis board output, source catalogs, and a growing research/fork memory system.

The system is also not ready to behave like an autonomous fund. The core failure is not lack of files or ambition. The failure is proof, reliability, and control-plane maturity:

- Futures strategy-factory is blocked: latest artifact reports walk-forward not deployable, rolling OOS thin, OOS windows not deployable, live-readiness not deployable, and futures demo execution enabled while paper-only promotion logic expects it disabled.
- Prediction markets are collecting 3 venues and finding watch candidates, but no paper-trade candidates. Latest cycle posture is watch-only.
- Hermes has a structured supervisor queue, but it is still primarily a planner/supervisor artifact. It is not yet a robust autonomous worker scheduler with retries, task leases, rollbacks, and cost accounting.
- Mac Mini resource pressure is real: SSD is high usage, tests time out under load, health warns about disk/log headroom, and heavy jobs are intentionally capped to 1.
- Many high-value market lanes exist as cataloged or partially wired research surfaces, not as fully validated execution sleeves.
- Git state is very dirty, with many source files modified and many new source/docs/scripts untracked. This is dangerous for a system that wants institutional reproducibility.

The correct near-term goal is not "turn on more agents." It is to make the existing machine boring, auditable, fail-closed, and statistically honest.

## Verification Snapshot

- [x] Located canonical repo: `/Users/brain/hedge`
- [x] Confirmed GitHub remote: `https://github.com/Rumblingb/hedge.git`
- [x] Current branch: `codex/bill-hedge-autonomy-spine`
- [x] Confirmed Mac launchd jobs for Bill and Hermes exist
- [x] Confirmed Apple Notes export from 2026-05-05 exists under `.rumbling-hedge/research/founder-notes/`
- [x] Confirmed Seagate HDD mounted and active
- [x] Ran TypeScript typecheck: passed
- [x] Ran `bill-health`: exited 0 and produced full JSON
- [!] Ran full test suite: 61 test files passed, 6 failed; 218 tests passed, 7 timed out in heavy research/live/OOS paths
- [!] Repo is dirty: both source and runtime files are modified/untracked

Timed-out suites/tests:

- `tests/agenticLoop.test.ts`: first agentic improvement loop test timed out at 50s.
- `tests/dailyPlan.test.ts`: first daily strategy plan test timed out at 45s.
- `tests/jarvisBrief.test.ts`: Jarvis brief envelope test timed out at 45s.
- `tests/liveReadiness.test.ts`: live deployment readiness test timed out at 45s.
- `tests/research.test.ts`: first walk-forward research test timed out at 45s.
- `tests/rollingOos.test.ts`: both rolling OOS tests timed out, one at 45s and one at 150s.

## Current Runtime State

Latest checked files:

- `STATUS.md`: system status around 2026-05-06 01:15 UTC
- `TAKEOVER.md`: takeover status around 2026-05-06 20:32 UTC
- `.rumbling-hedge/logs/bill-health.latest.json`
- `.rumbling-hedge/state/openjarvis-board.md`
- `.rumbling-hedge/state/hermes-supervisor.json`
- `.rumbling-hedge/state/prediction-cycle.latest.json`
- `.rumbling-hedge/state/strategy-factory.latest.json`
- `.rumbling-hedge/state/live-readiness.latest.json`
- `.rumbling-hedge/state/promotion-state.json`
- `.rumbling-hedge/state/quant-autonomy.latest.json`

Observed runtime posture:

- Prediction lane: active, shadow/watch-only.
- Futures-core lane: active, shadow/demo sampling, not deployable.
- Options-us: research-only, collecting/setup-debt.
- Crypto-liquid: research-only, collecting.
- Macro-rates: research-only, collecting.
- Long-only-compounder: research-only, setup-debt.
- Hermes supervisor: bounded-parallel queue exists.
- OpenJarvis: founder-facing board exists.
- Heavy compute: capped at 1.

## Mac Mini / HDD / Obsidian / Notes Inventory

### Mac Mini

- [x] `ops/mac-mini/` exists as the repo-native operator layer.
- [x] `~/Library/LaunchAgents` has Bill launchd jobs loaded or registered.
- [x] `bill-health` reports runtime OK but degraded warnings.
- [x] `BILL_MAX_HEAVY_JOBS=1` posture is encoded in docs and health output.
- [!] Full test suite is timeout-sensitive under current machine load.
- [!] Disk headroom is a recurring warning. Health reported around 26 GiB free; TAKEOVER reported 21.39 GiB free and 90.63% disk usage at one point.

### HDD / Cold Storage

Mounted volume:

- `/Volumes/Seagate Expansion Drive`
- `/Volumes/Seagate Expansion Drive/rumbling-hedge-cold`

Found cold storage:

- `archives/hedge-archive-2026-05-03_1047`
- `archives/hedge-archive-2026-05-03_2305`
- `archives/hedge-archive-2026-05-05_0237`
- `archives/superseded-csvs`
- `log-archives`
- `prediction-market-analysis`
- `repos/oracle3`
- `repos/pmxt`
- `repos/polymarket-agents`
- `strategy-lab-history`

Status:

- [x] HDD is mounted.
- [x] HDD has large free capacity.
- [x] Cold archives exist.
- [x] Prediction Market Analysis corpus is on HDD.
- [!] Hot repo still carries `.rumbling-hedge`, `data`, and duplicated dependency folders on SSD. Cleanup policy exists but needs stricter enforcement.
- [!] Need automated cold-tier lifecycle: archive, verify checksum, prune hot copy, record manifest.

### Obsidian / Memorybrain

Found:

- `/Users/brain/Applications/Obsidian.app`
- `/Users/brain/Documents/memorybrain/.obsidian`
- `/Users/brain/Documents/memorybrain/Agent-Hermes`
- `/Users/brain/Documents/memorybrain/Agent-Shared/Fleet/04-bill-hedge`
- `/Users/brain/Documents/memorybrain/Agent-Shared/hermes-goal-prompt.md`

Status:

- [x] Obsidian app and vault-like memorybrain folders exist.
- [x] Fleet docs include a Bill/Hedge lane and separation policy.
- [x] Hermes daily notes and master plan files exist.
- [!] Obsidian/memorybrain is not the canonical source for Bill runtime truth. Repo runtime artifacts are more current.
- [!] Need one-way sync rules: repo structured artifacts should feed Obsidian summaries, not the reverse.

### Apple Notes From 2026-05-05

Found:

- `.rumbling-hedge/research/founder-notes/apple-notes-2026-05-05.txt`
- `.rumbling-hedge/research/founder-notes/apple-notes-2026-05-05.raw.html`
- `.rumbling-hedge/research/founder-notes/apple-notes-2026-05-05.summary.json`

Captured themes from the summary file:

- HMM/regime gating
- Multi-factor feedback loop
- Strategy correlation matrix
- Hybrid Kelly/VIX sizing
- COT positioning and dealer context
- Signal decay and auto-suspend logic
- Longer OOS windows and embargo
- Deflated Sharpe, PBO, and multiple-testing control
- Structural edges over published/statistical anomalies
- Tail Score using VIX backwardation, COT, capitulation
- Weekly research loop
- Bond/credit and yield curve context
- Alternative data sources
- Short-term alpha papers
- Retaining alpha papers
- Finding alphas / overfitting papers

Implementation mapping:

- [x] `MacroContext` exists in `src/domain.ts` for HMM, COT, VIX, capitulation, and Kronos fields.
- [x] HMM/state artifacts exist under `.rumbling-hedge/state/hmm-regime.json`.
- [x] COT positioning context exists and is reported for 6E, ES, NQ, ZN, CL, GC.
- [x] `src/engine/multiFactorRanking.ts` exists.
- [x] `src/engine/strategyCorrelation.ts` exists.
- [x] `src/signals/hybridKellyVixSizing.ts` exists.
- [x] `src/signals/vixContangoFlag.ts` exists.
- [x] `scripts/signal_decay_monitor.py` exists.
- [x] Strategy-factory records no-edge ledger and OOS blockers.
- [!] Dealer gamma is degraded for all checked underlyings due provider/permission issues.
- [!] HMM/COT/VIX/capitulation are not consistently applied across every strategy or promotion gate.
- [!] Deflated Sharpe/PBO exists in concept/artifacts, but the testing pipeline still times out and needs faster deterministic coverage.
- [!] Signal decay exists mostly as a sidecar script/state, not a hard first-class promotion gate everywhere.

## Repo Inventory

Top-level source/control areas:

- `src/`: TypeScript system code.
- `tests/`: 67 Vitest files.
- `ops/mac-mini/`: shell wrappers, launchd templates, scheduled Node scripts.
- `scripts/`: Python/shell research and market-lane sidecars.
- `docs/`: architecture, market, operations, and strategy docs.
- `config/`: Bill researcher target config.
- `patches/`: local patch/new target artifacts.
- `memory/`: untracked memory area.
- `.rumbling-hedge/`: runtime state, logs, research corpus, reports.
- `data/`: market data, snapshots, prediction data, research data.
- `dist/`: built JS output.
- `node_modules/` and `node_modules.broken/`: dependencies and broken duplicate dependency tree.

Important source modules by count:

- `src/engine`: 28 files.
- `src/research`: 28 files.
- `src/prediction`: 20 files.
- `src/strategies`: 64 files.
- `src/signals`: 5 files.
- `src/live`: 4 files.
- `src/data`: 5 files.
- `src/utils`: 6 files.

Test surface:

- 67 test files exist.
- The suite has broad coverage: prediction, research, execution guards, Topstep adapter, data, risk, strategy feeds, live readiness, OpenJarvis, and source catalogs.
- The suite is too heavy in current conditions: several high-level tests timed out at 45s to 50s during full run.

## Implementation Status By Layer

### 1. Configuration and Guardrails

Files:

- `src/config.ts`
- `src/domain.ts`
- `src/risk/guardrails.ts`
- `src/engine/killSwitch.ts`
- `docs/RISK_GUARDRAILS.md`

Status: implemented but incomplete for fund-grade operation.

Implemented:

- Paper/backtest/live mode shape.
- Challenge/funded profile defaults.
- Allowed Topstep symbols list.
- Topstep demo-only and read-only configuration.
- Kill switch path.
- Session windows, max trades, daily loss, max hold, RR threshold.
- Execution latency/slippage modeling fields.
- Stop management config.
- Secret redaction for diagnostics.

Gaps:

- Guardrails are mostly per-run config, not a centralized immutable policy ledger.
- No formal policy versioning or signed approval trail.
- No automated diff guard that refuses unapproved risk widening in Git.
- `futuresDemoDisabled` mismatch appears in strategy-factory blockers while demo routing is enabled for evidence collection.
- Live prediction gate is strict, but futures demo/live gate semantics need clearer separation: shadow, demo-route, paper-sim, real-money.

Checklist:

- [x] Encode core guardrails in code.
- [x] Read env and default conservatively.
- [x] Redact secrets.
- [x] Kill switch exists.
- [ ] Add immutable policy version field to every execution/research artifact.
- [ ] Add "risk widening requires approval" diff checker.
- [ ] Separate futures shadow/demo/paper/live terminology in schemas.
- [ ] Add formal capital allocator policy.

### 2. Backtest / Research / Walk-Forward

Files:

- `src/engine/backtest.ts`
- `src/engine/walkforward.ts`
- `src/engine/rollingOos.ts`
- `src/engine/riskModel.ts`
- `src/engine/expectedValueSurface.ts`
- `src/engine/strategyFactory.ts`
- `src/engine/liveReadiness.ts`
- `src/engine/agenticFund.ts`
- `src/engine/agenticLoop.ts`
- `src/research/profiles.ts`

Status: substantially implemented, not institutional-grade yet.

Implemented:

- Walk-forward research.
- Rolling OOS.
- Live readiness stress pass.
- Strategy-factory gate aggregator.
- Agentic improvement loop that only tightens selected env parameters.
- No-edge ledger.
- Research profiles with strategy/symbol/guardrail overrides.
- Survivability score and failed check diagnostics.

Current artifacts:

- Strategy-factory status: blocked.
- Selected profile: `ict-killzone-core`.
- Profiles available: 17.
- Latest targeted run evaluated only 1 profile.
- Latest strategy-factory evidence: survivability score 10, live readiness final score 0, rolling OOS mean survivability 12.
- Latest live readiness final: status red, survivability score 50, not deployable.

Gaps:

- Heavy tests time out, indicating high-level evaluation is too slow or too broad for routine CI on the Mac.
- OOS evidence is thin; latest rolling OOS only 1/2 windows in one artifact and warnings mention 1/4 requested windows elsewhere.
- Strategy-factory profile selection is currently narrow in latest run, so broad strategy catalog is not really being evaluated each cycle.
- No full experiment registry with dataset hash, policy hash, code commit hash, and random seed per run.
- No PBO/deflated Sharpe report as a mandatory top-level artifact for every candidate.
- Research can still produce lots of candidate complexity before the proof harness is strong enough.

Checklist:

- [x] Backtest engine exists.
- [x] Walk-forward exists.
- [x] Rolling OOS exists.
- [x] Live-readiness stress exists.
- [x] No-edge ledger exists.
- [x] Agentic tightening loop exists.
- [ ] Make heavy tests deterministic and fast enough for every commit.
- [ ] Require 4+ independent OOS windows before any promotion.
- [ ] Add dataset/code/config hash to all research artifacts.
- [ ] Promote PBO/deflated Sharpe from idea to required artifact.
- [ ] Build a compact experiment registry indexed by strategy, dataset, commit, and regime.

### 3. Strategy Catalog

Files:

- `src/strategies/*.ts`
- `src/strategies/wctcEnsemble.ts`
- `src/signals/*.ts`
- `src/domain.ts`

Status: broad implementation, uneven proof.

Implemented in active catalog:

- ICT displacement
- Opening range reversal
- Session momentum
- Liquidity reversion
- Expiry flow
- Pairs trading
- Cross-sectional momentum
- Volatility regime
- VWAP reversion
- Bollinger squeeze
- WorldQuant alpha subset
- Drift-regime CSM
- HMM pairs arb
- Gamma stability
- LLM momentum gate
- Two-level uncertainty
- LLM GA evolutionary
- Drawdown momentum
- Push-response anomaly
- Optimal cost pairs
- Network momentum
- Capitulation score
- Structural flows
- Event spike fade
- Opening stop hunt
- Post-news settlement
- Options selling framework

Status split:

- Implemented and tested at least at unit/smoke level: core strategies, some prediction and risk-adjacent logic.
- Implemented but incomplete: structural flows, capitulation/tail, gamma-conditioned strategies, options framework, event spike/news settlement, HMM macro wiring.
- Not truly implemented as production lanes: L2 microstructure absorption, real futures curve carry, robust options vol surface, full long-only compounder, portfolio optimizer, PMA-driven calibration at scale.

Gaps:

- 64 strategy files are too many relative to proof quality. This is a research library, not a validated fund.
- Several strategies are pattern proxies using OHLCV rather than true microstructure or venue-specific data.
- Strategy correlation exists but is not yet a hard portfolio exposure governor across all lanes.
- Signal decay exists but is not universally enforcing auto-suspension.
- Macro context fields exist, but strategy use is partial.

Checklist:

- [x] Broad strategy catalog exists.
- [x] Ensemble selection exists.
- [x] Multi-factor ranking hook exists.
- [x] No-edge memory exists.
- [ ] Reduce active execution candidates to 2 to 3 lanes until proof improves.
- [ ] Add per-strategy "proof passport": data, OOS, stress, decay, correlation, deployment status.
- [ ] Promote correlation matrix to a hard exposure guard.
- [ ] Promote signal decay to a hard demotion guard.
- [ ] Split "research-only strategy" from "candidate strategy" in code, not only docs.

### 4. Prediction Markets

Files:

- `src/prediction/*`
- `src/prediction/adapters/kalshi.ts`
- `src/prediction/adapters/manifold.ts`
- `src/prediction/adapters/polymarket.ts`
- `src/prediction/execution/*`
- `.rumbling-hedge/state/prediction-cycle.latest.json`
- `.rumbling-hedge/state/promotion-state.json`

Status: implemented for collection, scan, review, and fail-closed paper/live gating. Not generating deployable paper candidates.

Implemented:

- Polymarket, Kalshi, and Manifold collection.
- Cross-venue matcher/scanner.
- Fees/sizing/policy.
- Committee review.
- Journal/report/training/review.
- Live gate that refuses unless explicit env approvals are set.
- Promotion state artifact.
- Copy-demo lane, currently disabled/fail-closed.

Latest cycle:

- Source: combined.
- Markets collected: 600.
- Venue counts: Polymarket 540, Kalshi 54, Manifold 6.
- Cross-venue pairs: 32,724.
- Viable pairs: 2.
- Verdict counts: reject 0, watch 2, paper-trade 0.
- Execute: skipped because promotion review is not ready for paper execution.
- Promotion blockers: no-paper-candidates, top-candidate-zero-stake, lead-candidate-not-paper-trade, committee-reject.

Gaps:

- No paper candidates over recent cycles.
- Committee and scan policy may be too strict or correctly exposing lack of real edge. Do not loosen until counterfactual analysis proves missed profitable trades.
- Copy-demo disabled and domain-filter idle.
- No authenticated execution path should be trusted until paper evidence exists.
- PMA dataset is ready on HDD but not fully integrated into live scanner calibration.

Checklist:

- [x] Collect 3 venues.
- [x] Cross-venue matching exists.
- [x] Committee exists.
- [x] Promotion state exists.
- [x] Live gate fail-closed.
- [ ] Add counterfactual report: "what did we reject and what happened later?"
- [ ] Calibrate scan thresholds against PMA historical corpus.
- [ ] Add micro-paper state distinct from watch and paper-trade, with explicit approval.
- [ ] Keep live disabled until paper fills have a real record.

### 5. Futures / Topstep / Demo

Files:

- `src/adapters/projectx/*`
- `src/adapters/topstep/topstepAdapter.ts`
- `src/live/*`
- `src/engine/dailyPlan.ts`
- `src/engine/liveReadiness.ts`
- `docs/TOPSTEP_DEMO_OPERATING_PATH.md`

Status: guarded demo/shadow path exists, not deployable.

Implemented:

- ProjectX/Topstep adapter.
- Demo account allowlist and lock.
- Demo sampling lanes.
- Futures preflight data refresh.
- Demo execution route with blockers.
- Live readiness artifact.
- Daily plan and operator-facing output.

Latest live readiness:

- Baseline status yellow, not deployable.
- Stressed baseline status red, not deployable.
- Final report status red, survivability score 50, not deployable.
- Failed checks include testTradeCount, cvar95TradeR, riskOfRuinProb, deflatedExpectancyR.
- Config is demo-only but read-only false in artifact, so route must remain guarded by evidence and explicit flags.

Gaps:

- Out-of-sample evidence is too thin.
- Strategy-factory says futures demo execution being enabled conflicts with paper-only promotion.
- Single data issues can degrade whole lane; Hermes queue already flags symbol-specific fallbacks.
- Full test suite times out in futures-heavy tests.
- No real broker-grade execution audit trail yet: order intent, route, adapter response, position reconciliation, and kill-switch snapshot per order.

Checklist:

- [x] Demo account lock exists.
- [x] Topstep adapter tests exist.
- [x] Futures preflight exists.
- [x] Demo sampling exists.
- [x] Live readiness exists.
- [ ] Keep demo route off unless evidence and founder approval both pass.
- [ ] Add order ledger with intent, approval, adapter response, reconciliation.
- [ ] Fix terminology mismatch between paper-only promotion and demo evidence collection.
- [ ] Add symbol-level degradation instead of lane-level failure.

### 6. Researcher / Source Catalog / Fork Intake

Files:

- `src/research/*`
- `config/researcher-targets.bill.json`
- `.rumbling-hedge/research/*`
- `docs/BILL_SOURCE_CATALOG.md`

Status: substantially implemented as research ingestion and memory. Needs stronger yield, quality, and provenance.

Implemented:

- Source catalog.
- Research collector/crawler/filter/corpus.
- YouTube transcript support.
- Strategy hypotheses.
- Fork intake and fork synthesis.
- MiroFish, no-edge ledger, graveyard, vector memory.
- COT, macro, options, dealer gamma, positioning modules.

Current source catalog includes:

- Yahoo no-key bars: active.
- FRED: configured.
- Polygon: configured.
- Polymarket public trader data: wired for copy-demo.
- Alpaca: catalog-only.
- Databento: catalog-only/deeper path not wired.
- FinanceDatabase: catalog-only.
- OpenFIGI: catalog-only.
- PMXT: catalog-only.
- Polymarket SDK: catalog-only.
- PMA dataset: local/HDD bounded importer.
- SEC EDGAR: catalog-only.
- yfinance: catalog-only.

Gaps:

- Researcher found novel material in at least one run but retained no durable chunks.
- Many valuable vendors are catalog-only, not automated collectors.
- Dealer gamma failing due permissions or provider limitations.
- No central provenance score per research chunk feeding model/promotion.
- Research loop can become a content treadmill unless tied to experiment outcomes.

Checklist:

- [x] Source catalog exists.
- [x] Researcher-run exists.
- [x] Fork cards and synthesis exist.
- [x] Strategy hypotheses exist.
- [x] No-edge ledger exists.
- [ ] Improve researcher yield and retained chunk quality.
- [ ] Convert catalog-only sources into prioritized collector backlog.
- [ ] Add source provenance/age/permission score.
- [ ] Wire research output directly to experiment registry and no-edge decisions.

### 7. Hermes / OpenJarvis / OpenClaw

Files:

- `src/engine/hermesSupervisor.ts`
- `.rumbling-hedge/state/hermes-supervisor.json`
- `docs/HERMES_ORCHESTRATION_TODO.md`
- `docs/OPENJARVIS_CONTROL_PLANE.md`
- `~/.hermes`
- `~/.openclaw/workspace-bill`
- `~/.openclaw/workspace-hermes`
- `/Users/brain/Documents/memorybrain/Agent-Hermes`

Status: control-plane skeleton exists; autonomy supervisor is not yet robust enough for unattended fund operation.

Implemented:

- Hermes supervisor structured artifact.
- Active/queued/backlog/needs-approval/done task states.
- CLI commands documented for approve, pause, resume, complete, why.
- OpenJarvis board output.
- OpenClaw workspaces and Bill/Hermes memory exist.
- Hermes AgentPay Labs cycles exist under `~/.hermes/agentpay-labs`.

Current Hermes active work:

- Harden futures free-data refresh with symbol-specific fallbacks.
- Force one AgentPay artifact through Agency OS.
- Keep futures demo lanes sampling overnight.

Needs approval:

- Improve prediction economics and paper thresholds without forcing execution.
- Tighten futures evidence thresholds and ranking stability.
- Add approval and pause-resume controls so Hermes can run safe loops without widening authority.

Gaps:

- Supervisor queue exists but no confirmed durable worker lease protocol.
- No automatic rollback/safe retry policy yet.
- No phone-safe founder commands mapped into OpenJarvis controls yet.
- No complete cost accounting per worker/task/model.
- OpenClaw/Hermes memories are broad and partially legacy; current truth should be compact structured artifacts.
- Launchd has multiple jobs but no single self-healing Bill bash loop is active per TAKEOVER.

Checklist:

- [x] Structured supervisor artifact exists.
- [x] Approval/pause/resume command design exists.
- [x] OpenJarvis board exists.
- [x] OpenClaw workspaces exist.
- [ ] Add task leases, heartbeat expiry, retries, and failure quarantine.
- [ ] Add task cost ledger.
- [ ] Add phone-safe founder approval commands.
- [ ] Add "one truth" synchronization from runtime JSON to Obsidian/memory.
- [ ] Make Hermes run only bounded, typed worker contracts.

### 8. Ops / Launchd / Health

Files:

- `ops/mac-mini/bin/*`
- `ops/mac-mini/scripts/*`
- `ops/mac-mini/launchd/*`
- `~/Library/LaunchAgents/com.agentpay.bill.*`
- `~/Library/LaunchAgents/ai.hermes.gateway.plist`

Status: useful Mac-native ops layer exists; needs cleanup and self-healing discipline.

Implemented wrappers:

- doctor, health, cost profile
- prediction collect/scan/train/report/review/execute/cycle
- promotion status/review
- research collect/report/researcher
- paper loop
- live readiness
- kill switch
- TimesFM status
- NIM smoke
- strategy lab
- quant autonomy
- cold archive

Launchd observed:

- `com.agentpay.bill.prediction-cycle` every 600s.
- `com.agentpay.bill.paper-loop` every 3600s.
- health, research-collect, researcher-run, strategy-lab, quant-autonomy jobs present.
- Hermes gateway and Hermes watchdog/AgentPay Labs jobs present, some with nonzero launchctl status codes.

Gaps:

- Launchd jobs are distributed and not all clearly healthy.
- TAKEOVER notes no bash loop and no self-healing orchestrator.
- `bill-health` deep checks skipped unless `BILL_HEALTH_DEEP=true`.
- Runtime artifacts and logs consume material disk space.
- No single operator command gives "safe to run heavy job now" with disk, memory, swap, locks, and launchd status combined.

Checklist:

- [x] Mac-native wrappers exist.
- [x] Launchd templates exist.
- [x] Health script exists.
- [x] Cold archive script exists.
- [ ] Add launchd drift checker: repo templates vs installed plists.
- [ ] Add self-healing orchestrator or intentionally remove the expectation.
- [ ] Add hot-storage cleanup service with manifest.
- [ ] Run deep health on schedule when machine is idle.

## Financial Market Lane Audit

### Prediction Markets

Status: most operational active lane, still watch-only.

- [x] Polymarket collection.
- [x] Kalshi collection.
- [x] Manifold collection.
- [x] Matching, scan, committee, review.
- [x] Paper/live gates.
- [!] No paper candidates.
- [!] PMA corpus not fully used for calibration.

Next: build counterfactual rejected-candidate learning and PMA calibration.

### Futures Core

Status: central research/demo lane, blocked by evidence.

- [x] ES/NQ/CL/GC/6E/ZN data support.
- [x] Topstep/ProjectX adapter.
- [x] Demo account lock.
- [x] Strategy factory and live readiness.
- [!] OOS too thin.
- [!] Tail risk and risk-of-ruin blockers.
- [!] Dataset/data-provider fragility.

Next: narrow to ES/NQ, 2 strategies, 4+ OOS windows, full proof passport.

### Options US

Status: research-only/setup-debt.

- [x] Options collector modules exist.
- [x] Dealer gamma module exists.
- [x] Options strategy files exist.
- [!] Dealer gamma failing for SPY/QQQ/IWM/GLD/TLT.
- [!] No validated options execution lane.

Next: fix options greeks data, then build options-only research harness before any execution logic.

### Crypto Liquid

Status: data/research lane.

- [x] BTC/ETH bars exist.
- [x] BTC 5m edge module exists.
- [x] Crypto track scripts exist.
- [!] No complete exchange execution, risk, custody, or funding model.

Next: keep crypto as feature/training context and prediction-market subject matter until a real exchange/custody policy exists.

### Macro / Rates / Bonds

Status: context lane, partially wired.

- [x] COT data.
- [x] FRED configured.
- [x] ZN context.
- [x] Macro/rates source catalog.
- [!] Credit spread/yield curve features not fully enforced as gates.
- [!] COT weekly context is not a complete strategy.

Next: wire macro context as regime/risk modifiers, not entries.

### Long-Only Compounder

Status: concept/setup-debt.

- [x] Board recognizes lane.
- [x] Source catalog includes equities/fundamentals candidates.
- [!] No portfolio accounting, tax, rebalancing, factor/risk model, or broker integration.

Next: build separate research/accounting sleeve funded only from realized surplus.

### Alternative Data / Structural Edges

Status: concept plus some sidecars.

- [x] COT/positioning.
- [x] PMA dataset.
- [x] Source/fork catalog.
- [x] Apple Notes structural edge themes captured.
- [!] L2/MBO microstructure not implemented.
- [!] Futures curve carry not implemented with real curve data.
- [!] Congressional/social/filings/sentiment are not production collectors.

Next: prioritize structural edges where the data is real and cheap: COT, calendar, expiry, PMA, futures curve.

## Git / Reproducibility Audit

Current Git state:

- Many modified tracked files.
- Many new untracked docs/scripts/source modules.
- Runtime files changed under `data`, `journals`, and `.rumbling-hedge`.
- `.gitignore` has been updated to ignore many runtime paths.

Risk:

This is the biggest engineering risk after trading evidence. A system cannot become fund-grade if the source of truth is a dirty worktree plus runtime artifacts plus memory folders.

Checklist:

- [x] `.gitignore` excludes major runtime and dependency paths.
- [x] Remote origin exists.
- [!] Existing worktree is dirty.
- [!] Source changes and runtime changes are mixed.
- [!] `node_modules.broken` exists and consumes space.
- [ ] Create a clean branch/checkpoint commit for source-only changes.
- [ ] Move runtime artifacts to ignored state/cold storage.
- [ ] Add `npm run verify:source` that ignores runtime state.
- [ ] Add report of untracked source files that must be reviewed before promotion.

## Implemented vs Half-Implemented vs Not Implemented

### Implemented

- Repo-native Bill CLI with many commands.
- Mac-native wrappers and launchd templates.
- Prediction-market collection/scanning/review.
- Prediction live gate fail-closed.
- Futures backtest/walk-forward/OOS/live-readiness.
- Topstep/ProjectX adapter with demo account guard tests.
- Strategy catalog and ensemble.
- Researcher source catalog, corpus, fork intake/synthesis.
- Hermes supervisor artifact.
- OpenJarvis board artifact.
- No-edge ledger.
- Cold storage path and archives.
- Apple Notes import summary.

### Implemented But Incomplete

- Hermes as full supervisor.
- Strategy-factory proof.
- Futures demo/paper promotion.
- Prediction market paper trading.
- Dealer gamma and options surface.
- HMM/COT/macro context wiring.
- Signal decay and strategy correlation as hard gates.
- PMA historical calibration.
- Researcher target yield.
- Obsidian/memorybrain synchronization.
- Launchd self-healing.
- Deep health checks.
- Experiment registry.

### Not Implemented To Fund-Grade Standard

- Real autonomous capital allocation.
- Real-money live trading with institutional controls.
- Portfolio-wide exposure optimizer.
- Order lifecycle ledger and reconciliation.
- Broker/exchange/custody accounting across all lanes.
- L2/MBO scalp engine.
- Futures curve carry engine with real term-structure data.
- Production options vol/risk engine.
- Long-only compounder.
- Formal compliance/risk/audit trail.
- Disaster recovery runbook with tested restore.
- CI/CD with reproducible research artifacts.

## Gaps Blocking "Top Hedge Fund / Algo Firm" Standard

1. Evidence quality
   - Current strategies are not repeatedly deployable across independent OOS windows.
   - Too much breadth, not enough proof depth.

2. Data quality
   - Free feeds are useful but not execution-grade truth.
   - Dealer gamma and options greeks are degraded.
   - Cataloged sources are not the same as wired, monitored collectors.

3. Reproducibility
   - Dirty worktree and mixed runtime/source state.
   - Need hashes for code, data, config, and artifacts.

4. Control plane
   - Hermes queues tasks but does not yet provide full worker lease/retry/cost/rollback guarantees.
   - Launchd is operational but not cleanly self-healing.

5. Risk and governance
   - Approval model exists but needs stronger enforcement and audit trails.
   - Need "cannot widen risk" checks at code, env, and runtime levels.

6. Portfolio construction
   - Current system is lane-based, not a full portfolio manager.
   - Correlation, capital allocation, drawdown budgets, and exposure netting need to be centralized.

7. Execution
   - Demo and paper paths exist, but no institutional-grade order ledger/reconciliation.
   - Real-money execution should remain off.

8. Operations
   - Mac Mini resource pressure is material.
   - Heavy compute needs scheduling around memory/disk/swap and test load.

## Priority Next Steps

### Phase 0: Stabilize The Machine

- [ ] Clean up SSD: archive/prune runtime logs, duplicate dependencies, old snapshots.
- [ ] Add launchd drift checker.
- [ ] Add deep health scheduled during idle windows.
- [ ] Add "safe heavy job" preflight combining disk, memory, swap, locks, and launchd.
- [ ] Stop running full heavy tests in parallel on constrained hardware; split fast unit and slow research suites.

### Phase 1: Make Source Truth Clean

- [ ] Separate source changes from runtime changes.
- [ ] Review all untracked source/docs/scripts.
- [ ] Commit or discard intentionally, never leave "mystery source" in the fund repo.
- [ ] Add source-only verification.
- [ ] Add experiment artifact hashing.

### Phase 2: Narrow The Trading Wedge

- [ ] Freeze active futures research to ES/NQ and 2 to 3 strategies.
- [ ] Require 4+ OOS windows and deflated Sharpe/PBO before any promotion.
- [ ] Keep prediction lane watch-only until counterfactual/PMA calibration proves missed edge.
- [ ] Keep options/crypto/macro/compounder as research-only.

### Phase 3: Make Hermes A Real Supervisor

- [ ] Add task leases, heartbeat expiry, and failure quarantine.
- [ ] Add retry policy by task class.
- [ ] Add cost ledger per task/model/tool.
- [ ] Add founder phone-safe approve/pause/resume/complete commands.
- [ ] Make worker tasks typed contracts with input artifact, output artifact, timeout, and rollback policy.

### Phase 4: Build Fund-Grade Research Loop

- [ ] Experiment registry with dataset/code/config hashes.
- [ ] Strategy proof passports.
- [ ] No-edge and signal-decay as hard gates.
- [ ] Correlation matrix as portfolio exposure guard.
- [ ] Counterfactual learning for prediction and futures missed trades.
- [ ] PMA calibration for prediction-market thresholds.

### Phase 5: Execution Readiness

- [ ] Add order intent ledger.
- [ ] Add pre-trade risk snapshot.
- [ ] Add adapter response and reconciliation log.
- [ ] Add position reconciliation and kill-switch state to every execution artifact.
- [ ] Only after repeated green demo/paper cycles: ask for explicit founder approval to widen.

## Final Assessment

Bill/Hedge has a serious skeleton: data, strategies, prediction-market matching, futures research, launchd ops, Hermes supervision, OpenJarvis presentation, and research memory. The strongest part is the fail-closed posture: the system is currently refusing to trade because the evidence is weak. That is correct.

The weakest part is system discipline. There are too many strategies, too many untracked files, too much runtime/source mixing, and too much aspiration relative to statistically validated edge. To beat top firms over time, the system has to become narrower, more reproducible, and more brutal about negative evidence.

The next real unlock is not a new model. It is a clean, hashed experiment loop plus a Hermes supervisor that can run bounded work reliably and cheaply while refusing to widen risk. Once that is boring, the agentic fund path becomes plausible.
