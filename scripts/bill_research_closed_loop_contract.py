#!/usr/bin/env python3
"""Build Bill's research-only closed-loop contract.

The contract is the small handoff a weaker agent can follow from "interesting
idea" to "machine evidence" without touching execution. It reads current
futures/prediction artifacts and writes both machine JSON and an Obsidian note.
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
CATALOG = VAULT / "Research-Catalog"
DEFAULT_OUTPUT = STATE / "bill-research-closed-loop-contract.latest.json"
DEFAULT_MARKDOWN = HERMES / "bill-research-closed-loop-contract-2026-05-29.md"


def read_json(path: Path, default: Any | None = None) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {} if default is None else default


def first_ids(items: list[dict[str, Any]], limit: int = 5) -> list[str]:
    return [str(item.get("id", "missing")) for item in items[:limit] if isinstance(item, dict)]


def count_with_zero(counts: dict[str, Any], key: str) -> Any:
    if not isinstance(counts, dict):
        return "missing"
    return counts[key] if key in counts else 0


def resolved_subject_summary(payload: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    return [
        {
            "externalId": item.get("externalId"),
            "status": item.get("status"),
            "resolvedMatchCount": item.get("resolvedMatchCount"),
            "subjectSpecificMatchCount": item.get("subjectSpecificMatchCount"),
            "subjectSpecificWinRate": item.get("subjectSpecificWinRate"),
        }
        for item in items[:limit]
        if isinstance(item, dict)
    ]


def research_seed_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    queue = payload.get("nextBuildQueue") if isinstance(payload.get("nextBuildQueue"), list) else []
    queued_youtube_targets = (
        payload.get("queuedYouTubeResearcherTargets")
        if isinstance(payload.get("queuedYouTubeResearcherTargets"), list)
        else []
    )
    latest_youtube_run = (
        payload.get("queuedYouTubeLatestRun")
        if isinstance(payload.get("queuedYouTubeLatestRun"), dict)
        else {}
    )
    return {
        "researchOnly": payload.get("researchOnly", "missing"),
        "writesOrders": payload.get("writesOrders", "missing"),
        "readyForExecution": payload.get("readyForExecution", False),
        "totalSeeds": summary.get("totalSeeds", "missing"),
        "machineTestableSeeds": summary.get("machineTestableSeeds", "missing"),
        "candidateRetestSeeds": summary.get("candidateRetestSeeds", "missing"),
        "quarantinedNoEdgeSeeds": summary.get("quarantinedNoEdgeSeeds", "missing"),
        "unmappedSeeds": summary.get("unmappedSeeds", "missing"),
        "duplicateSourceIds": summary.get("duplicateSourceIds", "missing"),
        "executableSeeds": summary.get("executableSeeds", "missing"),
        "queuedYouTubeSeeds": summary.get("queuedYouTubeSeeds", "missing"),
        "queuedYouTubeTargetIds": [
            str(item.get("id"))
            for item in queued_youtube_targets[:5]
            if isinstance(item, dict) and item.get("id")
        ],
        "queuedYouTubeLatestRun": {
            "present": latest_youtube_run.get("present", False),
            "runId": latest_youtube_run.get("runId"),
            "status": latest_youtube_run.get("status"),
            "targetsAttempted": latest_youtube_run.get("targetsAttempted"),
            "targetsSucceeded": latest_youtube_run.get("targetsSucceeded"),
            "chunksCollected": latest_youtube_run.get("chunksCollected"),
            "strategyHypothesesCount": latest_youtube_run.get("strategyHypothesesCount"),
            "blockers": latest_youtube_run.get("blockers") if isinstance(latest_youtube_run.get("blockers"), list) else [],
        },
        "nextBuildQueue": [
            {
                "id": item.get("id"),
                "sourceId": item.get("sourceId"),
                "title": item.get("title"),
                "inferredStrategyId": item.get("inferredStrategyId"),
                "decision": item.get("decision"),
                "machineTestable": item.get("machineTestable"),
                "localExecutable": item.get("localExecutable"),
                "blockers": item.get("blockers") or [],
                "nextAction": item.get("nextAction"),
            }
            for item in queue[:5]
            if isinstance(item, dict)
        ],
        "hardRules": payload.get("hardRules") or [],
    }


def research_seed_target_refresh_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    latest = payload.get("latestQueuedRun") if isinstance(payload.get("latestQueuedRun"), dict) else {}
    decisions = payload.get("targetDecisions") if isinstance(payload.get("targetDecisions"), list) else []
    return {
        "present": bool(payload),
        "decision": payload.get("decision", "missing"),
        "researchOnly": payload.get("researchOnly", "missing"),
        "writesOrders": payload.get("writesOrders", "missing"),
        "touchesBroker": payload.get("touchesBroker", "missing"),
        "readyForExecution": payload.get("readyForExecution", False),
        "queuedTargetCount": summary.get("queuedTargetCount", "missing"),
        "retireOrManualConvertCount": summary.get("retireOrManualConvertCount", "missing"),
        "rerunnableTargetCount": summary.get("rerunnableTargetCount", "missing"),
        "zeroYieldSameTargets": summary.get("zeroYieldSameTargets", "missing"),
        "latestRun": {
            "runId": latest.get("runId"),
            "status": latest.get("status"),
            "chunksCollected": latest.get("chunksCollected"),
            "strategyHypothesesCount": latest.get("strategyHypothesesCount"),
            "blockers": latest.get("blockers") if isinstance(latest.get("blockers"), list) else [],
        },
        "targetDecisions": [
            {
                "targetId": item.get("targetId"),
                "action": item.get("action"),
                "rerunAllowed": item.get("rerunAllowed"),
                "reason": item.get("reason"),
            }
            for item in decisions[:5]
            if isinstance(item, dict)
        ],
        "newTargetRequirements": payload.get("newTargetRequirements") if isinstance(payload.get("newTargetRequirements"), list) else [],
    }


def next_research_action_summary(payload: dict[str, Any]) -> dict[str, Any]:
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    if not actions:
        actions = payload.get("queue") if isinstance(payload.get("queue"), list) else []
    return {
        "researchOnly": payload.get("researchOnly", "missing"),
        "writesOrders": payload.get("writesOrders", "missing"),
        "readyForExecution": payload.get("readyForExecution", False),
        "actionCount": len(actions),
        "topActions": [
            {
                "id": item.get("id"),
                "lane": item.get("lane"),
                "priority": item.get("priority"),
                "firstCommand": item.get("firstCommand") or (item.get("commands") or ["missing"])[0],
                "promotionGate": item.get("promotionGate"),
                "commandHint": item.get("commandHint"),
                "researchOnly": item.get("researchOnly", True),
                "writesOrders": item.get("writesOrders", False),
                "touchesBroker": item.get("touchesBroker", False),
            }
            for item in actions[:8]
            if isinstance(item, dict)
        ],
    }


def build_prompt_to_artifact_checklist() -> list[dict[str, Any]]:
    return [
        {
            "step": "source-capture",
            "requiredArtifact": "Obsidian resource card or manifest entry with URL/path, source type, and lane",
            "acceptance": "The idea has a traceable source. YT/social/paper claims are hypotheses only.",
        },
        {
            "step": "hypothesis-card",
            "requiredArtifact": "Hypothesis note with market, edge mechanism, invalidation, and one changed variable",
            "acceptance": "The proposed change is testable without changing multiple knobs at once.",
        },
        {
            "step": "data-provenance",
            "requiredArtifact": "Dataset path, date range, freshness result, symbol/venue mapping, and known gaps",
            "acceptance": "No stale/fallback/no-data artifact is allowed to stand in for evidence.",
        },
        {
            "step": "implementation-link",
            "requiredArtifact": "Script/module path plus exact command used to run the test",
            "acceptance": "The implementation is deterministic and research-only unless promotion gates later approve it.",
        },
        {
            "step": "in-sample-baseline",
            "requiredArtifact": "Baseline metrics with costs/slippage/fees visible",
            "acceptance": "Full-sample strength can seed OOS work but cannot promote a strategy.",
        },
        {
            "step": "out-of-sample-proof",
            "requiredArtifact": "Purged/walk-forward/OOS artifact, window count, PF/expectancy, drawdown, and trade count",
            "acceptance": "The OOS contract beats the strategy-family threshold after costs.",
        },
        {
            "step": "stress-and-fillability",
            "requiredArtifact": "Futures cost stress or prediction spread/CLOB persistence/fillability gate",
            "acceptance": "The edge survives conservative transaction costs and realistic fill assumptions.",
        },
        {
            "step": "decision-memory",
            "requiredArtifact": "Promotion, retest, quarantine, or no-edge ledger entry",
            "acceptance": "Rejected ideas are preserved so the loop does not keep rediscovering the same false edge.",
        },
        {
            "step": "execution-separation",
            "requiredArtifact": "Daily plan and live-readiness gate continue to show execution locked unless explicitly green",
            "acceptance": "Research artifacts never submit orders, write fills, change route flags, or approve sizing.",
        },
    ]


def build_contract(args: argparse.Namespace) -> dict[str, Any]:
    futures = read_json(Path(args.futures_triage))
    prediction = read_json(Path(args.prediction_triage))
    drilldown = read_json(Path(args.prediction_drilldown))
    narrow_scan = read_json(Path(args.prediction_narrow_scan))
    resolved_join = read_json(Path(args.prediction_resolved_join))
    live = read_json(Path(args.live_readiness))
    tooling = read_json(Path(args.alpha_tooling))
    worktree = read_json(Path(args.worktree))
    zoo = read_json(Path(args.strategy_zoo))
    zoo_counts = zoo.get("counts") if isinstance(zoo.get("counts"), dict) else {}
    futures_no_edge = read_json(Path(args.futures_no_edge))
    strategy_feed = read_json(Path(args.strategy_feed))
    seed_triage = read_json(Path(getattr(args, "research_seed_triage", STATE / "research-seed-triage.latest.json")))
    seed_target_refresh = read_json(Path(getattr(args, "research_seed_target_refresh", STATE / "research-seed-target-refresh-plan.latest.json")))
    next_actions = read_json(Path(getattr(args, "next_research_actions", STATE / "bill-next-research-actions.latest.json")))
    manifest = Path(args.resource_manifest)

    futures_tests = futures.get("nextTests") if isinstance(futures.get("nextTests"), list) else []
    prediction_tests = prediction.get("nextTests") if isinstance(prediction.get("nextTests"), list) else []
    drilldown_tests = drilldown.get("nextTests") if isinstance(drilldown.get("nextTests"), list) else []
    source_blockers = worktree.get("sourceCleanBlockers") if isinstance(worktree.get("sourceCleanBlockers"), list) else []

    return {
        "command": "bill-research-closed-loop-contract",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "writesOrders": False,
        "readyForExecution": False,
        "priorityLanes": ["futures", "prediction-markets"],
        "executionBoundary": {
            "dailyPlanMustApprove": True,
            "deterministicCodeRoutes": True,
            "llmMayRoute": False,
            "currentReadyForDemoExpansion": bool(live.get("readyForDemoExpansion")),
            "currentReadyForLive": bool(live.get("readyForLive")),
            "blockers": live.get("blockers") or [],
            "warnings": live.get("warnings") or [],
        },
        "tooling": {
            "status": tooling.get("status", "missing"),
            "readyForResearchLoop": tooling.get("readyForResearchLoop", False),
            "readyForExecution": tooling.get("readyForExecution", False),
            "blockers": tooling.get("blockers") or [],
            "warnings": tooling.get("warnings") or [],
        },
        "sourceHygiene": {
            "sourceClean": not source_blockers,
            "blockers": source_blockers,
        },
        "resourceMemory": {
            "fullManifestPath": str(manifest),
            "fullManifestExists": manifest.exists(),
            "resourceInventoryPath": str(CATALOG / "Bill-Resource-Inventory.md"),
        },
        "strategyCatalog": {
            "total": zoo.get("totalStrategies", zoo.get("total", count_with_zero(zoo_counts, "total"))),
            "skeleton": zoo.get("skeletonCount", count_with_zero(zoo_counts, "classification:SKELETON")),
            "gold": zoo.get("goldCount", count_with_zero(zoo_counts, "classification:GOLD")),
            "quarantined": zoo.get("quarantinedCount", count_with_zero(zoo_counts, "classification:QUARANTINED")),
        },
        "researchStrategyFeed": {
            "allowedDirectives": len(strategy_feed.get("directives") or []),
            "blockedDirectives": strategy_feed.get("blockedDirectiveCount", len(strategy_feed.get("blockedDirectives") or [])),
            "directiveBlockReason": strategy_feed.get("directiveBlockReason", "missing"),
            "blockedStrategies": [
                item.get("strategyId")
                for item in (strategy_feed.get("blockedDirectives") or [])
                if isinstance(item, dict)
            ],
        },
        "researchSeedTriage": research_seed_summary(seed_triage),
        "researchSeedTargetRefresh": research_seed_target_refresh_summary(seed_target_refresh),
        "nextResearchActions": next_research_action_summary(next_actions),
        "promptToArtifactChecklist": build_prompt_to_artifact_checklist(),
        "futures": {
            "decision": futures.get("decision", "missing"),
            "readyForDemoExpansion": futures.get("readyForDemoExpansion", False),
            "nextTestIds": first_ids(futures_tests),
            "noEdgeMemory": {
                "entries": futures_no_edge.get("count", "missing"),
                "noEdge": futures_no_edge.get("noEdgeCount", "missing"),
                "needsNewFeature": futures_no_edge.get("needsNewFeatureCount", "missing"),
                "promotable": futures_no_edge.get("promotableCount", "missing"),
            },
            "oneVariableQueue": futures_tests,
            "hardRules": futures.get("hardRules") or [],
        },
        "predictionMarkets": {
            "decision": prediction.get("decision", "missing"),
            "readyForPaper": prediction.get("readyForPaper", False),
            "evidenceNextTestIds": first_ids(prediction_tests),
            "categoryNextTestIds": first_ids(drilldown_tests),
            "narrowScan": {
                "researchOnly": narrow_scan.get("researchOnly", "missing"),
                "writesOrders": narrow_scan.get("writesOrders", "missing"),
                "readyForPaper": narrow_scan.get("readyForPaper", False),
                "categoryCount": (narrow_scan.get("summary") or {}).get("categoryCount", "missing"),
                "paperCandidates": (narrow_scan.get("summary") or {}).get("paperCandidates", "missing"),
                "watchCandidates": (narrow_scan.get("summary") or {}).get("watchCandidates", "missing"),
                "viablePairs": (narrow_scan.get("summary") or {}).get("viablePairs", "missing"),
                "repairableNearMisses": (narrow_scan.get("summary") or {}).get("repairableNearMisses", "missing"),
                "reports": [
                    {
                        "category": item.get("category"),
                        "status": item.get("status"),
                        "snapshotMarketCount": item.get("snapshotMarketCount"),
                        "journalPath": item.get("journalPath"),
                    }
                    for item in (narrow_scan.get("reports") or [])[:6]
                    if isinstance(item, dict)
                ],
            },
            "narrowSnapshots": [
                {
                    "category": item.get("category"),
                    "path": item.get("path"),
                    "marketCount": item.get("marketCount"),
                    "researchOnly": item.get("researchOnly"),
                    "writesOrders": item.get("writesOrders"),
                    "nextTestId": item.get("nextTestId"),
                }
                for item in (drilldown.get("narrowSnapshots") or [])[:6]
                if isinstance(item, dict)
            ],
            "resolvedOutcomeJoin": {
                "historicalRowsLoaded": resolved_join.get("historicalRowsLoaded", "missing"),
                "statusCounts": resolved_join.get("statusCounts", {}),
                "joinedResearchOnlyCount": resolved_join.get("joinedResearchOnlyCount", "missing"),
                "minSpecificMatches": resolved_join.get("minSpecificMatches", "missing"),
                "subjectSpecific": resolved_subject_summary(resolved_join),
                "readyForPaper": resolved_join.get("readyForPaper", False),
            },
            "resolvedOutcomeReview": prediction.get("resolvedOutcomeReview") or {
                "status": "missing",
                "decision": "missing",
                "broadPriorRisk": "missing",
                "readyForPaper": False,
                "items": [],
                "requiredNextEvidence": [],
            },
            "oneVariableQueue": prediction_tests + drilldown_tests,
            "hardRules": (prediction.get("hardRules") or []) + (drilldown.get("hardRules") or []),
        },
        "nextOperatorActions": [
            "Keep execution locked while source hygiene, OOS, and prediction-paper gates are red.",
            "For futures, test only branches that can improve OOS evidence after cost/slippage stress.",
            "For prediction markets, run narrow category scans and resolved-outcome joins before more CLOB capture.",
            "Treat YT/paper/web 'gold' as source material until research seed triage and local OOS artifacts agree.",
            "Write every rejected hypothesis to no-edge memory instead of weakening thresholds.",
            "Sync Obsidian after each research loop so the control hub reflects machine truth.",
        ],
    }


def write_markdown(path: Path, contract: dict[str, Any]) -> None:
    checklist = contract["promptToArtifactChecklist"]
    futures = contract["futures"]
    prediction = contract["predictionMarkets"]
    seed_triage = contract["researchSeedTriage"]
    seed_target_refresh = contract["researchSeedTargetRefresh"]
    next_actions = contract["nextResearchActions"]
    boundary = contract["executionBoundary"]
    lines = [
        "# Bill Research Closed-Loop Contract - 2026-05-29",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "This page is the handoff contract for futures and prediction-market research. It is research-only and cannot approve trades.",
        "",
        "## Execution Boundary",
        "",
        f"- Ready for demo expansion: `{boundary['currentReadyForDemoExpansion']}`",
        f"- Ready for live: `{boundary['currentReadyForLive']}`",
        f"- Writes orders: `{contract['writesOrders']}`",
        f"- LLM may route: `{boundary['llmMayRoute']}`",
        f"- Blockers: `{boundary['blockers']}`",
        f"- Research strategy feed: allowed `{contract['researchStrategyFeed']['allowedDirectives']}`, blocked `{contract['researchStrategyFeed']['blockedDirectives']}`, reason `{contract['researchStrategyFeed']['directiveBlockReason']}`",
        f"- Research seed triage: total `{seed_triage['totalSeeds']}`, candidateRetest `{seed_triage['candidateRetestSeeds']}`, quarantined `{seed_triage['quarantinedNoEdgeSeeds']}`, executable `{seed_triage['executableSeeds']}`, duplicateSourceIds `{seed_triage['duplicateSourceIds']}`",
        f"- Next research actions: count `{next_actions['actionCount']}`, researchOnly `{next_actions['researchOnly']}`, writesOrders `{next_actions['writesOrders']}`, readyForExecution `{next_actions['readyForExecution']}`",
        "",
        "## Prompt To Artifact Checklist",
        "",
    ]
    for item in checklist:
        lines.append(f"- `{item['step']}`: {item['requiredArtifact']} Acceptance: {item['acceptance']}")
    lines.extend([
        "",
        "## Futures Queue",
        "",
        f"- Decision: `{futures['decision']}`",
        f"- Ready for demo expansion: `{futures['readyForDemoExpansion']}`",
        f"- Next tests: `{futures['nextTestIds']}`",
        "",
    ])
    for item in futures["oneVariableQueue"]:
        lines.append(f"- `{item.get('id', 'missing')}`: one variable `{item.get('oneVariable', 'missing')}`. {item.get('promotionRule', '')}")
    lines.extend([
        "",
        "## Research Seed Triage",
        "",
        f"- Research-only: `{seed_triage['researchOnly']}`",
        f"- Writes orders: `{seed_triage['writesOrders']}`",
        f"- Ready for execution: `{seed_triage['readyForExecution']}`",
        f"- Total seeds: `{seed_triage['totalSeeds']}`",
        f"- Machine-testable seeds: `{seed_triage['machineTestableSeeds']}`",
        f"- Candidate retest seeds: `{seed_triage['candidateRetestSeeds']}`",
        f"- Quarantined/no-edge seeds: `{seed_triage['quarantinedNoEdgeSeeds']}`",
        f"- Unmapped seeds: `{seed_triage['unmappedSeeds']}`",
        f"- Duplicate source ids: `{seed_triage['duplicateSourceIds']}`",
        f"- Queued YouTube seeds: `{seed_triage['queuedYouTubeSeeds']}` targets `{seed_triage['queuedYouTubeTargetIds']}`",
        f"- Latest queued YouTube run: status `{seed_triage['queuedYouTubeLatestRun']['status']}`, chunks `{seed_triage['queuedYouTubeLatestRun']['chunksCollected']}`, hypotheses `{seed_triage['queuedYouTubeLatestRun']['strategyHypothesesCount']}`, blockers `{seed_triage['queuedYouTubeLatestRun']['blockers']}`",
        f"- Target refresh plan: `{seed_target_refresh['decision']}` queued `{seed_target_refresh['queuedTargetCount']}`, retire/manual `{seed_target_refresh['retireOrManualConvertCount']}`, rerunnable `{seed_target_refresh['rerunnableTargetCount']}`",
        "",
    ])
    for item in seed_triage["nextBuildQueue"]:
        lines.append(f"- `{item.get('inferredStrategyId', 'missing')}`: `{item.get('id', 'missing')}` {item.get('title', '')}. {item.get('nextAction', '')}")
    for item in seed_target_refresh["targetDecisions"]:
        lines.append(
            f"- refresh `{item.get('targetId', 'missing')}`: action `{item.get('action', 'missing')}`, rerun `{item.get('rerunAllowed')}`. {item.get('reason', '')}"
        )
    lines.extend([
        "",
        "## Next Research Actions",
        "",
    ])
    for item in next_actions["topActions"]:
        lines.append(f"- `{item.get('id', 'missing')}` / `{item.get('lane', 'missing')}`: first command `{item.get('firstCommand', 'missing')}`. Gate: {item.get('promotionGate', '')}")
    lines.extend([
        "",
        "## Prediction-Market Queue",
        "",
        f"- Decision: `{prediction['decision']}`",
        f"- Ready for paper: `{prediction['readyForPaper']}`",
        f"- Evidence tests: `{prediction['evidenceNextTestIds']}`",
        f"- Category tests: `{prediction['categoryNextTestIds']}`",
        f"- Narrow scan: categories `{prediction['narrowScan']['categoryCount']}`, watch `{prediction['narrowScan']['watchCandidates']}`, paper `{prediction['narrowScan']['paperCandidates']}`, viablePairs `{prediction['narrowScan']['viablePairs']}`, repairableNearMisses `{prediction['narrowScan']['repairableNearMisses']}`, readyForPaper `{prediction['narrowScan']['readyForPaper']}`",
        f"- Narrow snapshots: `{[(item.get('category'), item.get('marketCount'), item.get('path')) for item in prediction.get('narrowSnapshots', [])]}`",
        f"- Resolved outcome join: historicalRows `{prediction['resolvedOutcomeJoin']['historicalRowsLoaded']}`, statusCounts `{prediction['resolvedOutcomeJoin']['statusCounts']}`, subjectSpecific `{prediction['resolvedOutcomeJoin']['subjectSpecific']}`, readyForPaper `{prediction['resolvedOutcomeJoin']['readyForPaper']}`",
        f"- Resolved outcome review: decision `{prediction['resolvedOutcomeReview'].get('decision', 'missing')}`, broadPriorRisk `{prediction['resolvedOutcomeReview'].get('broadPriorRisk', 'missing')}`, readyForPaper `{prediction['resolvedOutcomeReview'].get('readyForPaper', False)}`",
        "",
    ])
    for item in prediction["oneVariableQueue"]:
        lines.append(f"- `{item.get('id', 'missing')}`: one variable `{item.get('oneVariable', 'missing')}`. {item.get('promotionRule', '')}")
    lines.extend([
        "",
        "## Operator Actions",
        "",
    ])
    for action in contract["nextOperatorActions"]:
        lines.append(f"- {action}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Bill/Hermes research-only closed-loop contract.")
    parser.add_argument("--futures-triage", default=str(STATE / "futures-evidence-triage.latest.json"))
    parser.add_argument("--prediction-triage", default=str(STATE / "prediction-evidence-triage.latest.json"))
    parser.add_argument("--prediction-drilldown", default=str(STATE / "prediction-category-drilldown.latest.json"))
    parser.add_argument("--prediction-narrow-scan", default=str(STATE / "prediction-narrow-scan-runner.latest.json"))
    parser.add_argument("--prediction-resolved-join", default=str(STATE / "prediction-resolved-outcome-join.latest.json"))
    parser.add_argument("--live-readiness", default=str(STATE / "live-readiness-gate.latest.json"))
    parser.add_argument("--alpha-tooling", default=str(STATE / "alpha-research-tooling-check.latest.json"))
    parser.add_argument("--worktree", default=str(STATE / "worktree-consolidation.latest.json"))
    parser.add_argument("--strategy-zoo", default=str(STATE / "strategy-zoo-audit.latest.json"))
    parser.add_argument("--futures-no-edge", default=str(ROOT / ".rumbling-hedge/research/futures-no-edge-ledger/latest.json"))
    parser.add_argument("--strategy-feed", default=str(ROOT / ".rumbling-hedge/research/researcher/strategy-feed.latest.json"))
    parser.add_argument("--research-seed-triage", default=str(STATE / "research-seed-triage.latest.json"))
    parser.add_argument("--research-seed-target-refresh", default=str(STATE / "research-seed-target-refresh-plan.latest.json"))
    parser.add_argument("--next-research-actions", default=str(STATE / "bill-next-research-actions.latest.json"))
    parser.add_argument("--resource-manifest", default=str(CATALOG / "Bill-Resource-Full-Manifest.jsonl"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()
    contract = build_contract(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    write_markdown(Path(args.markdown), contract)
    print(json.dumps(contract, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
