#!/usr/bin/env python3
"""Review Bill/Hermes source hygiene lane packets without staging or routing.

This turns source-hygiene packets into a deterministic handoff for humans and
weaker agents. It classifies paths, highlights shadow/proxy-only files, and
keeps execution locked. It never stages, deletes, reverts, routes, funds, or
touches a broker.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "bill-source-packet-review.latest.json"

LANE_PACKET_IDS = {
    "packet-01-control-research-scaffold": "control-research",
    "packet-05-futures-strategy-lane": "futures",
    "packet-06-prediction-market-lane": "prediction-markets",
    "packet-07-dependency-review": "dependencies",
    "packet-08-sibling-worktree-selective-intake": "sibling-worktree",
}
REQUIRED_PACKET_IDS = (
    "packet-01-control-research-scaffold",
    "packet-05-futures-strategy-lane",
    "packet-06-prediction-market-lane",
)
EXECUTION_TERMS = (
    "ops/",
    "/live/",
    "execute",
    "execution",
    "fund",
    "deposit",
    "swap",
    "wire-up",
    "router",
    "route",
    "bridge",
    "pmbot",
    "gengarexecution",
)
SHADOW_TERMS = (
    "dom_proxy",
    "whale_flow",
    "kalman_pairs",
    "rolling_window",
)
DEPENDENCY_REVIEW_PATHS = {
    "package.json",
    "package-lock.json",
    "requirements.bill-alpha.txt",
}
EVIDENCE_TERMS = (
    "frontier",
    "queue",
    "triage",
    "cycle",
    "databento",
    "orderflow",
    "feature_smoke",
    "contract",
    "parser",
    "fixture",
    "validator",
    "requirements",
    "parity",
    "proof",
    "open_session",
    "coverage",
    "cost",
    "slippage",
    "quality",
    "signal_quality",
    "evidence",
    "audit",
    "handoff",
    "hygiene",
    "intake",
    "packet_review",
    "sync",
    "next_research",
    "no_edge",
    "replay",
    "walkforward",
    "label",
    "resolved",
    "cards",
    "fillability",
    "calibration",
    "microstructure",
    "clob",
    "capture",
    "mapping",
    "timestamp_dataset",
    "watch_review",
    "manual_review",
    "sensitivity",
    "target_refresh",
    "rss",
    "research_safety",
    "shadow_cron",
    "stale",
    "claim_guard",
    "vol_regime",
    "multitf",
    "risk_aware",
    "failure_rag",
    "brain_cortex",
    "brain-cycle",
    "observation",
)

PATH_REVIEW_HINTS = {
    "package.json": {
        "recommendation": "dependency-and-script-review-before-staging",
        "reason": (
            "Bill package scripts now wire many futures, prediction-market, source-hygiene, "
            "and firewall commands, and dependency changes can alter research/runtime behavior. "
            "Treat this as an alpha toolchain patch, not strategy evidence."
        ),
        "blockers": [
            "review package-lock.json together with package.json",
            "confirm every new bill:* script points to a present non-routing artifact or verifier",
            "run typecheck and relevant Node/Python suites before staging",
            "tooling success does not approve broker, funding, paper, demo, or live execution",
        ],
    },
    "package-lock.json": {
        "recommendation": "dependency-lock-review-before-staging",
        "reason": (
            "Package lock drift must be reviewed with package.json so dependency resolution "
            "changes are intentional and tied to a named alpha research use."
        ),
        "blockers": [
            "review direct ws dependency and transitive resolution changes",
            "run npm test/typecheck before staging",
            "dependency install success is not research edge evidence",
        ],
    },
    "requirements.bill-alpha.txt": {
        "recommendation": "python-alpha-tooling-review-before-staging",
        "reason": (
            "Python alpha tooling requirements affect futures/prediction research reproducibility. "
            "Keep them dependency-review only until tooling checks and focused suites pass."
        ),
        "blockers": [
            "run alpha tooling check in the active venv",
            "confirm dependencies are used by named research scripts",
            "dependency install success is not research edge evidence",
        ],
    },
    "command-center.html": {
        "recommendation": "keep-command-center-observability-after-focused-tests",
        "reason": (
            "Command Center UI renders source, risk, Topstep, prediction, and agent-governance "
            "state as founder observability. It is a dashboard/control-plane view only, not a "
            "route approval, broker, order, staging, or funding surface."
        ),
        "blockers": [
            "must keep route status blocked until daily-control and broker reconciliation gates are green",
            "must not expose buttons or flows that submit orders, fund accounts, stage files, or mutate n8n/Hermes state",
            "must label fallback/TradingView/Yahoo data as non-execution-grade unless broker-grade parity is current",
            "focused Command Center, source packet, source hygiene, and goal audit tests must pass before staging",
        ],
    },
    "command_center_server.py": {
        "recommendation": "keep-command-center-observability-after-focused-tests",
        "reason": (
            "Command Center API aggregates deterministic Bill/Hermes status artifacts for founder "
            "review. It must remain read-only telemetry and gate explanation, not a broker adapter, "
            "n8n mutator, order router, or execution authority."
        ),
        "blockers": [
            "must not write orders, broker state, n8n workflow DB rows, or route approvals",
            "must keep readyForExecution=false when goal audit, source hygiene, prediction, or Topstep gates are blocked",
            "must surface stale/fallback data rather than converting it into execution-grade truth",
            "focused Command Center, source packet, source hygiene, and goal audit tests must pass before staging",
        ],
    },
    "tests/test_command_center_server.py": {
        "recommendation": "keep-command-center-observability-after-focused-tests",
        "reason": (
            "Command Center tests validate the founder cockpit contracts and blocker actions. "
            "They protect read-only telemetry semantics and do not authorize route, paper, demo, "
            "broker, staging, or live execution."
        ),
        "blockers": [
            "tests must assert blocked route posture and read-only/no-order semantics",
            "tests must cover source-clearance runway and prediction gate freshness without clearing them",
            "green tests do not approve broker use, funding, staging, paper, demo, or live execution",
        ],
    },
    "scripts/premarket_risk_brief.py": {
        "recommendation": "keep-research-premarket-risk-brief-after-focused-tests",
        "reason": (
            "Premarket risk brief combines existing daily-plan, source-hygiene, Topstep safety, "
            "data freshness, signal-quality, and research artifacts into a fail-closed human "
            "risk read. It does not fetch live data, touch brokers, route orders, size orders "
            "for execution, fund accounts, or grant route approval."
        ),
        "blockers": [
            "must keep NO_TRADE_ALGO when daily plan, broker reconciliation, source hygiene, or Topstep session safety is blocked",
            "strategy candidates must remain watch-only and cannot override the daily plan",
            "must keep researchOnly=true, readyForExecution=false, writesOrders=false, touchesBroker=false, and movesFunds=false",
            "focused premarket risk brief, source-intake, source-hygiene, packet-review, and goal-audit tests must pass before staging",
        ],
    },
    "tests/test_premarket_risk_brief.py": {
        "recommendation": "keep-research-premarket-risk-brief-after-focused-tests",
        "reason": (
            "Premarket risk brief tests assert blocked control state forces NO_TRADE_ALGO, "
            "zero algo contracts, watch-only strategy use, and read-only/no-order semantics."
        ),
        "blockers": [
            "must be reviewed with scripts/premarket_risk_brief.py",
            "test pass is source hygiene evidence only, not futures demo, broker, route, paper, funding, or live approval",
        ],
    },
    "scripts/topstep_market_data_smoke.py": {
        "recommendation": "keep-research-topstep-readonly-market-data-after-focused-tests",
        "reason": (
            "Topstep market-data smoke authenticates only under locked env flags and reads "
            "ProjectX/TopstepX contract and historical-bar endpoints for broker-current bar "
            "evidence. It touches the broker API in read-only market-data mode and must not "
            "be treated as execution-grade permission."
        ),
        "blockers": [
            "must require RH_TOPSTEP_READ_ONLY=true, BILL_ENABLE_FUTURES_DEMO_EXECUTION=false, and RH_LIVE_EXECUTION_ENABLED=false",
            "must refuse broker touch while Topstep session safety is paused unless the operator explicitly overrides a proof window",
            "must never call order, modify, cancel, account-funding, or route endpoints",
            "must keep researchOnly=true, readyForExecution=false, writesOrders=false, placesOrders=false, modifiesOrders=false, and cancelsOrders=false",
        ],
    },
    "tests/test_topstep_market_data_smoke.py": {
        "recommendation": "keep-research-topstep-readonly-market-data-after-focused-tests",
        "reason": (
            "Topstep market-data smoke tests verify read-only locks, session-safety pauses, "
            "no-login safety blocks, and no-order metadata before the broker-current bar "
            "proof can be used as research evidence."
        ),
        "blockers": [
            "must be reviewed with scripts/topstep_market_data_smoke.py",
            "test pass is source hygiene evidence only, not Topstep route, demo expansion, broker, or live approval",
        ],
    },
    "scripts/topstep_readonly_bar_archive.py": {
        "recommendation": "keep-research-topstep-readonly-bar-archive-after-focused-tests",
        "reason": (
            "Topstep read-only bar archive accumulates broker-relevant NQ/MNQ bar evidence "
            "over time using the same locked market-data helper. It can improve research "
            "depth and parity evidence, but it is not a broker feed adapter or execution gate."
        ),
        "blockers": [
            "must inherit the Topstep market-data smoke safety blockers before any login",
            "archive writes must stay local research CSV writes only and never write route/order state",
            "must not treat session-count depth as execution-grade realtime data, DOM, OOS clearance, source hygiene clearance, or daily route approval",
            "must keep researchOnly=true, readyForExecution=false, readyForDemoExpansion=false, writesOrders=false, placesOrders=false, modifiesOrders=false, and cancelsOrders=false",
        ],
    },
    "tests/test_topstep_readonly_bar_archive.py": {
        "recommendation": "keep-research-topstep-readonly-bar-archive-after-focused-tests",
        "reason": (
            "Topstep read-only archive tests verify dedupe, session-depth accounting, no-login "
            "safety blocking, and no-order metadata for the broker-current bar archive."
        ),
        "blockers": [
            "must be reviewed with scripts/topstep_readonly_bar_archive.py",
            "test pass is source hygiene evidence only, not current-session data proof, Topstep demo expansion, or live approval",
        ],
    },
    "tests/ollamaAdapter.test.ts": {
        "recommendation": "keep-research-llm-adapter-tests-after-node-suite",
        "reason": (
            "Ollama adapter tests mock fetch to validate local LLM request/response parsing, "
            "defaults, timeout config, and JSON error handling. They support research tooling "
            "quality, not signal, broker, route, paper, demo, or live execution authority."
        ),
        "blockers": [
            "must keep network calls mocked in tests",
            "must not grant LLM output route, order, sizing, funding, or broker authority",
            "must remain separate from deterministic daily-plan and execution gates",
        ],
    },
    "ops/mac-mini/scripts/brain-cycle.sh": {
        "recommendation": "keep-research-brain-cycle-advisory-only-after-diff-review",
        "reason": (
            "Brain cycle wrapper runs brain_cortex.py with --advisory-only. It can refresh "
            "research/control state for Hermes, but must not become a motor, broker, route, "
            "funding, sizing, paper, demo, or live execution path."
        ),
        "blockers": [
            "must keep --advisory-only",
            "must not call master_bridge, signal_router, broker adapters, funding scripts, or order submission",
            "must remain linked as control-plane research context only",
            "operator approval still required before staging",
        ],
    },
    "scripts/cot_signal.py": {
        "recommendation": "keep-research-shadow-only-after-diff-review",
        "reason": (
            "Modified COT research signal now prefers the official CFTC positioning intake "
            "and emits explicit no-order/no-broker metadata. It is useful as delayed weekly "
            "regime context, not as an intraday Topstep route, confirmation, or sizing input."
        ),
        "blockers": [
            "weekly delayed positioning data only",
            "modified z-score direction logic needs review",
            "must pass CFTC positioning ingest and futures evidence triage",
            "no route, confirmation, or sizing promotion artifact",
        ],
    },
    "scripts/dom_edge_bridge.py": {
        "recommendation": "keep-research-shadow-only-after-diff-review",
        "reason": (
            "DOM edge bridge converts the OHLCV DOM proxy into the legacy dom_micro_edges.json "
            "shape consumed by TypeScript. It is a diagnostic compatibility bridge only and "
            "emits explicit proxy-only/no-order metadata."
        ),
        "blockers": [
            "OHLCV proxy is not true DOM, depth, tape, or broker execution evidence",
            "must keep researchOnly=true, proxyOnly=true, writesOrders=false, and touchesBroker=false",
            "must not become a master_bridge, signal_router, sizing, route, or order path",
            "source proxy and canonical edge artifacts must remain linked by provenance",
        ],
    },
    "scripts/donchian_breakout.py": {
        "recommendation": "keep-research-shadow-only-after-diff-review",
        "reason": (
            "Modified Donchian output now writes symbol-specific research state and explicit "
            "no-order metadata. Keep it as a diagnostic strategy candidate until independent "
            "OOS, cost, and bracket replay evidence exists."
        ),
        "blockers": [
            "legacy breakout signal must not feed master_bridge directly",
            "requires purged OOS or walk-forward evidence",
            "requires cost/slippage stress and Topstep bracket replay artifact",
            "symbol-specific state consumers need diff review",
        ],
    },
    "scripts/ichimoku_full_system.py": {
        "recommendation": "keep-research-shadow-only-after-diff-review",
        "reason": (
            "Modified Ichimoku output now writes symbol-specific research state and explicit "
            "no-order metadata. Treat it as a trend-context candidate, not an execution approval."
        ),
        "blockers": [
            "legacy trend signal must not feed master_bridge directly",
            "requires purged OOS or walk-forward evidence",
            "requires cost/slippage stress and Topstep bracket replay artifact",
            "symbol-specific state consumers need diff review",
        ],
    },
    "scripts/noise_stepforward_analysis.py": {
        "recommendation": "keep-research-evidence-only-after-diff-review",
        "reason": (
            "Modified noise and step-forward analysis improves CLI/state-dir control and empty-row "
            "handling. Use it to rank regimes and research windows, not to approve a trade route."
        ),
        "blockers": [
            "analysis output is evidence context only",
            "state-dir override and row filtering need diff review",
            "must be tied to futures evidence triage or alpha frontier queue before promotion",
            "no direct broker, bridge, or sizing integration allowed",
        ],
    },
    "scripts/noise_area_scalp.py": {
        "recommendation": "keep-research-evidence-only-after-noise-area-safety-tests",
        "reason": (
            "Noise Area scalp is a research-only intraday futures candidate. Stale breakouts "
            "are now recorded as raw research reads while the public signal fields stay HOLD, "
            "with explicit no-order/no-broker metadata."
        ),
        "blockers": [
            "stale data must suppress entry_signal and direction",
            "requires OOS, walk-forward, cost/slippage, and bracket replay before promotion",
            "must keep researchOnly=true, writesOrders=false, touchesBroker=false",
            "focused noise-area safety tests must pass before staging",
        ],
    },
    "scripts/probe-60m-signals.ts": {
        "recommendation": "keep-research-evidence-only-after-60m-probe-review",
        "reason": (
            "60m signal probe evaluates existing GOLD strategy classes against normalized CSVs "
            "and prints research-only diagnostics. It must not become a bridge input or route "
            "approval source."
        ),
        "blockers": [
            "probe output must keep readyForExecution=false and writesOrders=false",
            "CSV latest bar freshness must be checked by data gates before any demo discussion",
            "requires OOS/walk-forward and cost/slippage evidence, not point-in-time signals",
            "focused TypeScript probe run must pass before staging",
        ],
    },
    "scripts/qrs_session_bias.py": {
        "recommendation": "keep-research-evidence-only-after-qrs-safety-tests",
        "reason": (
            "QRS/RSRS session bias is a research-only futures context signal. Stale bullish or "
            "bearish reads are suppressed to neutral while preserved as raw research diagnostics."
        ),
        "blockers": [
            "stale data must suppress directional bias to neutral",
            "requires OOS/walk-forward and cost/slippage evidence before any promotion",
            "must keep researchOnly=true, writesOrders=false, touchesBroker=false",
            "focused QRS safety tests must pass before staging",
        ],
    },
    "scripts/refresh_futures_research_data.py": {
        "recommendation": "keep-research-evidence-only-after-refresh-tests",
        "reason": (
            "Futures research data refresh rebuilds Yahoo/yfinance CSVs and provenance only. "
            "It is not execution-grade realtime data and must not clear broker/current parity."
        ),
        "blockers": [
            "incomplete symbol sets must not overwrite all-market CSVs",
            "Yahoo/yfinance bars are research data, not execution-grade realtime",
            "must keep readyForExecution=false, writesOrders=false, touchesBroker=false",
            "focused refresh tests must pass before staging",
        ],
    },
    "scripts/vol_noise_scalp.py": {
        "recommendation": "keep-research-evidence-only-after-vol-noise-safety-tests",
        "reason": (
            "Vol-targeted Noise Area scalp is a research-only backtest/sweep candidate. "
            "Its state output now uses canonical repo state and explicit no-order/no-broker metadata."
        ),
        "blockers": [
            "research Yahoo/local CSV bars are not execution-grade realtime data",
            "backtest signals must not be consumed by bridge, router, or sizing code",
            "requires OOS/walk-forward, cost/slippage, and bracket replay before promotion",
            "focused vol-noise safety tests must pass before staging",
        ],
    },
    "scripts/session_trader.py": {
        "recommendation": "keep-research-shadow-only-after-diff-review",
        "reason": (
            "Modified session helper fixes New York timezone handling and disables hardcoded price "
            "fallbacks when execution-grade NQ data is missing. Keep it as session context unless "
            "fresh data parity and route firewalls prove otherwise."
        ),
        "blockers": [
            "script name and session logic are execution-adjacent",
            "requires fresh NQ data parity proof",
            "requires route/firewall tests before any bridge consumer is allowed",
            "must keep no-trade behavior when recent data is insufficient",
        ],
    },
    "backtrader_verify.py": {
        "recommendation": "retire-or-replace-with-backtrader-research-loop",
        "reason": (
            "Ad-hoc Backtrader demo with hardcoded local paths and toy SMA/RSI examples; "
            "use scripts/backtrader_research_loop.py or the futures replay harness for evidence."
        ),
        "blockers": [
            "no purged OOS split",
            "no bracket/OCO replay artifact",
            "no JSON state output",
            "hardcoded absolute data paths",
        ],
    },
    "docs/TOPSTEP_CLOSED_LOOP_FRAMEWORK_PLAN_2026_05_26.md": {
        "recommendation": "keep-as-historical-reference-only",
        "reason": (
            "Useful dated plan, but current truth must come from BILL-CONTROL-HUB, "
            "daily plan, goal audit, broker monitor, and clearance artifacts."
        ),
        "blockers": [
            "dated 2026-05-26 plan",
            "contains build-next items that may now be superseded",
            "not a current route approval source",
        ],
    },
    "scripts/backtrader_research_loop.py": {
        "recommendation": "keep-research-evidence-only-after-backtrader-and-source-tests",
        "reason": (
            "Research-only Backtrader harness for fixed futures strategy sweeps. It writes "
            "state/CSV evidence under .rumbling-hedge, uses simulated orders only inside "
            "Backtrader, and has no broker credentials or route authority."
        ),
        "blockers": [
            "full-sample Backtrader results are not sufficient for promotion",
            "requires purged OOS, walk-forward, cost/slippage, data freshness, and bracket replay evidence",
            "must remain researchOnly=true, writesOrders=false, touchesBroker=false",
            "focused Backtrader/source packet tests must pass before staging",
        ],
    },
    "scripts/cftc_tff_positioning_ingest.py": {
        "recommendation": "keep-research-evidence-only-after-cftc-ingest-tests",
        "reason": (
            "Read-only CFTC TFF positioning intake for weekly regime context. It fetches "
            "public CFTC data and writes research state/CSV artifacts; positioning cannot "
            "be used as an intraday route, confirmation, or trade directive."
        ),
        "blockers": [
            "CFTC data is delayed weekly context only",
            "missing or stale core markets must block freshness",
            "must remain researchOnly=true, writesOrders=false, touchesBroker=false",
            "focused CFTC ingest tests must pass before staging",
        ],
    },
    "scripts/cot_regime_filter_research.py": {
        "recommendation": "keep-research-evidence-only-after-cot-filter-tests",
        "reason": (
            "Research-only replay that changes one variable: adding a delayed weekly COT "
            "regime gate to fixed Backtrader strategy families. It can reject or retain "
            "a hypothesis, but it cannot approve demo/live execution."
        ),
        "blockers": [
            "COT filter results need OOS and cost/slippage confirmation",
            "must use release lag to avoid lookahead",
            "must remain researchOnly=true, writesOrders=false, touchesBroker=false",
            "focused COT regime filter tests must pass before staging",
        ],
    },
    "scripts/prediction_event_mapping_refinement.py": {
        "recommendation": "keep-research-mapping-gate-after-focused-tests",
        "reason": (
            "Prediction event mapping refinement now preserves mixed macro/geopolitical "
            "headline families and emits specificity blockers. It is a research gate for "
            "token-specific CLOB capture, not a paper/live signal."
        ),
        "blockers": [
            "must pass prediction event mapping/refinement focused tests",
            "must remain readyForPaper=false and readyForExecution=false",
            "mapping blocker can only be cleared by forward capture and no-lookahead replay evidence",
            "no funding, paper, broker, or route authority",
        ],
    },
    "tests/test_prediction_event_mapping_refinement.py": {
        "recommendation": "keep-research-mapping-gate-after-focused-tests",
        "reason": (
            "Mapping-refinement tests verify ambiguous headline fanout remains blocked and "
            "public capture leads cannot override clean event/market mapping requirements."
        ),
        "blockers": [
            "must be reviewed with scripts/prediction_event_mapping_refinement.py",
            "test pass is source hygiene evidence only, not mapping clearance or paper approval",
        ],
    },
    "scripts/prediction_event_capture_cycle.py": {
        "recommendation": "keep-research-capture-orchestration-after-focused-tests",
        "reason": (
            "Prediction event capture cycle surfaces token-specific target exclusions and "
            "runs public CLOB capture only when explicitly requested. It must remain a "
            "research-only capture/orchestration artifact."
        ),
        "blockers": [
            "must keep writesOrders=false and touchesBroker=false",
            "must not promote stale or ambiguous event windows to paper",
            "requires no-lookahead replay, fillability, and resolved-label review before paper discussion",
        ],
    },
    "tests/test_prediction_event_capture_cycle.py": {
        "recommendation": "keep-research-capture-orchestration-after-focused-tests",
        "reason": (
            "Capture-cycle tests verify bounded public CLOB recording stays research-only "
            "and that live-quality/fillability failures block paper promotion."
        ),
        "blockers": [
            "must be reviewed with scripts/prediction_event_capture_cycle.py",
            "test pass is source hygiene evidence only, not paper, funding, broker, demo, or live approval",
        ],
    },
    "scripts/prediction_event_lag_sensitivity.py": {
        "recommendation": "keep-research-event-lag-sensitivity-after-focused-tests",
        "reason": (
            "Event-lag sensitivity searches bounded post-news windows and watch scenarios. "
            "It can find manual-review candidates, but cannot create paper evidence without "
            "clean mapping, no-lookahead replay, resolved labels, and fillable CLOB capture."
        ),
        "blockers": [
            "watchReady or repriced windows must not imply readyForPaper",
            "must keep readyForExecution=false and writesOrders=false",
            "requires manual review and paper-promotion gate clearance before any paper discussion",
        ],
    },
    "tests/test_prediction_event_lag_sensitivity.py": {
        "recommendation": "keep-research-event-lag-sensitivity-after-focused-tests",
        "reason": (
            "Sensitivity tests keep event-lag watch scenarios separate from paper-grade "
            "evidence and preserve the no-execution contract."
        ),
        "blockers": [
            "must be reviewed with scripts/prediction_event_lag_sensitivity.py",
            "test pass is source hygiene evidence only, not event-trading approval",
        ],
    },
    "scripts/prediction_event_lag_watch_review.py": {
        "recommendation": "keep-research-event-lag-watch-review-after-focused-tests",
        "reason": (
            "Event-lag watch review prepares human-readable watch windows. It is a research "
            "filter between sensitivity and manual review, not a signal or paper approval."
        ),
        "blockers": [
            "manual-review-required blockers must remain visible",
            "watch windows must not bypass mapping, resolved-label, spread, fee, or fillability gates",
            "must keep readyForPaper=false and readyForExecution=false",
        ],
    },
    "tests/test_prediction_event_lag_watch_review.py": {
        "recommendation": "keep-research-event-lag-watch-review-after-focused-tests",
        "reason": (
            "Watch-review tests verify candidate windows remain research-only until manual "
            "review and paper-promotion gates clear."
        ),
        "blockers": [
            "must be reviewed with scripts/prediction_event_lag_watch_review.py",
            "test pass is source hygiene evidence only, not paper readiness",
        ],
    },
    "scripts/prediction_event_lag_manual_review.py": {
        "recommendation": "keep-research-manual-event-lag-review-after-focused-tests",
        "reason": (
            "Prediction event manual review converts event-lag replay/capture artifacts into "
            "human-reviewable windows and now separates observed public CLOB capture from "
            "paper-grade no-lookahead evidence. It is evidence triage only, not a watch, "
            "paper, funding, broker, demo, live, or execution approval source."
        ),
        "blockers": [
            "must distinguish forwardCaptureObserved from forwardCaptureEvidencePresent",
            "observed public CLOB capture without fillability must stay paper-blocked",
            "must keep readyForPaper=false and readyForExecution=false unless deterministic evidence gates clear",
            "manual review, capture cycle, paper gate, next-action, Obsidian sync, and goal audit tests must pass before staging",
        ],
    },
    "tests/test_prediction_event_lag_manual_review.py": {
        "recommendation": "keep-research-manual-event-lag-review-after-focused-tests",
        "reason": (
            "Manual event-lag review tests verify observed forward capture cannot be confused "
            "with fillable or paper-grade evidence, and that blocker language remains precise "
            "for future agents."
        ),
        "blockers": [
            "must be reviewed with scripts/prediction_event_lag_manual_review.py",
            "test pass is source hygiene evidence only, not prediction paper or execution approval",
        ],
    },
    "scripts/prediction_event_lag_replay.py": {
        "recommendation": "keep-research-event-lag-replay-after-focused-tests",
        "reason": (
            "Event-lag replay measures post-news repricing against timestamped event data. "
            "It must remain no-lookahead research evidence and cannot promote incomplete or "
            "ambiguous event windows to paper."
        ),
        "blockers": [
            "completeEventCount must be required before paper evidence",
            "must not treat stale pre-event quotes as no-lookahead proof",
            "must keep readyForPaper=false and readyForExecution=false until downstream gates clear",
        ],
    },
    "tests/test_prediction_event_lag_replay.py": {
        "recommendation": "keep-research-event-lag-replay-after-focused-tests",
        "reason": (
            "Event-lag replay tests verify no-lookahead and completeness blockers remain "
            "visible before sensitivity, manual review, and paper gates consume the replay."
        ),
        "blockers": [
            "must be reviewed with scripts/prediction_event_lag_replay.py",
            "test pass is source hygiene evidence only, not paper evidence",
        ],
    },
    "scripts/prediction_evidence_triage.py": {
        "recommendation": "keep-research-prediction-evidence-triage-after-focused-tests",
        "reason": (
            "Prediction evidence triage summarizes macro, event-lag, CLOB, label, and "
            "fillability artifacts. It can rank research lanes, but must not convert partial "
            "evidence into paper, funding, or execution permission."
        ),
        "blockers": [
            "must preserve paper-promotion blockers from source artifacts",
            "triage ranking must not override no-edge memory",
            "must keep readyForPaper=false and readyForExecution=false unless deterministic gates clear",
        ],
    },
    "tests/test_prediction_evidence_triage.py": {
        "recommendation": "keep-research-prediction-evidence-triage-after-focused-tests",
        "reason": (
            "Prediction triage tests verify summary artifacts remain research-only and "
            "preserve blocker state from the underlying evidence gates."
        ),
        "blockers": [
            "must be reviewed with scripts/prediction_evidence_triage.py",
            "test pass is source hygiene evidence only, not paper or execution approval",
        ],
    },
    "scripts/polymarket_clob_recorder.mjs": {
        "recommendation": "keep-research-public-clob-recorder-after-node-tests",
        "reason": (
            "Polymarket CLOB recorder collects bounded public order-book data only. It is "
            "allowed as a research sensor, but must stay separate from signed order, funding, "
            "paper promotion, broker, demo, and live execution paths."
        ),
        "blockers": [
            "must use public/read-only endpoints only",
            "must enforce max duration, max assets, max output size, and min free disk gates",
            "recorded CLOB movement is not paper evidence without fillability, resolved labels, and no-lookahead replay",
        ],
    },
    "tests/polymarketClobRecorder.test.ts": {
        "recommendation": "keep-research-public-clob-recorder-after-node-tests",
        "reason": (
            "Recorder tests verify the public CLOB capture path remains bounded and separate "
            "from any order-writing or funding behavior."
        ),
        "blockers": [
            "must be reviewed with scripts/polymarket_clob_recorder.mjs",
            "test pass is source hygiene evidence only, not paper, funding, or execution approval",
        ],
    },
    "scripts/polymarket_clob_persistence_lab.mjs": {
        "recommendation": "keep-research-clob-persistence-lab-after-node-tests",
        "reason": (
            "CLOB persistence lab analyzes recorded public book movement. Current fixed "
            "CLOB forms are rejected in no-edge memory, so this lab must only test genuinely "
            "new feature families with resolved-label and fillability gates."
        ),
        "blockers": [
            "must not rerun rejected fixed CLOB forms with looser thresholds",
            "must preserve no-edge ledger blockers",
            "must keep writesOrders=false and touchesBroker=false",
        ],
    },
    "tests/polymarketClobPersistence.test.ts": {
        "recommendation": "keep-research-clob-persistence-lab-after-node-tests",
        "reason": (
            "CLOB persistence tests verify persistence analysis stays bounded and cannot "
            "promote rejected fixed-form features."
        ),
        "blockers": [
            "must be reviewed with scripts/polymarket_clob_persistence_lab.mjs",
            "test pass is source hygiene evidence only, not paper evidence",
        ],
    },
    "scripts/prediction_macro_rates_requirements.py": {
        "recommendation": "keep-research-macro-rates-requirements-after-focused-tests",
        "reason": (
            "Macro-rates requirements gate Kalshi/Polymarket macro market research. They "
            "can clear parser prerequisites, but paper still requires source-specific resolved "
            "labels, comparable samples, fillability, fees, and spread stress."
        ),
        "blockers": [
            "requirements cleared must not imply cross-source replay cleared",
            "must keep macro/rates paper blockers visible",
            "must keep readyForPaper=false and readyForExecution=false until downstream gates clear",
        ],
    },
    "tests/test_prediction_macro_rates_requirements.py": {
        "recommendation": "keep-research-macro-rates-requirements-after-focused-tests",
        "reason": (
            "Macro-rates requirements tests verify prerequisites are separate from paper or "
            "execution approval."
        ),
        "blockers": [
            "must be reviewed with scripts/prediction_macro_rates_requirements.py",
            "test pass is source hygiene evidence only, not macro/rates paper readiness",
        ],
    },
    "scripts/prediction_macro_rates_cross_source_replay.py": {
        "recommendation": "keep-research-macro-rates-cross-source-replay-after-focused-tests",
        "reason": (
            "Macro-rates cross-source replay compares source/parser variants under fees and "
            "sample-size constraints. It is a candidate filter only and cannot paper-trade "
            "small or incomparable samples."
        ),
        "blockers": [
            "too-few-source-specific-sample-rows must block watch/paper promotion",
            "fee-stressed replay must remain separate from gross parser reads",
            "must keep readyForPaper=false and readyForExecution=false unless sample and fillability gates clear",
        ],
    },
    "tests/test_prediction_macro_rates_cross_source_replay.py": {
        "recommendation": "keep-research-macro-rates-cross-source-replay-after-focused-tests",
        "reason": (
            "Cross-source replay tests verify fee/sample blockers stay active before any "
            "macro-rates paper discussion."
        ),
        "blockers": [
            "must be reviewed with scripts/prediction_macro_rates_cross_source_replay.py",
            "test pass is source hygiene evidence only, not paper readiness",
        ],
    },
    "scripts/prediction_macro_rates_parser_fixture.py": {
        "recommendation": "keep-research-macro-rates-parser-fixture-after-focused-tests",
        "reason": (
            "Macro-rates parser fixture is a source-normalization helper. Parser extraction "
            "quality can seed replay, but cannot become a signal without resolved labels, "
            "fillability, fee stress, and cross-source coverage."
        ),
        "blockers": [
            "parser fixture pass must not imply trading edge",
            "must not loosen settlement horizon or source parsing to create candidates",
            "must keep writesOrders=false and touchesBroker=false",
        ],
    },
    "tests/test_prediction_macro_rates_parser_fixture.py": {
        "recommendation": "keep-research-macro-rates-parser-fixture-after-focused-tests",
        "reason": (
            "Parser fixture tests verify market-line extraction remains reproducible and "
            "separate from strategy approval."
        ),
        "blockers": [
            "must be reviewed with scripts/prediction_macro_rates_parser_fixture.py",
            "test pass is source hygiene evidence only, not macro strategy evidence",
        ],
    },
    "scripts/bill_next_research_actions.py": {
        "recommendation": "keep-research-queue-after-control-tests",
        "reason": (
            "Next research actions now prioritize the prediction mapping repair when ambiguous "
            "mapping blocks token-specific capture and preserves precise forward-capture blockers. "
            "Queue priority is not execution approval."
        ),
        "blockers": [
            "all queued actions must remain researchOnly=true",
            "all queued actions must keep writesOrders=false and touchesBroker=false",
            "completed manual event-lag review must move to mapping repair, not repeat stale manual review",
            "when prediction targetCount=0, use standing forward CLOB capture instead of target-specific capture",
            "must preserve forward-public-clob-capture-observed-but-not-paper-grade when applicable",
            "priority changes must be validated against goal completion and Obsidian sync tests",
        ],
    },
    "tests/test_bill_next_research_actions.py": {
        "recommendation": "keep-research-queue-after-control-tests",
        "reason": (
            "Next research action tests keep futures and prediction-market queues locked to "
            "research-only decisions while checking that precise blocker language flows from "
            "manual review into the daily action list."
        ),
        "blockers": [
            "must be reviewed with scripts/bill_next_research_actions.py",
            "test pass is source hygiene evidence only, not broker, paper, demo, live, or funding approval",
        ],
    },
    "scripts/alpha_research_direction_audit.py": {
        "recommendation": "keep-research-direction-after-focused-tests",
        "reason": (
            "Alpha research direction audit ranks futures and prediction-market research lanes, "
            "makes retire/quarantine decisions explicit, and emits readyForResearchLoop without "
            "granting execution, paper, demo, funding, or broker authority."
        ),
        "blockers": [
            "must keep readyForExecution=false and readyForDemoExpansion=false",
            "must not convert YT, paper, or web labels into execution evidence",
            "must keep rejected fixed forms in retire/quarantine lanes",
            "must pass alpha direction, current alpha watch, next-action, and goal audit tests before staging",
        ],
    },
    "tests/test_alpha_research_direction_audit.py": {
        "recommendation": "keep-research-direction-after-focused-tests",
        "reason": (
            "Alpha research direction tests verify lane ranking, retirement, and unsafe-command "
            "checks stay research-only while preserving execution locks."
        ),
        "blockers": [
            "must be reviewed with scripts/alpha_research_direction_audit.py",
            "test pass is source hygiene evidence only, not broker, paper, demo, live, or funding approval",
        ],
    },
    "scripts/current_alpha_watch.py": {
        "recommendation": "keep-research-watch-after-alpha-direction-tests",
        "reason": (
            "Current alpha watch is the daily Obsidian-facing synthesis of futures and "
            "prediction-market research lanes. It surfaces blockers and one-variable tests, "
            "but stays research-only and cannot approve orders."
        ),
        "blockers": [
            "must keep writesOrders=false and touchesBroker=false",
            "must surface goal blockers and fillable-live-book count without treating them as clearance",
            "must keep readyForExecution=false even when readyForResearchLoop=true",
            "must pass current alpha watch and Obsidian sync tests before staging",
        ],
    },
    "tests/test_current_alpha_watch.py": {
        "recommendation": "keep-research-watch-after-alpha-direction-tests",
        "reason": (
            "Current alpha watch tests verify the daily watch remains research-only, preserves "
            "zero fillable-live-book blockers, uses current dates, and does not imply execution."
        ),
        "blockers": [
            "must be reviewed with scripts/current_alpha_watch.py",
            "test pass is source hygiene evidence only, not execution approval",
        ],
    },
    "scripts/prediction_event_paper_promotion_gate.py": {
        "recommendation": "keep-research-paper-gate-after-prediction-gate-tests",
        "reason": (
            "Prediction event paper-promotion gate is a read-only evidence combiner. It now "
            "distinguishes safe fillable public CLOB capture from paper-grade no-lookahead "
            "repriced event-window evidence, so research progress cannot be mistaken for "
            "paper, funding, demo, live, or broker approval."
        ),
        "blockers": [
            "must keep readyForExecution=false, writesOrders=false, touchesBroker=false, and movesFunds=false",
            "must keep fillable live books separate from paper-grade no-lookahead repriced windows",
            "must require resolved labels, clean mapping, and post-spread CLOB edge before paper review",
            "prediction paper-promotion gate and capture-cycle tests must pass before staging",
        ],
    },
    "tests/test_prediction_event_paper_promotion_gate.py": {
        "recommendation": "keep-research-paper-gate-after-prediction-gate-tests",
        "reason": (
            "Prediction paper-promotion gate tests verify the gate remains read-only, can "
            "surface fillable capture without paper readiness, and only reaches paper-review "
            "status when every deterministic evidence subgate passes."
        ),
        "blockers": [
            "must be reviewed with scripts/prediction_event_paper_promotion_gate.py",
            "test pass is source hygiene evidence only, not execution or paper approval",
        ],
    },
    "scripts/alpha_frontier_queue.py": {
        "recommendation": "keep-research-frontier-after-no-edge-and-queue-tests",
        "reason": (
            "Alpha frontier queue ranks futures and prediction-market hypotheses after reading "
            "no-edge memory, source catalogs, and control artifacts. It may steer research, but "
            "it must not requeue rejected fixed forms or imply paper/demo/live readiness."
        ),
        "blockers": [
            "must not rerun CLOB fixed forms already rejected in prediction no-edge memory",
            "exhausted CLOB fixed-form state must route to labels, longer bounded capture, or genuinely new features",
            "frontier priority is not execution, paper, demo, funding, or broker approval",
            "alpha frontier, next-action, source-intake, Obsidian sync, and goal audit tests must pass before staging",
        ],
    },
    "scripts/bill_source_intake_manifest.py": {
        "recommendation": "keep-source-visibility-after-intake-and-hygiene-tests",
        "reason": (
            "Source intake manifest makes dirty-tree state visible and classifies validated "
            "research scaffolds versus quarantined execution paths. It can reduce review fog, "
            "but it cannot clear source hygiene or authorize staging by itself."
        ),
        "blockers": [
            "validated-research-scaffold classification requires focused validation command coverage",
            "execution-live dirty paths must remain quarantined even when firewalls pass",
            "sourceClean must remain false while dirty source, execution-live files, or sibling worktrees remain",
            "source intake, source hygiene, packet review, clearance handoff, and goal audit tests must pass before staging",
        ],
    },
    "scripts/bill_source_packet_review.py": {
        "recommendation": "keep-source-packet-review-after-focused-tests",
        "reason": (
            "Source packet review turns source-hygiene lanes into human/agent handoff rows with "
            "review recommendations and blockers. It is a review map only; it never stages, "
            "deletes, routes, funds, or approves trading."
        ),
        "blockers": [
            "review recommendations must preserve readyForExecution=false and safeToStageAutomatically=false",
            "packet review must not hide missing required packets",
            "manual clearance proposals are proposal-only and must not stage files automatically",
            "packet review, source hygiene, clearance handoff, Obsidian sync, and goal audit tests must pass before staging",
        ],
    },
    "scripts/research_seed_triage.py": {
        "recommendation": "keep-research-seed-triage-after-focused-tests",
        "reason": (
            "Research seed triage separates web, paper, and YouTube source-card labels from "
            "execution evidence. It can surface gold/candidate material for one-variable "
            "research, but must keep promoted/executable seed counts at zero until deterministic "
            "OOS, data-quality, cost, and promotion gates clear."
        ),
        "blockers": [
            "YouTube, paper, and web labels are source provenance, not strategy edge evidence",
            "must keep executableSeeds at zero unless promotion gates explicitly clear",
            "durable source cards are hypothesis-only until retested in the futures/prediction research lanes",
            "must keep writesOrders=false, touchesBroker=false, and readyForExecution=false",
            "focused research seed triage, Obsidian sync, and goal audit tests must pass before staging",
        ],
    },
    "tests/test_research_seed_triage.py": {
        "recommendation": "keep-research-seed-triage-after-focused-tests",
        "reason": (
            "Research seed triage tests verify queued YouTube/source-card material stays "
            "visible as hypothesis intake while executable and candidate-retest counts remain "
            "blocked without promotion evidence."
        ),
        "blockers": [
            "must be reviewed with scripts/research_seed_triage.py",
            "test pass is source hygiene evidence only, not futures demo, prediction paper, or execution approval",
        ],
    },
    "scripts/sync_bill_obsidian.py": {
        "recommendation": "keep-control-memory-sync-after-focused-tests",
        "reason": (
            "Obsidian sync exposes Bill/Hermes state to humans and weaker agents. It may "
            "record blockers and planned research, but must not become broker truth or route authority."
        ),
        "blockers": [
            "daily plan must continue to show no orders approved when route approval is blocked",
            "sync output must not imply demo/live/paper readiness from proxy artifacts",
            "focused Obsidian sync tests must pass before staging",
        ],
    },
    "scripts/bill_goal_completion_audit.py": {
        "recommendation": "keep-completion-guard-after-audit-tests",
        "reason": (
            "Goal completion audit is the guard that prevents effort or green helper tests from "
            "being mistaken for demo readiness. Changes here must preserve the hard blockedIds rule."
        ),
        "blockers": [
            "do not mark goalComplete while blockedIds is non-empty",
            "must map prompt requirements to concrete artifacts",
            "must keep writesOrders=false and touchesBroker=false",
            "focused goal audit tests must pass before staging",
        ],
    },
    "scripts/bill_runtime_architecture_audit.py": {
        "recommendation": "keep-runtime-architecture-audit-after-focused-tests",
        "reason": (
            "Runtime architecture audit makes the split between research, n8n/Hermes orchestration, "
            "cron, Kanban, AI-Scientist templates, and locked execution visible. It is a control-plane "
            "map only and must not mutate n8n, cron, broker, funding, route, paper, demo, or live state."
        ),
        "blockers": [
            "must keep readyForExecution=false, writesOrders=false, and touchesBroker=false",
            "must not mutate n8n DB, Hermes Kanban, cron jobs, broker adapters, or execution flags",
            "AI-Scientist checks must remain sandbox/template checks, not strategy promotion approval",
            "runtime architecture, source packet, Obsidian sync, and goal audit tests must pass before staging",
        ],
    },
    "tests/test_bill_runtime_architecture_audit.py": {
        "recommendation": "keep-runtime-architecture-audit-after-focused-tests",
        "reason": (
            "Runtime architecture audit tests verify n8n/export parity, Kanban blocked-task triage, "
            "cron validator integration, and AI-Scientist safety metadata stay visible while execution remains locked."
        ),
        "blockers": [
            "must be reviewed with scripts/bill_runtime_architecture_audit.py",
            "test pass is source hygiene evidence only, not futures demo, prediction paper, or execution approval",
        ],
    },
    "scripts/bill_fund_os_completion_audit.py": {
        "recommendation": "keep-research-fund-os-completion-audit-after-focused-tests",
        "reason": (
            "Fund OS completion audit maps the founder fund path, shadow-cron safety, and futures/prediction/copy/brokerage/options "
            "promotion ladder into a handoff. It is a readiness contract only and must not approve funding, broker access, routing, "
            "paper, demo, live, copy trading, or options expansion."
        ),
        "blockers": [
            "must keep tradingReadinessStatus blocked when evidence gates fail",
            "must preserve shadow-cron checks and validator trust review",
            "fund promotion ladder is advisory until source, data, broker, paper, and daily gates pass",
            "fund OS audit, source hygiene, Obsidian sync, and goal audit tests must pass before staging",
        ],
    },
    "tests/test_bill_fund_os_completion_audit.py": {
        "recommendation": "keep-research-fund-os-completion-audit-after-focused-tests",
        "reason": (
            "Fund OS audit tests verify shadow-cron safety, validator reconciliation, and expansion-ladder blocking so weaker agents "
            "cannot mistake the fund path for execution permission."
        ),
        "blockers": [
            "must be reviewed with scripts/bill_fund_os_completion_audit.py",
            "test pass is source hygiene evidence only, not futures demo, prediction paper, funding, brokerage, copy-trading, or options approval",
        ],
    },
    "scripts/verify_no_execution_enabled_processes.py": {
        "recommendation": "keep-research-no-execution-process-guard-after-focused-tests",
        "reason": (
            "No-execution process guard is a read-only control-plane verifier that scans running Bill/Hermes processes for "
            "unsafe execution flags. It improves clearance evidence by catching env drift; it does not route, submit, fund, "
            "or approve trades."
        ),
        "blockers": [
            "must remain process-inspection only and never kill, restart, route, fund, or mutate runtime state",
            "unsafe running-process findings must block clearance rather than promote demo/live execution",
            "must keep researchOnly=true, writesOrders=false, touchesBroker=false, and movesFunds=false",
            "focused no-execution-process, clearance, source-hygiene, and goal audit tests must pass before staging",
        ],
    },
    "tests/test_verify_no_execution_processes.py": {
        "recommendation": "keep-research-no-execution-process-guard-after-focused-tests",
        "reason": (
            "No-execution process guard tests prove unsafe process flags are detected while safe/read-only process evidence stays non-routing."
        ),
        "blockers": [
            "must be reviewed with scripts/verify_no_execution_enabled_processes.py",
            "test pass is source hygiene evidence only, not futures demo, prediction paper, broker, funding, or live approval",
        ],
    },
    "scripts/stale_strategy_claim_guard.py": {
        "recommendation": "keep-stale-claim-guard-after-focused-tests",
        "reason": (
            "Stale strategy claim guard scans Bill/Hermes markdown for superseded ready-to-trade "
            "claims so old strategy audits and chat-copied plans cannot be mistaken for current "
            "paper, demo, or live approval."
        ),
        "blockers": [
            "guard pass only means stale approval language is currently contextualized",
            "must remain researchOnly=true, writesOrders=false, touchesBroker=false",
            "must be visible in source intake, clearance evidence, goal audit, and Obsidian notes",
            "focused stale-claim, clearance, source-hygiene, and goal audit tests must pass before staging",
        ],
    },
    "tests/test_strategy_evidence_copy.py": {
        "recommendation": "keep-strategy-evidence-copy-guard-after-focused-tests",
        "reason": (
            "Strategy evidence copy tests keep old 15m/60m full-sample leaderboard language from "
            "reappearing in executable strategy source. The guard exists so weaker agents see these "
            "strategies as research-only until current OOS, walk-forward, cost, and daily gates clear."
        ),
        "blockers": [
            "must be reviewed with the 15m/60m strategy source comments it protects",
            "test pass is source hygiene evidence only, not futures demo or live readiness",
            "must stay linked to stale-claim guard, futures evidence triage, and Obsidian notes",
        ],
    },
    "scripts/prediction_no_edge_ledger.py": {
        "recommendation": "keep-research-no-edge-memory-after-focused-tests",
        "reason": (
            "Prediction no-edge ledger records rejected prediction-market hypotheses from direct "
            "CLOB edge-gate and triage artifacts so future agents do not threshold-mine stale or "
            "failed baselines. It is durable research memory only, not paper/live authority."
        ),
        "blockers": [
            "must prefer direct polymarket CLOB edge-gate evidence over stale triage summaries",
            "must keep current-form rejections research-only unless retestPassed or supersededBy is explicit",
            "must keep writesOrders=false and touchesBroker=false",
            "focused prediction no-edge ledger and queue tests must pass before staging",
        ],
    },
    "scripts/prediction_clob_microstructure_feature_audit.py": {
        "recommendation": "keep-research-clob-feature-audit-after-focused-tests",
        "reason": (
            "Prediction CLOB microstructure audit now separates raw data availability from "
            "unrejected feature readiness, using the no-edge ledger to prevent weaker agents "
            "from rerunning already rejected fixed forms."
        ),
        "blockers": [
            "must read prediction no-edge ledger before advertising a feature as ready",
            "rawDataReady must not imply readyForPaper, readyForExecution, or watch eligibility",
            "all current fixed-form rejections must keep readyFeatureCount at zero unless superseded by explicit new evidence",
            "focused CLOB audit, alpha queue, no-edge ledger, next-action, Obsidian sync, and goal audit tests must pass before staging",
        ],
    },
}

CONTROL_EVIDENCE_PATHS = {
    "ai-scientist-templates/financial_strategy/experiment.py",
    "ai-scientist-templates/financial_strategy/ideas.json",
    "ai-scientist-templates/financial_strategy/latex/fancyhdr.sty",
    "ai-scientist-templates/financial_strategy/latex/iclr2024_conference.bst",
    "ai-scientist-templates/financial_strategy/latex/iclr2024_conference.sty",
    "ai-scientist-templates/financial_strategy/latex/natbib.sty",
    "ai-scientist-templates/financial_strategy/latex/template.tex",
    "ai-scientist-templates/financial_strategy/plot.py",
    "ai-scientist-templates/financial_strategy/prompt.json",
    "ai-scientist-templates/financial_strategy/seed_ideas.json",
    "ai-scientist-templates/financial_strategy/test_run/final_info.json",
    "ai-scientist-templates/financial_strategy/test_run_15m/final_info.json",
    "ai-scientist-templates/financial_strategy/test_run_30m/final_info.json",
    "ai-scientist-templates/financial_strategy/test_run_60m/final_info.json",
    "ai-scientist-templates/financial_strategy/test_run_known_baselines/final_info.json",
    "tests/test_ai_scientist_financial_template.py",
    "ops/activate-bill-workflows.sh",
    "ops/mac-mini/bin/bill-chatgpt-frontdoor",
    "scripts/bill_execution_intake_manifest.py",
    "tests/test_bill_execution_intake_manifest.py",
    "scripts/verify_execution_quarantine.py",
    "tests/test_verify_execution_quarantine.py",
    "scripts/verify_no_execution_enabled_processes.py",
    "tests/test_verify_no_execution_processes.py",
    "tests/test_bill_package_scripts.py",
    "scripts/build_data_master_csv.py",
    "tests/test_build_data_master_csv.py",
    "scripts/topstep_daily_learning.py",
    "tests/test_topstep_daily_learning.py",
    "scripts/topstep_demo_observation_posture.py",
    "tests/test_topstep_demo_observation_posture.py",
    "tests/test_topstep_runtime_semantics.py",
    "scripts/realtime_data_preflight.py",
    "tests/test_realtime_data_preflight.py",
    "scripts/finnhub_news.py",
    "tests/test_finnhub_news.py",
    "scripts/free_data_feed_audit.py",
    "tests/test_free_data_feed_audit.py",
    "scripts/topstep_session_safety_clearance.py",
    "tests/test_topstep_session_safety_clearance.py",
    "scripts/founder_quant_cto_metaprompt.py",
    "tests/test_founder_quant_cto_metaprompt.py",
    "scripts/strategy_test_framework_status.py",
    "tests/test_strategy_test_framework_status.py",
    "scripts/cron_brain_tick.sh",
    "scripts/cron_verify_execution_quarantine.sh",
    "scripts/cron_verify_master_bridge.sh",
    "scripts/cron_verify_no_execution.sh",
    "scripts/cron_verify_topstep_demo.sh",
    "tests/test_cron_research_wrappers.py",
    "scripts/signal_quality_advisor.py",
    "tests/test_signal_quality_advisor.py",
    "scripts/signal_source_truth_audit.py",
    "tests/test_signal_source_truth_audit.py",
    "scripts/ai_screener.py",
    "tests/test_ai_screener.py",
    "scripts/futures_nq_sizing_overlay.py",
    "tests/test_futures_nq_sizing_overlay.py",
    "command-center.html",
    "command_center_server.py",
    "tests/test_command_center_server.py",
    "tests/test_futures_strategy_shadow_safety.py",
    "tests/test_cot_signal_safety.py",
    "tests/test_cftc_tff_positioning_ingest.py",
    "tests/test_cot_regime_filter_research.py",
    "tests/test_noise_area_scalp_safety.py",
    "tests/test_qrs_session_bias_safety.py",
    "tests/test_refresh_futures_research_data.py",
    "tests/test_vol_noise_scalp_safety.py",
}

FUTURES_PACKET_RESEARCH_HINT_PATHS = {
    "src/data/csv.ts",
    "src/engine/researchFabric.ts",
    "tests/research.test.ts",
    "scripts/futures_evidence_triage.py",
    "tests/test_futures_evidence_triage.py",
    "scripts/gex_backtest.py",
    "tests/test_gex_backtest.py",
    "scripts/strategy_diagnostic.py",
    "scripts/strategy_signal_diagnostic.py",
    "tests/test_strategy_diagnostic.py",
    "tests/test_strategy_signal_diagnostic.py",
    "scripts/futures_nq_historical_session_replay.py",
    "tests/test_futures_nq_historical_session_replay.py",
    "scripts/futures_nq_historical_session_walkforward.py",
    "tests/test_futures_nq_historical_session_walkforward.py",
    "scripts/futures_nq_historical_session_cost_stress.py",
    "tests/test_futures_nq_historical_session_cost_stress.py",
    "scripts/futures_nq_research_cycle.py",
    "scripts/futures_data_requirements.py",
    "tests/test_futures_data_requirements.py",
    "scripts/futures_cost_slippage_gate.py",
    "scripts/databento_orderflow_feature_smoke.py",
    "tests/test_databento_orderflow_feature_smoke.py",
    "scripts/databento_realtime_smoke.py",
    "tests/test_databento_realtime_smoke.py",
    "scripts/futures_data_quality_snapshot.py",
    "tests/test_futures_data_quality_snapshot.py",
    "scripts/futures_no_edge_ledger.py",
    "tests/test_futures_no_edge_ledger.py",
    "scripts/futures_nq_current_data_parity.py",
    "tests/test_futures_nq_current_data_parity.py",
    "scripts/data_freshness_gate.py",
    "tests/test_data_freshness_gate.py",
    "scripts/futures_nq_historical_coverage_audit.py",
    "scripts/futures_nq_session_structure_audit.py",
    "scripts/microstructure_filter.py",
    "scripts/vol_regime_oos_replay.py",
}

FUTURES_PACKET_RESEARCH_HINT = {
    "recommendation": "keep-research-futures-evidence-gate-after-focused-tests",
    "reason": (
        "Futures packet evidence files support NQ historical OOS, walk-forward, "
        "cost/slippage, data-quality, Databento/order-flow, and no-edge review. "
        "They are research gates only and cannot clear Topstep demo, routing, sizing, "
        "broker parity, or live execution."
    ),
    "blockers": [
        "historical/OOS evidence must stay separate from current broker-grade data parity",
        "Databento/order-flow smoke must not approve routing without open-session execution-grade proof",
        "cost, walk-forward, no-edge, source hygiene, broker parity, and daily route gates must remain visible",
        "must keep readyForExecution=false, writesOrders=false, and touchesBroker=false",
    ],
}


def review_hint_for_path(path: str) -> dict[str, Any]:
    hint = PATH_REVIEW_HINTS.get(path)
    if isinstance(hint, dict):
        return hint
    if path in FUTURES_PACKET_RESEARCH_HINT_PATHS:
        return FUTURES_PACKET_RESEARCH_HINT
    return {}


def default_markdown_path() -> Path:
    review_date = datetime.now(timezone.utc).date().isoformat()
    return HERMES / f"bill-source-packet-review-{review_date}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def classify_path(path: str, status: str) -> tuple[str, str]:
    lower = path.lower()
    if status == "sibling-worktree-dirty" or ":" in path:
        return "quarantine-review", "non-canonical sibling worktree path requires selective intake before staging"
    if path in CONTROL_EVIDENCE_PATHS:
        return "keep-research", "control-plane execution firewall evidence; not an execution route"
    hint = review_hint_for_path(path)
    recommendation = str(hint.get("recommendation") or "")
    if path in DEPENDENCY_REVIEW_PATHS:
        return "dependency-reviewed", "dependency/tooling path reviewed; operator approval still required before staging"
    if recommendation.startswith("keep-research-shadow-only"):
        return "shadow-only", "reviewed research shadow signal with explicit no-order metadata"
    if recommendation.startswith("keep-research-evidence-only"):
        return "keep-research", "reviewed research evidence helper with explicit no-order metadata"
    if recommendation.startswith("keep-research-"):
        return "keep-research", "reviewed research/control helper with explicit no-order metadata"
    if recommendation.startswith("retire-"):
        return "retired-reference", "reviewed retired/ad-hoc artifact; do not use as current evidence"
    if recommendation.startswith("keep-as-historical-reference-only"):
        return "historical-reference", "reviewed historical reference; not a current approval source"
    if any(term in lower for term in EXECUTION_TERMS):
        return "quarantine-review", "execution/funding/ops-like path must stay out of research lane promotion"
    if any(term in lower for term in SHADOW_TERMS):
        return "shadow-only", "diagnostic/proxy signal; useful for research review, not execution confirmation"
    if any(term in lower for term in EVIDENCE_TERMS):
        return "keep-research", "evidence, gate, label, replay, or data-quality helper"
    if status.strip() == "??":
        return "review-before-staging", "untracked research file needs explicit human review before staging"
    return "review-before-staging", "modified research path needs local diff and test review before staging"


def review_packet(packet: dict[str, Any]) -> dict[str, Any]:
    packet_id = str(packet.get("id") or "missing")
    lane = LANE_PACKET_IDS.get(packet_id, "unknown")
    footprint = packet.get("pathFootprint") if isinstance(packet.get("pathFootprint"), list) else []
    paths = packet.get("paths") if isinstance(packet.get("paths"), list) else []
    diff_summary = packet.get("diffSummary") if isinstance(packet.get("diffSummary"), dict) else {}
    manual_stage_eligible = bool(packet.get("manualStageEligible"))
    manual_stage_command = str(packet.get("manualStageCommand") or "")
    manual_stage_warning = str(packet.get("manualStageWarning") or "")
    by_path = {
        str(row.get("path")): row
        for row in footprint
        if isinstance(row, dict) and row.get("path")
    }
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for path in paths:
        path_text = str(path)
        row = by_path.get(path_text, {})
        status = str(row.get("status", "status-not-in-packet-footprint"))
        classification, reason = classify_path(path_text, status)
        hint = review_hint_for_path(path_text)
        counts[classification] = counts.get(classification, 0) + 1
        rows.append({
            "path": path_text,
            "status": status,
            "exists": row.get("exists", (ROOT / path_text).exists()),
            "trackedDiff": row.get("trackedDiff", False),
            "addedLines": row.get("addedLines", 0),
            "deletedLines": row.get("deletedLines", 0),
            "classification": classification,
            "reason": reason,
            "reviewRecommendation": hint.get("recommendation"),
            "reviewReason": hint.get("reason"),
            "reviewBlockers": hint.get("blockers", []),
        })
    unsafe_count = counts.get("quarantine-review", 0)
    commands = packet.get("commands") if isinstance(packet.get("commands"), list) else []
    return {
        "id": packet_id,
        "lane": lane,
        "title": packet.get("title", "missing"),
        "decision": "manual-review-only" if unsafe_count == 0 else "quarantine-review-required",
        "packetDecision": packet.get("decision", "missing"),
        "pathCount": len(rows),
        "sourcePacketPathCount": packet.get("pathCount"),
        "diffSummary": diff_summary,
        "classificationCounts": counts,
        "rows": rows,
        "firstCommand": commands[0] if commands else None,
        "commands": commands,
        "manualStageEligible": manual_stage_eligible,
        "manualStageCommand": manual_stage_command,
        "manualStageWarning": manual_stage_warning,
        "manualStageOperatorOnly": True,
        "researchOnly": True,
        "safeToStageAutomatically": False,
        "automaticCleanupAllowed": False,
        "operatorApprovalRequired": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
    }


def clearance_proposal(reviewed_packets: list[dict[str, Any]]) -> dict[str, Any]:
    """Build prioritized human review hints without clearing source hygiene."""
    lane_proposals: list[dict[str, Any]] = []
    for packet in reviewed_packets:
        rows = packet.get("rows") if isinstance(packet.get("rows"), list) else []
        by_class: dict[str, list[str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "")
            if not path:
                continue
            classification = str(row.get("classification") or "unknown")
            by_class.setdefault(classification, []).append(path)
        review_first = by_class.get("review-before-staging", [])
        keep_research = by_class.get("keep-research", [])
        shadow_only = by_class.get("shadow-only", [])
        quarantine_review = by_class.get("quarantine-review", [])
        dependency_reviewed = by_class.get("dependency-reviewed", [])
        historical_reference = by_class.get("historical-reference", [])
        retired_reference = by_class.get("retired-reference", [])
        lane_proposals.append({
            "packetId": packet.get("id"),
            "lane": packet.get("lane"),
            "decision": "manual-diff-review-required",
            "packetDecision": packet.get("packetDecision"),
            "manualStageEligible": packet.get("manualStageEligible") is True,
            "manualStageWarning": packet.get("manualStageWarning"),
            "diffSummary": packet.get("diffSummary") if isinstance(packet.get("diffSummary"), dict) else {},
            "classificationCounts": packet.get("classificationCounts") if isinstance(packet.get("classificationCounts"), dict) else {},
            "reviewFirst": review_first[:12],
            "keepResearchCandidates": keep_research[:12],
            "shadowOnly": shadow_only[:12],
            "quarantineReview": quarantine_review[:12],
            "dependencyReviewed": dependency_reviewed[:12],
            "historicalReference": historical_reference[:12],
            "retiredReference": retired_reference[:12],
            "omittedCounts": {
                "reviewFirst": max(0, len(review_first) - 12),
                "keepResearchCandidates": max(0, len(keep_research) - 12),
                "shadowOnly": max(0, len(shadow_only) - 12),
                "quarantineReview": max(0, len(quarantine_review) - 12),
                "dependencyReviewed": max(0, len(dependency_reviewed) - 12),
                "historicalReference": max(0, len(historical_reference) - 12),
                "retiredReference": max(0, len(retired_reference) - 12),
            },
            "operatorAction": "Review diffs and tests manually; do not stage from this artifact.",
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
            "safeToStageAutomatically": False,
        })
    return {
        "decision": "manual-clearance-proposal-only",
        "description": "Prioritized review hints for source hygiene. This proposal does not clear source hygiene or approve staging.",
        "laneProposals": lane_proposals,
        "nextCommands": [
            "npm run --silent bill:source-hygiene-plan",
            "npm run --silent bill:source-packet-review",
            "npm run --silent bill:clearance-evidence",
            "npm run --silent bill:goal-completion-audit",
            "npm run --silent bill:obsidian-sync",
        ],
        "hardBlockers": [
            "operator approval required before staging",
            "source tree remains dirty until git status and intake manifests are clean",
            "execution/live files remain quarantined even when firewall tests pass",
        ],
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "safeToStageAutomatically": False,
    }


def packet_summaries(reviewed_packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": packet.get("id"),
            "lane": packet.get("lane"),
            "decision": packet.get("decision"),
            "packetDecision": packet.get("packetDecision"),
            "pathCount": packet.get("pathCount"),
            "sourcePacketPathCount": packet.get("sourcePacketPathCount"),
            "diffSummary": packet.get("diffSummary")
            if isinstance(packet.get("diffSummary"), dict)
            else {},
            "classificationCounts": packet.get("classificationCounts")
            if isinstance(packet.get("classificationCounts"), dict)
            else {},
            "firstCommand": packet.get("firstCommand"),
            "manualStageEligible": packet.get("manualStageEligible") is True,
            "manualStageWarning": packet.get("manualStageWarning"),
            "safeToStageAutomatically": False,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
            "researchOnly": True,
        }
        for packet in reviewed_packets
    ]


def build_review(source_hygiene: dict[str, Any]) -> dict[str, Any]:
    packets = source_hygiene.get("nextReviewPackets") if isinstance(source_hygiene.get("nextReviewPackets"), list) else []
    reviewed_packets = [
        review_packet(packet)
        for packet in packets
        if isinstance(packet, dict) and packet.get("id") in LANE_PACKET_IDS
    ]
    missing_packets = [
        packet_id
        for packet_id in REQUIRED_PACKET_IDS
        if packet_id not in {packet.get("id") for packet in reviewed_packets}
    ]
    aggregate_counts: dict[str, int] = {}
    for packet in reviewed_packets:
        for classification, count in packet.get("classificationCounts", {}).items():
            aggregate_counts[classification] = aggregate_counts.get(classification, 0) + int(count)
    source_clean_blockers = (
        source_hygiene.get("sourceCleanBlockers")
        if isinstance(source_hygiene.get("sourceCleanBlockers"), list)
        else []
    )
    all_rows = [
        row
        for packet in reviewed_packets
        for row in (packet.get("rows") if isinstance(packet.get("rows"), list) else [])
        if isinstance(row, dict)
    ]
    top_quarantine_review = [
        str(row.get("path"))
        for row in all_rows
        if row.get("classification") == "quarantine-review" and row.get("path")
    ][:12]
    top_review_before_staging = [
        str(row.get("path"))
        for row in all_rows
        if row.get("classification") == "review-before-staging" and row.get("path")
    ][:12]
    return {
        "command": "bill-source-packet-review",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": "source-packet-review-visible-execution-locked",
        "researchOnly": True,
        "sourceHygieneCleared": False,
        "packetReviewCleared": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "safeToStageAutomatically": False,
        "automaticCleanupAllowed": False,
        "operatorApprovalRequired": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "sourceCleanBlockers": source_clean_blockers,
        "missingPackets": missing_packets,
        "reviewedPacketCount": len(reviewed_packets),
        "classificationCounts": aggregate_counts,
        "keepResearchCount": aggregate_counts.get("keep-research", 0),
        "shadowOnlyCount": aggregate_counts.get("shadow-only", 0),
        "dependencyReviewedCount": aggregate_counts.get("dependency-reviewed", 0),
        "reviewBeforeStagingCount": aggregate_counts.get("review-before-staging", 0),
        "quarantineReviewCount": aggregate_counts.get("quarantine-review", 0),
        "topReviewBeforeStaging": top_review_before_staging,
        "topQuarantineReview": top_quarantine_review,
        "requiresOperatorDecision": True,
        "packetSummaries": packet_summaries(reviewed_packets),
        "manualClearanceProposal": clearance_proposal(reviewed_packets),
        "packets": reviewed_packets,
        "hardRules": [
            "Packet review is source hygiene evidence only.",
            "No automatic staging, deletion, moves, or reverts.",
            "No order routing, broker writes, funding, demo expansion, or live trading.",
            "Shadow/proxy signal files cannot approve execution.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    proposal = payload.get("manualClearanceProposal") if isinstance(payload.get("manualClearanceProposal"), dict) else {}
    generated_date = str(payload.get("generatedAt") or datetime.now(timezone.utc).isoformat()).split("T", 1)[0]
    lines = [
        f"# Bill Source Packet Review - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Read-only review of control, futures, and prediction-market source hygiene packets. This page does not approve staging, cleanup, routing, funding, demo, paper, or live trading.",
        "",
        "## Decision",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Reviewed packets: `{payload.get('reviewedPacketCount')}`",
        f"- Missing packets: `{payload.get('missingPackets')}`",
        f"- Classification counts: `{payload.get('classificationCounts')}`",
        f"- Keep research count: `{payload.get('keepResearchCount')}`",
        f"- Shadow only count: `{payload.get('shadowOnlyCount')}`",
        f"- Dependency reviewed count: `{payload.get('dependencyReviewedCount')}`",
        f"- Review before staging count: `{payload.get('reviewBeforeStagingCount')}`",
        f"- Quarantine review count: `{payload.get('quarantineReviewCount')}`",
        f"- Source clean blockers: `{payload.get('sourceCleanBlockers')}`",
        f"- Top review before staging: `{payload.get('topReviewBeforeStaging')}`",
        f"- Top quarantine review: `{payload.get('topQuarantineReview')}`",
        f"- Safe to stage automatically: `{payload.get('safeToStageAutomatically')}`",
        f"- Requires operator decision: `{payload.get('requiresOperatorDecision')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Manual clearance proposal: `{proposal.get('decision')}`",
        "",
        "## Manual Clearance Proposal",
        "",
    ]
    lines.append(proposal.get("description", "missing"))
    lines.append("")
    lines.append("### Hard Blockers")
    lines.append("")
    for blocker in proposal.get("hardBlockers") or ["missing"]:
        lines.append(f"- {blocker}")
    lines.append("")
    lines.append("### Next Commands")
    lines.append("")
    for command in proposal.get("nextCommands") or ["missing"]:
        lines.append(f"- `{command}`")
    lines.append("")
    for lane in proposal.get("laneProposals") or []:
        lines.append(f"### `{lane.get('lane')}`")
        lines.append("")
        lines.append(f"- Packet: `{lane.get('packetId')}`")
        lines.append(f"- Decision: `{lane.get('decision')}`")
        lines.append(f"- Classification counts: `{lane.get('classificationCounts')}`")
        lines.append(f"- Review first: `{lane.get('reviewFirst')}`")
        lines.append(f"- Keep research candidates: `{lane.get('keepResearchCandidates')}`")
        lines.append(f"- Shadow only: `{lane.get('shadowOnly')}`")
        lines.append(f"- Dependency reviewed: `{lane.get('dependencyReviewed')}`")
        lines.append(f"- Historical reference: `{lane.get('historicalReference')}`")
        lines.append(f"- Retired reference: `{lane.get('retiredReference')}`")
        lines.append(f"- Quarantine review: `{lane.get('quarantineReview')}`")
        lines.append(f"- Omitted counts: `{lane.get('omittedCounts')}`")
        lines.append("")
    lines.extend([
        "## Packets",
        "",
    ])
    for packet in payload.get("packets") or []:
        lines.append(f"### `{packet.get('id')}`")
        lines.append("")
        lines.append(f"- Lane: `{packet.get('lane')}`")
        lines.append(f"- Decision: `{packet.get('decision')}`")
        lines.append(f"- Source packet decision: `{packet.get('packetDecision')}`")
        lines.append(f"- Diff summary: `{packet.get('diffSummary')}`")
        lines.append(f"- Manual-stage eligible: `{packet.get('manualStageEligible')}`")
        lines.append(f"- Manual-stage warning: {packet.get('manualStageWarning')}")
        lines.append(f"- Manual-stage command: `{packet.get('manualStageCommand')}`")
        lines.append(f"- Safe to stage automatically: `{packet.get('safeToStageAutomatically')}`")
        lines.append(f"- Classification counts: `{packet.get('classificationCounts')}`")
        lines.append(f"- First command: `{(packet.get('commands') or ['missing'])[0]}`")
        lines.append("- Paths:")
        for row in packet.get("rows") or []:
            lines.append(
                f"  - `{row.get('path')}` - `{row.get('classification')}` "
                f"({row.get('reason')})"
            )
            if row.get("reviewRecommendation"):
                lines.append(f"    - Recommendation: `{row.get('reviewRecommendation')}`")
                lines.append(f"    - Review reason: {row.get('reviewReason')}")
                lines.append(f"    - Review blockers: `{row.get('reviewBlockers')}`")
        lines.append("")
    lines.extend(["## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review source hygiene lane packets without cleanup or execution.")
    parser.add_argument("--source-hygiene", default=str(STATE / "bill-source-hygiene-plan.latest.json"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args()

    payload = build_review(read_json(Path(args.source_hygiene)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown = Path(args.markdown) if args.markdown else default_markdown_path()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
