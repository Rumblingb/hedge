#!/usr/bin/env python3
"""Generate the current founder/quant/CTO operating metaprompt.

This is a coordination artifact for Bill/Hermes/Codex agents. It is not a
route approval, broker instruction, or execution gate.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
HERMES = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "founder-quant-cto-metaprompt.latest.json"
DEFAULT_MARKDOWN = HERMES / f"founder-quant-cto-metaprompt-{datetime.now(timezone.utc).date().isoformat()}.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def first_list(value: Any, limit: int = 8) -> list[Any]:
    return value[:limit] if isinstance(value, list) else []


def blocker_queue(
    *,
    goal: dict[str, Any],
    topstep_clearance: dict[str, Any],
    source_hygiene: dict[str, Any],
    prediction_gate: dict[str, Any],
    feeds: dict[str, Any],
) -> list[dict[str, Any]]:
    feed_summary = feeds.get("summary") if isinstance(feeds.get("summary"), dict) else {}
    goal_blocked = set(first_list(goal.get("blockedIds"), 16))
    topstep_operator_required = bool(topstep_clearance.get("operatorConfirmationRequired", True))
    source_clean = bool(source_hygiene.get("sourceClean") or source_hygiene.get("canonicalSourceClean"))
    source_dirty = int(source_hygiene.get("dirtyStatusCount") or source_hygiene.get("canonicalDirtyFiles") or 0)
    source_review_backlog = int(source_hygiene.get("reviewBacklogCount") or 0)
    source_goal_blocked = "source-hygiene-not-cleared" in goal_blocked
    source_cleared = (
        not source_goal_blocked
        and source_clean
        and source_dirty == 0
        and source_review_backlog == 0
    )
    source_is_sibling_only = source_goal_blocked and source_clean and source_dirty == 0 and source_review_backlog == 0
    source_why = (
        "Canonical source is clean; the remaining source blocker is dirty sibling worktree quarantine/selective intake."
        if source_is_sibling_only
        else "Source hygiene is clear in the goal audit; keep monitoring drift, but do not spend cycles on solved source blockers."
        if source_cleared
        else "Dirty execution/live or review packets must be classified before capital-risk promotion."
    )
    source_next_command = (
        "npm run --silent bill:sibling-worktree-intake"
        if source_is_sibling_only or source_cleared
        else "npm run --silent bill:source-packet-review"
    )
    return [
        {
            "id": "topstep-session-safety",
            "status": "blocked" if topstep_operator_required else "ready-for-bounded-readonly-proof-review",
            "why": "TopstepX/ProjectX session warning must be cleared before any broker-touching read-only proof window.",
            "nextCommand": "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-session-safety-clearance",
            "humanStep": "Operator closes extra TopstepX/ProjectX sessions and confirms the warning is gone.",
        },
        {
            "id": "source-hygiene",
            "status": "blocked" if source_goal_blocked else "clear",
            "why": source_why,
            "nextCommand": source_next_command,
            "evidence": {
                "sourceClean": source_clean,
                "reviewBacklogCount": source_review_backlog,
                "dirtyStatusCount": source_dirty,
                "siblingOnly": source_is_sibling_only,
                "goalBlocked": source_goal_blocked,
            },
        },
        {
            "id": "prediction-paper",
            "status": "blocked" if not prediction_gate.get("readyForPaper") else "paper-review-ready",
            "why": "Prediction markets need no-lookahead public CLOB evidence, clean mapping, labels, and manual review.",
            "nextCommand": "npm run --silent bill:prediction-event-paper-promotion-gate",
            "blockedIds": first_list(prediction_gate.get("blockedIds"), 8),
        },
        {
            "id": "feed-posture",
            "status": "research-only",
            "why": "TopstepX/ProjectX is futures broker truth; free feeds are context only.",
            "wiredResearchFeeds": first_list(feed_summary.get("wiredResearchFeeds"), 8),
            "optionalFutureResearch": first_list(feed_summary.get("optionalFutureResearch"), 8),
        },
        {
            "id": "goal-audit",
            "status": "blocked" if goal.get("blockedIds") else "clear",
            "why": "Do not mark the goal complete while prompt/artifact blockers remain.",
            "blockedIds": first_list(goal.get("blockedIds"), 8),
            "promptUncoveredIds": first_list(goal.get("promptUncoveredIds"), 8),
        },
    ]


def capital_doctrine(goal: dict[str, Any]) -> dict[str, Any]:
    blocked = set(first_list(goal.get("blockedIds"), 16))
    return {
        "currentMode": "L0_RESEARCH_CONTROL_PLANE",
        "capitalAtRiskPermission": "ZERO_NEW_RISK",
        "northStar": (
            "Compound from verified realized gains, not forecasts. One clean payout-defense path beats many "
            "uncleared experiments."
        ),
        "sequence": [
            {
                "id": "topstep-100k-demo-calibration",
                "status": "blocked" if "futures-demo-not-cleared" in blocked else "review",
                "rule": "Use only after daily route, broker reconciliation, source hygiene, Topstep session safety, and model gates clear.",
            },
            {
                "id": "prop-payout-defense",
                "status": "locked",
                "rule": "After demo evidence clears, size for survival, consistency, and payout reliability before maximizing notional.",
            },
            {
                "id": "prop-reinvestment-ladder",
                "status": "locked",
                "rule": "Reinvest only realized payouts into additional prop accounts after drawdown controls stay green.",
            },
            {
                "id": "prediction-paper-then-funded",
                "status": "blocked" if "prediction-paper-not-cleared" in blocked else "review",
                "rule": "Prediction markets start as paper only; funding waits for no-lookahead, fillability, labels, and post-spread edge.",
            },
            {
                "id": "brokerage-options-crypto",
                "status": "locked",
                "rule": "Options, brokerage, and crypto are separate risk budgets after futures/prediction evidence is durable.",
            },
        ],
    }


def kill_switches() -> list[dict[str, str]]:
    return [
        {"id": "daily-plan-not-approved", "action": "block all routing"},
        {"id": "broker-reconciliation-not-green", "action": "block all routing"},
        {"id": "source-hygiene-not-cleared", "action": "block promotion and execution only while the goal audit still carries this blocker"},
        {"id": "topstep-session-warning", "action": "pause broker-touching proof loops"},
        {"id": "matrix-or-oos-rejected", "action": "record no-edge memory; require new hypothesis"},
        {"id": "prediction-paper-gate-blocked", "action": "paper/live prediction market trading disabled"},
        {"id": "agent-or-n8n-route-request", "action": "deny; deterministic code owns execution"},
    ]


def strategy_truth(strategy_framework: dict[str, Any]) -> dict[str, Any]:
    matrix = strategy_framework.get("walkforwardMatrix") if isinstance(strategy_framework.get("walkforwardMatrix"), dict) else {}
    factory = strategy_framework.get("strategyFactory") if isinstance(strategy_framework.get("strategyFactory"), dict) else {}
    no_edge = strategy_framework.get("futuresNoEdgeMemory") if isinstance(strategy_framework.get("futuresNoEdgeMemory"), dict) else {}
    return {
        "decision": "real-oos-validation-working-strategies-not-deployable",
        "latestOperatorHandoff": {
            "test": "ES 2000-2019 train to NQ 2022-2025 out-of-sample",
            "beforeScore": 78,
            "afterScore": 12,
            "meaning": (
                "The old score was in-sample contamination. The low real OOS score is useful evidence: "
                "current strategies did not transfer across ES low-rate-era data into NQ AI-boom data."
            ),
        },
        "currentFramework": {
            "decision": strategy_framework.get("decision", "missing"),
            "matrixStatus": matrix.get("status", "missing"),
            "totalWindowsEvaluated": matrix.get("totalWindowsEvaluated", 0),
            "factoryDeployable": bool(factory.get("walkforwardDeployable")),
            "noEdgeRecorded": bool(no_edge.get("matrixRejectionRecorded")),
        },
        "nextResearchShape": [
            "Keep HMM/regime fusion research-only until it survives broker-grade OOS windows.",
            "Train and test across multiple regimes and both ES/NQ, including COVID and AI-era conditions.",
            "Record failed forms into no-edge memory before adding parameters or sizing.",
        ],
    }


def operating_focus(goal: dict[str, Any], strategy_framework: dict[str, Any]) -> dict[str, Any]:
    """Founder-grade weekly focus: what to do next without changing execution authority."""
    blocked = set(first_list(goal.get("blockedIds"), 16))
    one_variable = (
        strategy_framework.get("oneVariableResearch", {}).get("resultSummary", {}).get("nextFollowUp", {})
        if isinstance(strategy_framework.get("oneVariableResearch"), dict)
        else {}
    )
    next_one_variable = one_variable.get("oneVariable") or "broker-grade data/depth only"
    return {
        "currentWeekMission": (
            "Run a one-week Topstep 100K demo observation loop with no autonomous routing: "
            "premarket risk brief, manual/demo observation, broker-reconciled EOD learning, "
            "and one-variable research updates."
        ),
        "highestProbabilityPath": [
            "Preserve the account first; no-trade days are valid when red-folder, source, or model gates are red.",
            "Use TopstepX/ProjectX as futures broker truth; collect read-only 5m+ archive depth before promoting any edge.",
            "Focus futures research on one variable at a time: data depth/source, feature family, cost stress, or sizing overlay.",
            "Use prediction markets in paper/research mode only until forward public CLOB capture, labels, mapping, and post-spread edge clear.",
            "Reinvest only realized, broker-reconciled payouts into additional prop accounts; never compound from dashboard estimates.",
        ],
        "activeResearchLanes": [
            {
                "id": "futures-topstep-demo-observation",
                "status": "blocked" if "futures-demo-not-cleared" in blocked else "review",
                "oneVariable": next_one_variable,
                "successEvidence": [
                    "broker-grade current/session bars",
                    "purged OOS or walk-forward windows",
                    "cost/slippage stress",
                    "daily plan and broker reconciliation",
                ],
            },
            {
                "id": "prediction-paper-forward-clob",
                "status": "blocked" if "prediction-paper-not-cleared" in blocked else "review",
                "oneVariable": "forward public CLOB capture window only",
                "successEvidence": [
                    "fillable public books",
                    "no-lookahead event windows",
                    "resolved labels",
                    "manual paper review",
                ],
            },
            {
                "id": "source-and-agent-coordination",
                "status": "blocked" if "source-hygiene-not-cleared" in blocked else "clear",
                "oneVariable": "selective intake only",
                "successEvidence": [
                    "canonical repo clean",
                    "sibling execution-live files quarantined",
                    "Hermes/Codex handoffs visible",
                ],
            },
        ],
        "agentPartnershipProtocol": [
            "Codex owns code, tests, source hygiene, and dashboard/control-plane integrity.",
            "Hermes owns Obsidian memory, Kanban follow-through, EOD dreaming, and human-readable handoffs.",
            "n8n owns scheduled research/notification workflows only; it does not route orders or move funds.",
            "Sibling Codex threads must coordinate through artifacts and explicit handoffs before changing executable strategy catalogs.",
        ],
        "dailyOperatingLoop": [
            "Premarket: run risk brief and mark red folders before any trade idea.",
            "Intraday: observe manual/demo behavior; capture intent, entry, exit, MAE/MFE, mistakes, and screenshots.",
            "EOD: run daily learning and dreaming synthesis; convert mistakes into one next-day rule.",
            "Research: update no-edge memory before testing the next hypothesis.",
        ],
    }


def lane_operating_contract(goal: dict[str, Any]) -> dict[str, Any]:
    """Make agent ownership explicit so parallel work cannot blur into execution."""
    blocked = set(first_list(goal.get("blockedIds"), 16))
    return {
        "decision": "two-lane-contract-active-execution-locked",
        "why": (
            "The fastest path to compounding is separate ownership: one lane hardens the control plane, "
            "the other tests strategy hypotheses. Neither lane can promote risk without artifact proof."
        ),
        "lanes": [
            {
                "id": "command-lane",
                "owner": "live Codex command thread",
                "status": "active",
                "scope": [
                    "Command Center UI/API",
                    "goal audit and blocker visibility",
                    "Topstep demo-readiness posture",
                    "source hygiene and canonical Obsidian sync",
                ],
                "forbidden": [
                    "no broker order writes",
                    "no route approval",
                    "no strategy claim promotion from research headlines",
                ],
                "currentBlockers": [
                    item
                    for item in [
                        "futures-demo-not-cleared" if "futures-demo-not-cleared" in blocked else None,
                        "prediction-paper-not-cleared" if "prediction-paper-not-cleared" in blocked else None,
                    ]
                    if item
                ],
                "handoffRule": "If a strategy issue appears, record it and hand it to the research lane instead of patching research files mid-run.",
            },
            {
                "id": "research-lane",
                "owner": "sibling Codex strategy-research thread",
                "status": "active-research-only",
                "scope": [
                    "one-variable strategy experiments",
                    "walk-forward and no-edge memory",
                    "Hermes/Obsidian research notes",
                    "adaptive strategy research audit",
                ],
                "forbidden": [
                    "no command-center, goal-gate, broker, cron, or route-approval edits",
                    "no deployable wording unless gates independently prove it",
                    "no execution-control changes",
                ],
                "currentBlockers": ["no promotable futures edge yet", "research artifacts must remain non-executable"],
                "handoffRule": "If an execution/control blocker appears, write a research note and hand it back to the command lane.",
            },
            {
                "id": "hermes-memory-lane",
                "owner": "Hermes/Obsidian/n8n memory layer",
                "status": "coordination-only",
                "scope": [
                    "daily plans and EOD dreaming",
                    "Kanban and human-readable handoffs",
                    "premarket red-folder context",
                    "research inventory and mistakes memory",
                ],
                "forbidden": [
                    "no broker truth replacement",
                    "no order routing authority",
                    "no stale thread claims overriding current artifacts",
                ],
                "currentBlockers": [],
                "handoffRule": "Memory may summarize and approve intent; deterministic code and daily/broker gates own routing permission.",
            },
        ],
        "proofStandard": [
            "Every claim must name the artifact or test that proves it.",
            "Backtests, papers, and videos are hypotheses until current OOS, cost/slippage, and broker/data gates agree.",
            "UI status must separate data readiness, human observation, algo demo expansion, and live execution.",
        ],
    }


def build_metaprompt(
    *,
    goal: dict[str, Any] | None = None,
    topstep_clearance: dict[str, Any] | None = None,
    source_hygiene: dict[str, Any] | None = None,
    prediction_gate: dict[str, Any] | None = None,
    feeds: dict[str, Any] | None = None,
    strategy_framework: dict[str, Any] | None = None,
) -> dict[str, Any]:
    goal = goal if isinstance(goal, dict) else read_json(STATE / "bill-goal-completion-audit.latest.json")
    topstep_clearance = topstep_clearance if isinstance(topstep_clearance, dict) else read_json(STATE / "topstep-session-safety-clearance.latest.json")
    source_hygiene = source_hygiene if isinstance(source_hygiene, dict) else read_json(STATE / "bill-source-hygiene-plan.latest.json")
    prediction_gate = prediction_gate if isinstance(prediction_gate, dict) else read_json(STATE / "prediction-event-paper-promotion-gate.latest.json")
    feeds = feeds if isinstance(feeds, dict) else read_json(STATE / "free-data-feed-audit.latest.json")
    strategy_framework = strategy_framework if isinstance(strategy_framework, dict) else read_json(STATE / "strategy-test-framework-status.latest.json")
    queue = blocker_queue(
        goal=goal,
        topstep_clearance=topstep_clearance,
        source_hygiene=source_hygiene,
        prediction_gate=prediction_gate,
        feeds=feeds,
    )
    return {
        "command": "founder-quant-cto-metaprompt",
        "generatedAt": now_iso(),
        "decision": "active-founder-operating-prompt-execution-locked",
        "role": "founder quant strategist PM CTO",
        "primeDirective": (
            "Maximize the probability of compounding capital by preserving capital first, "
            "removing real blockers, proving edges with current evidence, and never letting "
            "narrative conviction outrank daily-plan, broker, data, source, and model gates."
        ),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForLive": False,
        "safetyLocks": {
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
            "RH_TOPSTEP_READ_ONLY": "true",
            "RH_LIVE_EXECUTION_ENABLED": "false",
            "predictionLiveExecution": "disabled",
        },
        "truthOrder": [
            "broker/platform artifacts",
            "machine state under .rumbling-hedge/state",
            "daily Bill trading plan",
            "Obsidian/Hermes memory",
            "agent notes and old thread summaries",
        ],
        "staleOverrideRule": (
            "Any old Hermes/Codex note implying auto-fire, OCO demo routing, or next-signal execution is stale "
            "unless today's daily plan, broker reconciliation, Topstep session safety, source hygiene, "
            "and goal audit all prove it."
        ),
        "blockerQueue": queue,
        "capitalDoctrine": capital_doctrine(goal),
        "strategyTruth": strategy_truth(strategy_framework),
        "operatingFocus": operating_focus(goal, strategy_framework),
        "laneOperatingContract": lane_operating_contract(goal),
        "killSwitches": kill_switches(),
        "agentOperatingCommandments": [
            "First preserve optionality; no-trade is a valid profitable decision when evidence is weak.",
            "Never convert an attractive narrative, paper, video, or old thread into execution permission.",
            "One-variable tests only: change data source, feature family, label source, or sizing, not all at once.",
            "Retire rejected forms into no-edge memory before looking for the next hypothesis.",
            "Treat the 25-year OOS score drop as validation discipline: it blocks deployment and points to multi-regime training.",
            "Partner agents through state artifacts, Obsidian, and Hermes handoffs; avoid private hidden decisions.",
        ],
        "compoundingPath": [
            "Prove one Topstep account first with broker-reconciled data and deterministic gates.",
            "Reinvest realized payouts only after drawdown, consistency, and payout-defense controls are green.",
            "Use prediction markets only after paper-promotion evidence clears; use Alpaca as non-futures paper/research sandbox.",
            "Add options, brokerage, and crypto only with separate risk budgets after futures/prediction loops produce durable evidence.",
        ],
        "uiStandard": [
            "Show trade permission, broker state, data source, blocker stack, and next safe action in one scan.",
            "Separate data readiness from trade permission.",
            "Prefer dense evidence over decorative status cards.",
        ],
        "completionStandard": [
            "goal audit has zero blockers",
            "source hygiene blocker is gone through reviewed evidence",
            "futures demo expansion gate is green or explicitly retired",
            "prediction paper gate is green or explicitly retired",
            "Command Center, Obsidian, and machine artifacts agree",
            "execution remains deterministic and fail-closed",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Founder Quant CTO Metaprompt",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        f"Generated: `{payload['generatedAt']}`",
        f"Decision: `{payload['decision']}`",
        "",
        "## Prime Directive",
        "",
        payload["primeDirective"],
        "",
        "## Safety Locks",
        "",
    ]
    for key, value in payload["safetyLocks"].items():
        lines.append(f"- `{key}` = `{value}`")
    lines.extend(["", "## Current Blocker Queue", ""])
    for item in payload["blockerQueue"]:
        lines.append(f"### {item['id']}")
        lines.append(f"- Status: `{item['status']}`")
        lines.append(f"- Why: {item['why']}")
        if item.get("nextCommand"):
            lines.append(f"- Next command: `{item['nextCommand']}`")
        if item.get("humanStep"):
            lines.append(f"- Human step: {item['humanStep']}")
        lines.append("")
    lines.extend([
        "## Capital Doctrine",
        "",
        f"- Current mode: `{payload['capitalDoctrine']['currentMode']}`",
        f"- Capital at risk permission: `{payload['capitalDoctrine']['capitalAtRiskPermission']}`",
        f"- North star: {payload['capitalDoctrine']['northStar']}",
        "",
    ])
    for item in payload["capitalDoctrine"]["sequence"]:
        lines.append(f"- `{item['id']}`: `{item['status']}` - {item['rule']}")
    truth = payload.get("strategyTruth", {})
    focus = payload.get("operatingFocus", {})
    handoff = truth.get("latestOperatorHandoff", {}) if isinstance(truth, dict) else {}
    framework = truth.get("currentFramework", {}) if isinstance(truth, dict) else {}
    lines.extend([
        "",
        "## Strategy Truth",
        "",
        f"- Decision: `{truth.get('decision', 'missing')}`",
        f"- Latest OOS test: {handoff.get('test', 'missing')}",
        f"- Score: `{handoff.get('beforeScore', '?')}` before contamination fix -> `{handoff.get('afterScore', '?')}` real OOS",
        f"- Matrix: `{framework.get('matrixStatus', 'missing')}` across `{framework.get('totalWindowsEvaluated', 0)}` windows",
        f"- Factory deployable: `{framework.get('factoryDeployable', False)}`",
        "",
    ])
    lines.extend(f"- {item}" for item in truth.get("nextResearchShape", []))
    lines.extend([
        "",
        "## Operating Focus",
        "",
        focus.get("currentWeekMission", "missing"),
        "",
        "### Highest Probability Path",
        "",
    ])
    lines.extend(f"- {item}" for item in focus.get("highestProbabilityPath", []))
    lines.extend(["", "### Active Research Lanes", ""])
    for lane in focus.get("activeResearchLanes", []):
        lines.append(f"- `{lane.get('id')}`: `{lane.get('status')}` - one variable: {lane.get('oneVariable')}")
    lines.extend(["", "### Agent Partnership Protocol", ""])
    lines.extend(f"- {item}" for item in focus.get("agentPartnershipProtocol", []))
    lines.extend(["", "### Daily Operating Loop", ""])
    lines.extend(f"- {item}" for item in focus.get("dailyOperatingLoop", []))
    contract = payload.get("laneOperatingContract", {})
    lines.extend([
        "",
        "## Lane Operating Contract",
        "",
        f"Decision: `{contract.get('decision', 'missing')}`",
        "",
        contract.get("why", ""),
        "",
    ])
    for lane in contract.get("lanes", []):
        lines.append(f"### {lane.get('id')}")
        lines.append(f"- Owner: {lane.get('owner')}")
        lines.append(f"- Status: `{lane.get('status')}`")
        lines.append(f"- Scope: {', '.join(lane.get('scope', []))}")
        lines.append(f"- Forbidden: {', '.join(lane.get('forbidden', []))}")
        if lane.get("currentBlockers"):
            lines.append(f"- Current blockers: {', '.join(lane.get('currentBlockers', []))}")
        lines.append(f"- Handoff rule: {lane.get('handoffRule')}")
        lines.append("")
    lines.extend(["### Proof Standard", ""])
    lines.extend(f"- {item}" for item in contract.get("proofStandard", []))
    lines.extend(["", "## Kill Switches", ""])
    lines.extend(f"- `{item['id']}` -> {item['action']}" for item in payload["killSwitches"])
    lines.extend(["", "## Agent Operating Commandments", ""])
    lines.extend(f"- {item}" for item in payload["agentOperatingCommandments"])
    lines.extend([
        "",
        "## Stale Override Rule",
        "",
        payload["staleOverrideRule"],
        "",
        "## Compounding Path",
        "",
    ])
    lines.extend(f"- {item}" for item in payload["compoundingPath"])
    lines.extend(["", "## Completion Standard", ""])
    lines.extend(f"- {item}" for item in payload["completionStandard"])
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate current Bill founder/quant/CTO metaprompt.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_metaprompt()
    if not args.dry_run:
        output = Path(args.output)
        markdown = Path(args.markdown)
        output.parent.mkdir(parents=True, exist_ok=True)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        markdown.write_text(render_markdown(payload))
    if args.compact:
        print(json.dumps({
            "decision": payload["decision"],
            "blocked": [item["id"] for item in payload["blockerQueue"] if item["status"] == "blocked"],
            "wiredFeeds": next((item.get("wiredResearchFeeds", []) for item in payload["blockerQueue"] if item["id"] == "feed-posture"), []),
            "readyForExecution": payload["readyForExecution"],
        }, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
