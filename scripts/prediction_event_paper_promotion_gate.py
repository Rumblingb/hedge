#!/usr/bin/env python3
"""Deterministic paper-promotion gate for prediction event-lag research.

This is a read-only gate. It combines the scattered prediction-market
artifacts into one promotion decision so future agents cannot confuse forward
capture progress with paper readiness.
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
OUT = STATE / "prediction-event-paper-promotion-gate.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"prediction-event-paper-promotion-gate-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def check(
    *,
    item_id: str,
    requirement: str,
    passed: bool,
    evidence: dict[str, Any],
    blocker: str | None = None,
) -> dict[str, Any]:
    row = {
        "id": item_id,
        "requirement": requirement,
        "status": "pass" if passed else "blocked",
        "evidence": evidence,
    }
    if blocker and not passed:
        row["blocker"] = blocker
    return row


def build_gate(
    *,
    capture_cycle: dict[str, Any],
    manual_review: dict[str, Any],
    event_requirements: dict[str, Any],
    event_label_gap_plan: dict[str, Any],
    resolved_join: dict[str, Any],
    label_manifest: dict[str, Any],
    market_mapping: dict[str, Any],
    mapping_refinement: dict[str, Any],
    clob_microstructure: dict[str, Any],
    clob_edge_gate: dict[str, Any],
) -> dict[str, Any]:
    executed_recorder = (
        capture_cycle.get("executedRecorder")
        if isinstance(capture_cycle.get("executedRecorder"), dict)
        else {}
    )
    latest_recorder = (
        capture_cycle.get("latestRecorder")
        if isinstance(capture_cycle.get("latestRecorder"), dict)
        else {}
    )
    recorder_safe = (
        executed_recorder.get("publicMarketDataOnly") is True
        and executed_recorder.get("writesOrders") is False
        and executed_recorder.get("touchesBroker") is False
    )
    live_quality = (
        latest_recorder.get("liveQualityDiagnostics")
        if isinstance(latest_recorder.get("liveQualityDiagnostics"), dict)
        else {}
    )
    fillable_live_book_count = int(live_quality.get("fillableLiveBookCount") or 0)
    safe_public_capture_present = recorder_safe and fillable_live_book_count > 0
    complete_window_count = int(capture_cycle.get("completeWindowCount") or 0)
    repriced_window_count = int(capture_cycle.get("repricedWindowCount") or 0)
    capture_passed = (
        capture_cycle.get("captureCycleEvidencePassed") is True
        and recorder_safe
        and complete_window_count > 0
        and repriced_window_count > 0
    )
    manual_watch_count = int((manual_review.get("decisionCounts") or {}).get("keep-watch") or 0)
    manual_gate_passed = (
        manual_review.get("decision") == "research-only-manual-review-watch"
        and manual_watch_count > 0
        and manual_review.get("forwardCaptureEvidencePresent") is True
        and manual_review.get("writesOrders") is False
        and manual_review.get("touchesBroker") is False
    )
    event_requirements_passed = (
        event_requirements.get("blockedCount") == 0
        and bool(event_requirements)
        and event_requirements.get("researchOnly") is True
    )
    label_gap_passed = (
        bool(event_label_gap_plan)
        and int(event_label_gap_plan.get("gapCount") or 0) == 0
        and int(event_label_gap_plan.get("eventMappedGapCount") or 0) == 0
        and not as_list(event_label_gap_plan.get("blockedRequirements"))
    )
    no_lookahead_passed = (
        capture_cycle.get("paperPromotionEvidencePassed") is True
        and event_requirements_passed
        and label_gap_passed
    )
    resolved_label_passed = (
        resolved_join.get("readyForPaper") is True
        and int(resolved_join.get("joinedResearchOnlyCount") or 0) > 0
        and label_manifest.get("readyForPaper") is True
    )
    mapping_passed = (
        market_mapping.get("readyForPaper") is True
        and mapping_refinement.get("readyForPaper") is True
        and not as_list(market_mapping.get("blockers"))
        and not as_list(mapping_refinement.get("blockers"))
        and int(market_mapping.get("ambiguousHeadlineCount") or 0) == 0
        and int(market_mapping.get("ambiguousCounterpartyHeadlineCount") or 0) == 0
    )
    microstructure_passed = (
        clob_microstructure.get("readyForPaper") is True
        and int(clob_microstructure.get("readyFeatureCount") or 0) > 0
        and clob_edge_gate.get("readyForPaper") is True
        and int(clob_edge_gate.get("watchResearchGroups") or 0) > 0
    )
    safety_passed = (
        capture_cycle.get("researchOnly") is True
        and capture_cycle.get("writesOrders") is False
        and capture_cycle.get("touchesBroker") is False
        and latest_recorder.get("writesOrders", False) is False
        and manual_review.get("writesOrders") is False
        and manual_review.get("touchesBroker") is False
        and clob_edge_gate.get("writesOrders", False) is False
        and clob_edge_gate.get("touchesBroker", False) is False
    )
    if capture_passed:
        forward_capture_blocker = None
    elif safe_public_capture_present:
        forward_capture_blocker = "safe public CLOB capture observed fillable books, but no no-lookahead repriced complete event window exists yet"
    elif recorder_safe:
        forward_capture_blocker = "public CLOB recorder was safe, but no fillable live book or repriced complete event window was observed"
    else:
        forward_capture_blocker = "public CLOB capture is missing or unsafe"

    checklist = [
        check(
            item_id="forward-public-clob-capture",
            requirement="Forward capture must include public CLOB quotes for the reviewed token with no order or broker access.",
            passed=capture_passed,
            evidence={
                "captureCycleEvidencePassed": capture_cycle.get("captureCycleEvidencePassed"),
                "completeWindowCount": complete_window_count,
                "repricedWindowCount": repriced_window_count,
                "recorderSafe": recorder_safe,
                "safePublicCapturePresent": safe_public_capture_present,
                "fillableLiveBookCount": fillable_live_book_count,
                "liveQualityStatusCounts": live_quality.get("statusCounts") if isinstance(live_quality.get("statusCounts"), dict) else {},
                "executedRecorder": executed_recorder,
            },
            blocker=forward_capture_blocker,
        ),
        check(
            item_id="manual-review-watch",
            requirement="A separate manual review must preserve at least one watch window after forward capture.",
            passed=manual_gate_passed,
            evidence={
                "decision": manual_review.get("decision"),
                "decisionCounts": manual_review.get("decisionCounts"),
                "forwardCaptureEvidencePresent": manual_review.get("forwardCaptureEvidencePresent"),
                "blockers": as_list(manual_review.get("blockers")),
            },
            blocker="manual review has not cleared even a research watch window after forward capture",
        ),
        check(
            item_id="no-lookahead-event-window",
            requirement="Paper discussion needs no-lookahead event windows with all event-lag requirements and label-gap requirements clear.",
            passed=no_lookahead_passed,
            evidence={
                "paperPromotionEvidencePassed": capture_cycle.get("paperPromotionEvidencePassed"),
                "paperPromotionBlockers": as_list(capture_cycle.get("paperPromotionBlockers")),
                "eventRequirementsDecision": event_requirements.get("decision"),
                "eventRequirementsBlockedCount": event_requirements.get("blockedCount"),
                "eventLabelGapDecision": event_label_gap_plan.get("decision"),
                "blockedRequirements": as_list(event_label_gap_plan.get("blockedRequirements")),
            },
            blocker="event windows are still research-only; no-lookahead paper-promotion evidence has not passed",
        ),
        check(
            item_id="resolved-label-paper-coverage",
            requirement="Resolved labels must be paper-grade, subject-specific, and joined to comparable market families.",
            passed=resolved_label_passed,
            evidence={
                "resolvedJoinDecision": resolved_join.get("decision"),
                "resolvedJoinReadyForPaper": resolved_join.get("readyForPaper"),
                "joinedResearchOnlyCount": resolved_join.get("joinedResearchOnlyCount"),
                "statusCounts": resolved_join.get("statusCounts"),
                "labelManifestDecision": label_manifest.get("decision"),
                "labelManifestReadyForPaper": label_manifest.get("readyForPaper"),
                "usableForResearchJoinCount": label_manifest.get("usableForResearchJoinCount"),
            },
            blocker="resolved labels are usable for research context only, not paper promotion",
        ),
        check(
            item_id="event-market-mapping-clean",
            requirement="Headline-to-market mapping must be unambiguous before any paper candidate exists.",
            passed=mapping_passed,
            evidence={
                "mappingDecision": market_mapping.get("decision"),
                "mappingReadyForPaper": market_mapping.get("readyForPaper"),
                "ambiguousHeadlineCount": market_mapping.get("ambiguousHeadlineCount"),
                "ambiguousCounterpartyHeadlineCount": market_mapping.get("ambiguousCounterpartyHeadlineCount"),
                "mappingBlockers": as_list(market_mapping.get("blockers")),
                "refinementDecision": mapping_refinement.get("decision"),
                "refinementReadyForPaper": mapping_refinement.get("readyForPaper"),
                "refinementBlockers": as_list(mapping_refinement.get("blockers")),
            },
            blocker="event-to-market mapping remains ambiguous",
        ),
        check(
            item_id="post-spread-clob-edge",
            requirement="CLOB microstructure edge must survive spread/fillability stress with at least one ready feature.",
            passed=microstructure_passed,
            evidence={
                "microstructureDecision": clob_microstructure.get("decision"),
                "readyFeatureCount": clob_microstructure.get("readyFeatureCount"),
                "clobEdgeStatus": clob_edge_gate.get("status"),
                "watchResearchGroups": clob_edge_gate.get("watchResearchGroups"),
                "readyForPaper": clob_edge_gate.get("readyForPaper"),
                "blockerCounts": clob_edge_gate.get("blockerCounts"),
            },
            blocker="current CLOB feature family has no post-spread paper-grade edge",
        ),
        check(
            item_id="research-safety-locks",
            requirement="The promotion gate must remain read-only: no orders, broker access, or funding side effects.",
            passed=safety_passed,
            evidence={
                "captureWritesOrders": capture_cycle.get("writesOrders"),
                "captureTouchesBroker": capture_cycle.get("touchesBroker"),
                "manualWritesOrders": manual_review.get("writesOrders"),
                "manualTouchesBroker": manual_review.get("touchesBroker"),
                "clobWritesOrders": clob_edge_gate.get("writesOrders"),
                "clobTouchesBroker": clob_edge_gate.get("touchesBroker"),
            },
            blocker="one or more input artifacts is not explicitly read-only",
        ),
    ]
    blockers = [
        str(row["blocker"])
        for row in checklist
        if row.get("status") != "pass" and row.get("blocker")
    ]
    ready_for_paper = not blockers
    return {
        "command": "prediction-event-paper-promotion-gate",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForPaper": ready_for_paper,
        "readyForPaperReview": ready_for_paper,
        "decision": "paper-promotion-review-ready" if ready_for_paper else "research-only-paper-promotion-blocked",
        "passCount": sum(1 for row in checklist if row["status"] == "pass"),
        "blockedCount": sum(1 for row in checklist if row["status"] != "pass"),
        "blockedIds": [row["id"] for row in checklist if row["status"] != "pass"],
        "blockers": blockers,
        "checklist": checklist,
        "operatorRead": (
            "Forward CLOB capture can justify continued research only. Paper promotion requires every listed gate to pass."
            if blockers
            else "Paper-review evidence is complete, but this artifact still does not approve live execution or broker routing."
        ),
        "nextAction": (
            "Continue forward public CLOB capture and fix no-lookahead labels, mapping, and post-spread edge evidence before paper discussion."
            if blockers
            else "Run a separate paper-review note and keep execution/funding disabled."
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_at = str(payload.get("generatedAt") or "")
    gate_date = generated_at[:10] if len(generated_at) >= 10 else current_utc_date()
    lines = [
        f"# Prediction Event Paper Promotion Gate - {gate_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "This is a read-only promotion gate. It does not approve funding, orders, broker routing, demo, or live execution.",
        "",
        "## Decision",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Ready for paper review: `{payload.get('readyForPaperReview')}`",
        f"- Pass count: `{payload.get('passCount')}`",
        f"- Blocked ids: `{payload.get('blockedIds')}`",
        f"- Operator read: {payload.get('operatorRead')}",
        "",
        "## Checks",
        "",
    ]
    for row in payload.get("checklist") or []:
        lines.append(f"### {row.get('id')}")
        lines.append("")
        lines.append(f"- Status: `{row.get('status')}`")
        lines.append(f"- Requirement: {row.get('requirement')}")
        if row.get("blocker"):
            lines.append(f"- Blocker: {row.get('blocker')}")
        lines.append("")
    lines.extend(["## Next Action", "", f"- {payload.get('nextAction')}", ""])
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build the prediction event-lag paper-promotion gate.")
    p.add_argument("--capture-cycle", default=str(STATE / "prediction-event-capture-cycle.latest.json"))
    p.add_argument("--manual-review", default=str(STATE / "prediction-event-lag-manual-review.latest.json"))
    p.add_argument("--event-requirements", default=str(STATE / "prediction-event-lag-requirements.latest.json"))
    p.add_argument("--event-label-gap-plan", default=str(STATE / "prediction-event-label-gap-plan.latest.json"))
    p.add_argument("--resolved-join", default=str(STATE / "prediction-resolved-outcome-join.latest.json"))
    p.add_argument("--label-manifest", default=str(STATE / "prediction-label-source-manifest.latest.json"))
    p.add_argument("--market-mapping", default=str(STATE / "prediction-event-market-mapping-plan.latest.json"))
    p.add_argument("--mapping-refinement", default=str(STATE / "prediction-event-mapping-refinement.latest.json"))
    p.add_argument("--clob-microstructure", default=str(STATE / "prediction-clob-microstructure-feature-audit.latest.json"))
    p.add_argument("--clob-edge-gate", default=str(STATE / "polymarket-clob-edge-gate.latest.json"))
    p.add_argument("--output", default=str(OUT))
    p.add_argument("--markdown", default=str(default_markdown_path()))
    return p


def main() -> int:
    args = parser().parse_args()
    payload = build_gate(
        capture_cycle=read_json(Path(args.capture_cycle)),
        manual_review=read_json(Path(args.manual_review)),
        event_requirements=read_json(Path(args.event_requirements)),
        event_label_gap_plan=read_json(Path(args.event_label_gap_plan)),
        resolved_join=read_json(Path(args.resolved_join)),
        label_manifest=read_json(Path(args.label_manifest)),
        market_mapping=read_json(Path(args.market_mapping)),
        mapping_refinement=read_json(Path(args.mapping_refinement)),
        clob_microstructure=read_json(Path(args.clob_microstructure)),
        clob_edge_gate=read_json(Path(args.clob_edge_gate)),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if args.markdown:
        markdown = Path(args.markdown)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
