#!/usr/bin/env python3
"""Summarize adaptive futures strategy research without creating route authority.

This artifact is a founder-facing research truth table. It compares narrative
strategy claims against the current walk-forward, one-variable, MTF-entry, and
no-edge memory artifacts so agents can ask better next questions without
confusing research evidence for execution approval.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
RESEARCH = ROOT / ".rumbling-hedge" / "research" / "adaptive-strategy"
OBSIDIAN = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"

DEFAULT_BUILD_PLAN = OBSIDIAN / "build-plan-from-data-to-compound-2026-06-05.md"
DEFAULT_HERMES_NOTES = {
    "founder_metaprompt": OBSIDIAN / "founder-quant-cto-metaprompt-2026-06-05.md",
    "topstep_daily_learning": OBSIDIAN / "topstep-daily-learning-2026-06-05.md",
    "session_intelligence": OBSIDIAN / "session-intelligence-framework-2026-06-05.md",
    "strategy_factory_handoff": OBSIDIAN / "strategy-factory-one-variable-handoff-2026-06-05.md",
}
DEFAULT_OUTPUT = STATE / "adaptive-strategy-research-audit.latest.json"
DEFAULT_RESEARCH_OUTPUT = RESEARCH / "adaptive-strategy-research-audit.latest.json"
DEFAULT_MARKDOWN = OBSIDIAN / "adaptive-strategy-research-audit.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def as_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except Exception:
        return default


def claim_status_from_factory(factory: dict[str, Any], no_edge: dict[str, Any]) -> dict[str, Any]:
    no_edge_summary_raw = (
        factory.get("researchContext", {})
        .get("noEdgeLedger", {})
        .get("learningSummary", {})
    )
    no_edge_summary = no_edge_summary_raw if isinstance(no_edge_summary_raw, dict) else {}
    factory_no_edge = factory.get("researchContext", {}).get("noEdgeLedger", {})
    factory_no_edge = factory_no_edge if isinstance(factory_no_edge, dict) else {}
    profiles_evaluated = int(as_number(factory.get("quantCoverage", {}).get("profilesEvaluated")))
    promotable = int(
        as_number(
            no_edge_summary.get("promotableProfiles"),
            as_number(factory_no_edge.get("promotableProfiles"), as_number(no_edge.get("promotableCount"))),
        )
    )
    needs_more_data = int(
        as_number(
            no_edge_summary.get("needsMoreDataProfiles"),
            as_number(factory_no_edge.get("needsMoreDataProfiles"), as_number(no_edge.get("needsNewFeatureCount"))),
        )
    )
    factory_status = str(factory.get("status") or "")
    deployable = bool(factory.get("gates", {}).get("walkforwardDeployable"))

    if promotable > 0 and deployable:
        status = "partially-evidenced"
    else:
        status = "not-proven"

    contradiction = []
    if factory_status == "blocked":
        contradiction.append("strategy-factory-status-blocked")
    if not deployable:
        contradiction.append("walkforward-not-deployable")
    if promotable == 0:
        contradiction.append("zero-promotable-profiles")
    if needs_more_data:
        contradiction.append("profiles-need-more-data")

    return {
        "claim": "53/56 strategies have positive expectancy",
        "status": status,
        "profilesEvaluated": profiles_evaluated,
        "promotableProfiles": promotable,
        "needsMoreDataProfiles": needs_more_data,
        "factoryStatus": factory_status,
        "walkforwardDeployable": deployable,
        "contradictions": contradiction,
        "operatorRead": (
            "Treat positive expectancy as a hypothesis pool, not a deployable edge. "
            "Current promotion evidence has zero promotable profiles."
        ),
    }


def best_one_variable_watch(one_variable: dict[str, Any]) -> dict[str, Any]:
    result = one_variable.get("resultSummary", {})
    best = result.get("bestObserved") if isinstance(result.get("bestObserved"), dict) else {}
    follow_up = result.get("nextFollowUp") if isinstance(result.get("nextFollowUp"), dict) else {}
    return {
        "id": best.get("experimentId") or "",
        "baselineId": best.get("baselineId") or "",
        "status": "watch-only",
        "oneVariable": follow_up.get("oneVariable") or "session filter only",
        "oosTradeCount": int(as_number(best.get("oosTradeCount"))),
        "oosNetPoints": round(as_number(best.get("oosNetPoints")), 4),
        "oosProfitFactor": round(as_number(best.get("oosProfitFactor")), 6),
        "walkforwardPositiveFoldShare": round(as_number(best.get("walkforwardPositiveFoldShare")), 6),
        "blockers": best.get("blockers") if isinstance(best.get("blockers"), list) else [],
        "readyForExecution": False,
        "touchesBroker": False,
        "writesOrders": False,
        "why": follow_up.get("why")
        or "Best observed one-variable result still failed promotion gates.",
    }


def entry_watch(entry: dict[str, Any]) -> dict[str, Any]:
    best = entry.get("bestResearchWatch") if isinstance(entry.get("bestResearchWatch"), dict) else {}
    oos = best.get("oos") if isinstance(best.get("oos"), dict) else {}
    return {
        "id": best.get("id") or "",
        "status": "needs-broker-grade-overlap",
        "oosTradeCount": int(as_number(oos.get("tradeCount"))),
        "oosNetPoints": round(as_number(oos.get("netPoints")), 4),
        "oosProfitFactor": round(as_number(oos.get("profitFactor")), 6),
        "coveragePct": round(as_number(best.get("coveragePct")), 4),
        "blockers": best.get("blockers") if isinstance(best.get("blockers"), list) else [],
        "readyForExecution": False,
        "touchesBroker": False,
        "writesOrders": False,
        "operatorRead": (
            "Promising entry timing branch, but the current watch has too few OOS "
            "trades or thin lower-timeframe coverage."
        ),
    }


def no_edge_entries(no_edge: dict[str, Any]) -> list[dict[str, Any]]:
    entries = no_edge.get("entries") if isinstance(no_edge.get("entries"), list) else []
    selected: list[dict[str, Any]] = []
    for row in entries:
        if not isinstance(row, dict):
            continue
        verdict = str(row.get("verdict") or "")
        if verdict in {"no-edge", "needs-new-feature"}:
            selected.append(
                {
                    "id": row.get("id") or "",
                    "verdict": verdict,
                    "readyForExecution": False,
                }
            )
    return selected


def walkforward_summary(walkforward: dict[str, Any]) -> dict[str, Any]:
    configs = walkforward.get("configs") if isinstance(walkforward.get("configs"), list) else []
    config_summaries: list[dict[str, Any]] = []
    for config in configs:
        if not isinstance(config, dict):
            continue
        summary = config.get("summary") if isinstance(config.get("summary"), dict) else None
        if summary is None:
            summary = config.get("stitchedOos") if isinstance(config.get("stitchedOos"), dict) else config
        config_summaries.append(
            {
                "id": config.get("id") or config.get("configId") or "",
                "deployableWindows": int(as_number(summary.get("deployableWindows"))),
                "positiveWindows": int(as_number(summary.get("positiveWindows"))),
                "totalTrades": int(as_number(summary.get("totalTrades"))),
                "netR": round(as_number(summary.get("netR"), as_number(summary.get("netTotalR"))), 6),
                "profitFactor": round(as_number(summary.get("profitFactor")), 6),
            }
        )
    return {
        "status": walkforward.get("status") or walkforward.get("decision") or "",
        "deployable": False,
        "configs": config_summaries,
        "operatorRead": "Current walk-forward matrix is a rejection signal, not route evidence.",
    }


def hermes_memory_alignment(notes: dict[str, str]) -> dict[str, Any]:
    combined = "\n".join(notes.values()).lower()
    signals = {
        "zeroNewRisk": "zero_new_risk" in combined or "zero new risk" in combined,
        "researchHarnessNotExecutionEngine": "research harness" in combined and "execution engine" in combined,
        "sessionShadow": "session shadow" in combined,
        "firstTradeLearningData": "first trade" in combined and "learning data" in combined,
        "noTradeValid": "no-trade" in combined and "valid" in combined,
        "oneVariableOnly": "one-variable" in combined or "one variable" in combined,
        "brokerProofRequired": "broker" in combined and ("proof" in combined or "reconciled" in combined),
        "fiftyKPolicy": "50k" in combined and "100k" in combined,
    }
    missing = [name for name, present in signals.items() if not present]
    return {
        "sourceNotes": sorted(notes.keys()),
        "signals": signals,
        "missingSignals": missing,
        "operatorRead": (
            "Hermes' memory layer is aligned with the intended operating model when "
            "research harnesses stay separate from execution, every session becomes "
            "structured learning, and 100K demo context never overrides 50K sizing policy."
        ),
        "hermesInstruction": [
            "Keep the best strategy watches in Obsidian as research-only until promotion gates clear.",
            "For every Topstep/manual/demo trade, attach setup, session, news context, MAE/MFE, exit reason, and mistake tag.",
            "Convert mistake tags into one-variable research hypotheses, not direct execution changes.",
            "Retire rejected forms into no-edge memory before adding parameters or sizing overlays.",
        ],
    }


def build_research_queue(
    one_variable: dict[str, Any], entry: dict[str, Any], no_edge: dict[str, Any]
) -> list[dict[str, Any]]:
    queue = [
        {
            "id": "ny-morning-only-orb-breakout-15m-follow-up",
            "lane": "futures-nq",
            "status": "watch-only",
            "oneVariable": "walkforward PF and cost stress detail only",
            "source": "strategy-factory-one-variable-research",
            "readyForExecution": False,
        },
        {
            "id": "long-on-1m-red-candle-after-15m-bullish-signal",
            "lane": "futures-nq-entry-timing",
            "status": "needs-broker-grade-overlapping-1m-3m-15m-data",
            "oneVariable": "entry timing only",
            "source": "entry-hypothesis-research",
            "readyForExecution": False,
        },
        {
            "id": "daily-htf-regime-overlay",
            "lane": "futures-regime",
            "status": "not-yet-tested",
            "oneVariable": "daily/higher-timeframe regime tag only",
            "source": "user-thesis",
            "readyForExecution": False,
        },
        {
            "id": "pcr-vix-sector-leading-indicator-audit",
            "lane": "futures-leading-indicators",
            "status": "dataset-inventory-before-signal",
            "oneVariable": "leading-indicator confirmation only",
            "source": "brtnsmth-data-thesis",
            "readyForExecution": False,
        },
    ]

    no_edge_ids = {row.get("id") for row in no_edge_entries(no_edge) if row.get("verdict") == "no-edge"}
    if "entry-hypothesis-fakeout_retrace_filter_skip_large_upper_wick" in no_edge_ids:
        queue.append(
            {
                "id": "fakeout-filter-redesign",
                "lane": "futures-nq-entry-quality",
                "status": "current-form-retired",
                "oneVariable": "do not retest same fakeout filter without a new feature definition",
                "source": "futures-no-edge-ledger",
                "readyForExecution": False,
            }
        )

    if not best_one_variable_watch(one_variable).get("id"):
        queue[0]["status"] = "blocked-missing-one-variable-artifact"
    if not entry_watch(entry).get("id"):
        queue[1]["status"] = "blocked-missing-entry-artifact"
    return queue


def build_audit(
    *,
    build_plan_text: str,
    factory: dict[str, Any],
    one_variable: dict[str, Any],
    entry: dict[str, Any],
    no_edge: dict[str, Any],
    walkforward: dict[str, Any],
    build_plan_path: Path,
    hermes_notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    claim_review = [claim_status_from_factory(factory, no_edge)]
    if "Multi-TF entry" in build_plan_text or "multi-TF" in build_plan_text:
        claim_review.append(
            {
                "claim": "Multi-TF entry improves returns",
                "status": "research-watch-only",
                "contradictions": [
                    "requires-broker-grade-overlapping-lower-timeframe-data",
                    "requires-purged-oos-and-cost-stress",
                ],
                "operatorRead": (
                    "Keep daily/15m/30m direction separate from 1m/3m entry timing. "
                    "The lower timeframe may improve fills, but does not create route permission."
                ),
            }
        )

    return {
        "command": "adaptive-strategy-research-audit",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "decision": "research-only-adaptive-strategy-not-promotable",
        "researchOnly": True,
        "touchesBroker": False,
        "writesOrders": False,
        "movesFunds": False,
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "buildPlanPath": str(build_plan_path),
        "hermesMemoryAlignment": hermes_memory_alignment(hermes_notes or {}),
        "claimReview": claim_review,
        "currentBestWatches": [
            best_one_variable_watch(one_variable),
            entry_watch(entry),
        ],
        "walkforward": walkforward_summary(walkforward),
        "noEdgeMemory": {
            "decision": no_edge.get("decision") or "",
            "count": int(as_number(no_edge.get("count"))),
            "noEdgeCount": int(as_number(no_edge.get("noEdgeCount"))),
            "needsNewFeatureCount": int(as_number(no_edge.get("needsNewFeatureCount"))),
            "promotableCount": int(as_number(no_edge.get("promotableCount"))),
            "entries": no_edge_entries(no_edge),
        },
        "promotionDefinition": {
            "minimumOosTrades": 50,
            "minimumCostStressedProfitFactor": 1.25,
            "minimumPositiveFoldShare": 0.6,
            "requiresIndependentDatasetConfirmation": True,
            "requiresCurrentBrokerGradeParity": True,
            "requiresNoEdgeLedgerClearance": True,
            "requiresSessionAndRegimeLabel": True,
            "requiresOneVariableChangeOnly": True,
        },
        "researchQueue": build_research_queue(one_variable, entry, no_edge),
        "operatorRead": (
            "The intelligent path is conditional trading research: identify the "
            "session, regime, higher-timeframe context, and lower-timeframe entry "
            "condition where an edge appears, then reject it unless OOS, cost stress, "
            "coverage, and no-edge memory agree."
        ),
        "globalBlockers": [
            "research-only-artifact",
            "zero-promotable-profiles-in-current-ledger",
            "walkforward-matrix-rejects-current-configs",
            "no-broker-route-authority",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Adaptive Strategy Research Audit",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Research only: `{payload.get('researchOnly')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Writes orders: `{payload.get('writesOrders')}`",
        f"- Touches broker: `{payload.get('touchesBroker')}`",
        "",
        "## Claim Review",
        "",
    ]
    for claim in payload.get("claimReview") or []:
        lines.append(f"- `{claim.get('claim')}` -> `{claim.get('status')}`")
        read = claim.get("operatorRead")
        if read:
            lines.append(f"  - {read}")
        for blocker in claim.get("contradictions") or []:
            lines.append(f"  - `{blocker}`")

    lines.extend(["", "## Current Best Watches", ""])
    for watch in payload.get("currentBestWatches") or []:
        if not watch.get("id"):
            continue
        lines.append(
            f"- `{watch.get('id')}`: `{watch.get('status')}`, "
            f"OOS trades `{watch.get('oosTradeCount')}`, PF `{watch.get('oosProfitFactor')}`, "
            f"ready `{watch.get('readyForExecution')}`"
        )
        for blocker in watch.get("blockers") or []:
            lines.append(f"  - `{blocker}`")

    lines.extend(["", "## Promotion Definition", ""])
    for key, value in (payload.get("promotionDefinition") or {}).items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Research Queue", ""])
    for item in payload.get("researchQueue") or []:
        lines.append(
            f"- `{item.get('id')}`: `{item.get('status')}` | one variable: {item.get('oneVariable')}"
        )

    lines.extend(["", "## No-Edge Memory", ""])
    memory = payload.get("noEdgeMemory") or {}
    lines.append(
        f"- Count `{memory.get('count')}`, no-edge `{memory.get('noEdgeCount')}`, "
        f"needs-new-feature `{memory.get('needsNewFeatureCount')}`, promotable `{memory.get('promotableCount')}`"
    )
    lines.extend(["", "## Hermes Memory Alignment", ""])
    alignment = payload.get("hermesMemoryAlignment") or {}
    signals = alignment.get("signals") or {}
    for key, value in signals.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    for instruction in alignment.get("hermesInstruction") or []:
        lines.append(f"- {instruction}")
    lines.extend(["", payload.get("operatorRead") or "", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build adaptive strategy research truth table.")
    parser.add_argument("--build-plan", default=str(DEFAULT_BUILD_PLAN))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--research-output", default=str(DEFAULT_RESEARCH_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    build_plan_path = Path(args.build_plan)
    payload = build_audit(
        build_plan_text=read_text(build_plan_path),
        hermes_notes={name: read_text(path) for name, path in DEFAULT_HERMES_NOTES.items()},
        build_plan_path=build_plan_path,
        factory=read_json(STATE / "strategy-factory.latest.json"),
        one_variable=read_json(STATE / "strategy-factory-one-variable-research.latest.json"),
        entry=read_json(STATE / "entry-hypothesis-research.latest.json"),
        no_edge=read_json(ROOT / ".rumbling-hedge" / "research" / "futures-no-edge-ledger" / "latest.json"),
        walkforward=read_json(STATE / "walkforward-matrix.latest.json"),
    )

    for output_path in [Path(args.output), Path(args.research_output)]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload), encoding="utf-8")

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
