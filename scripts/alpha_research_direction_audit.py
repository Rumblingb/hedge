#!/usr/bin/env python3
"""Audit whether Bill/Hermes research is pointed at useful alpha lanes.

This is research-only. It reads the current seed triage, no-edge ledgers,
frontier queue, and promotion blockers, then emits a compact direction note:
what to continue, what to retire/quarantine, and the next one-variable test.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
RESEARCH = ROOT / ".rumbling-hedge" / "research"
VAULT = Path.home() / "Documents" / "memorybrain"
HERMES = VAULT / "Agent-Hermes"
OUT = STATE / "alpha-research-direction-audit.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"alpha-research-direction-audit-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def action_by_id(next_actions: dict[str, Any], action_id: str) -> dict[str, Any]:
    for item in rows(next_actions.get("actions")):
        if item.get("id") == action_id:
            return item
    return {}


def no_edge_entries(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    return rows(ledger.get("entries"))


def no_edge_ids(ledger: dict[str, Any]) -> set[str]:
    return {
        str(item.get("id"))
        for item in no_edge_entries(ledger)
        if item.get("id") and str(item.get("verdict") or "") in {"no-edge", "needs-new-feature"}
    }


def command_safe(action: dict[str, Any]) -> bool:
    commands = [str(command).lower() for command in (action.get("commands") if isinstance(action.get("commands"), list) else [])]
    banned_fragments = (
        "fund-and-trade",
        "deposit-clob",
        "deposit-simple",
        "swap-and-fund",
        "bill:prediction-execute",
        "pm-auto-execute",
    )
    return (
        action.get("writesOrders") is not True
        and action.get("touchesBroker") is not True
        and not any(any(term in command for term in banned_fragments) for command in commands)
    )


def build_audit(
    *,
    seed_triage: dict[str, Any],
    alpha_frontier: dict[str, Any],
    next_actions: dict[str, Any],
    futures_no_edge: dict[str, Any],
    prediction_no_edge: dict[str, Any],
    futures_cycle: dict[str, Any],
    prediction_gate: dict[str, Any],
    source_intake: dict[str, Any],
) -> dict[str, Any]:
    seed_summary = seed_triage.get("summary") if isinstance(seed_triage.get("summary"), dict) else {}
    frontier_items = rows(alpha_frontier.get("frontier"))
    if not frontier_items:
        frontier_items = rows(alpha_frontier.get("items"))
    actions = rows(next_actions.get("actions"))
    action_ids = {str(action.get("id")) for action in actions if action.get("id")}
    futures_rejected = no_edge_ids(futures_no_edge)
    prediction_rejected = no_edge_ids(prediction_no_edge)

    futures_source_action = action_by_id(next_actions, "futures-paid-nq-1m-session-structure-oos")
    options_action = action_by_id(next_actions, "futures-options-regime-risk-overlay")
    event_lag_action = action_by_id(next_actions, "prediction-news-first-event-lag-study") or action_by_id(
        next_actions,
        "prediction-event-mapping-refinement-after-manual-review",
    )

    continue_lanes = []
    if futures_source_action:
        continue_lanes.append({
            "id": "futures-paid-nq-session-structure",
            "rank": 1,
            "reason": "Best current futures lane: it changes data source/cadence before changing strategy parameters, and it keeps current/broker parity as a blocker.",
            "oneVariable": futures_source_action.get("oneVariable"),
            "firstCommand": futures_source_action.get("firstCommand"),
            "dataPaths": futures_source_action.get("dataPaths") if isinstance(futures_source_action.get("dataPaths"), list) else [],
            "readyForExecution": False,
        })
    if event_lag_action:
        continue_lanes.append({
            "id": "prediction-news-event-lag-forward-clob",
            "rank": 2,
            "reason": "Best current prediction lane: it treats news as leading information and uses public CLOB capture as evidence, while the paper-promotion gate remains blocked.",
            "oneVariable": event_lag_action.get("oneVariable"),
            "firstCommand": event_lag_action.get("firstCommand"),
            "paperPromotionGate": {
                "decision": prediction_gate.get("decision"),
                "blockedIds": prediction_gate.get("blockedIds") if isinstance(prediction_gate.get("blockedIds"), list) else [],
            },
            "readyForExecution": False,
        })
    if options_action:
        continue_lanes.append({
            "id": "futures-options-regime-risk-overlay",
            "rank": 3,
            "reason": "Worth keeping only as a risk overlay; it should not create entries and must improve OOS drawdown/expectancy without shrinking sample too far.",
            "oneVariable": options_action.get("oneVariable"),
            "firstCommand": options_action.get("firstCommand"),
            "readyForExecution": False,
        })

    rejected_counter = Counter()
    for item in no_edge_entries(futures_no_edge) + no_edge_entries(prediction_no_edge):
        rejected_counter[str(item.get("id") or "unknown")] += 1
    retire_lanes = [
        {
            "id": "generic-yt-gold-strategy-reruns",
            "reason": "Research seed triage has zero next-build items and many duplicate/YT seeds; do not retest narrative labels until transcripts become explicit rules and one-variable OOS plans.",
            "evidence": {
                "queuedYouTubeSeeds": seed_summary.get("queuedYouTubeSeeds"),
                "nextBuildQueueCount": len(rows(seed_triage.get("nextBuildQueue"))),
                "duplicateSourceIds": seed_summary.get("duplicateSourceIds"),
            },
        },
        {
            "id": "current-fixed-prediction-clob-forms",
            "reason": "Current CLOB drift/microstructure forms are rejected; do not loosen thresholds to manufacture paper candidates.",
            "evidence": {
                "predictionNoEdgeCount": prediction_no_edge.get("noEdgeCount"),
                "promotableCount": prediction_no_edge.get("promotableCount"),
                "rejectedIds": sorted(list(prediction_rejected))[:8],
            },
        },
        {
            "id": "current-futures-wq-orb-parameter-sweeps",
            "reason": "Backtrader/full-sample survivors are not enough; OOS/cost/live-readiness artifacts reject current deployability.",
            "evidence": {
                "futuresNoEdgeCount": futures_no_edge.get("noEdgeCount"),
                "promotableCount": futures_no_edge.get("promotableCount"),
                "cycleBlockers": futures_cycle.get("blockers") if isinstance(futures_cycle.get("blockers"), list) else [],
                "rejectedIds": sorted(list(futures_rejected))[:8],
            },
        },
    ]

    missing_evidence = [
        {
            "id": "futures-open-session-current-parity",
            "why": "Futures demo cannot expand until current/broker parity and execution-grade realtime data pass during an open session.",
            "artifact": ".rumbling-hedge/state/futures-broker-parity-plan.latest.json",
        },
        {
            "id": "prediction-paper-promotion-gate",
            "why": "Prediction research has forward CLOB watch evidence, but paper promotion remains blocked by no-lookahead, labels, mapping, and post-spread edge.",
            "artifact": ".rumbling-hedge/state/prediction-event-paper-promotion-gate.latest.json",
        },
        {
            "id": "source-hygiene-clearance",
            "why": "Research code can continue, but demo/live readiness cannot be called clean while source and execution-live files remain dirty.",
            "artifact": ".rumbling-hedge/state/bill-source-intake-manifest.latest.json",
        },
    ]

    next_test = {
        "id": "futures-paid-nq-session-structure-oos",
        "lane": "futures",
        "oneVariable": "data source/cadence only",
        "command": futures_source_action.get("firstCommand") or "npm run --silent bill:external-alpha-data-audit",
        "fullCommandSequence": futures_source_action.get("commands") if isinstance(futures_source_action.get("commands"), list) else [],
        "successCriteria": [
            "historical replay has enough OOS trades",
            "walk-forward and cost/slippage stress stay positive",
            "current/local/broker parity remains explicitly separated from historical evidence",
            "no execution flags are enabled",
        ],
        "rejectionCriteria": [
            "edge only appears in full-sample or tiny OOS windows",
            "improvement comes from changing multiple variables",
            "no overlap with current local/broker bars is misread as demo evidence",
        ],
    }

    if prediction_gate.get("decision") == "research-only-paper-promotion-blocked":
        next_test["parallelWatch"] = {
            "id": "prediction-forward-public-clob-capture",
            "oneVariable": "capture duration/window only",
            "command": "npm run --silent bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15 --max-output-mb 128 --min-free-gb 20",
            "blockedBy": prediction_gate.get("blockedIds") if isinstance(prediction_gate.get("blockedIds"), list) else [],
        }

    queue_safe = (
        next_actions.get("researchOnly") is True
        and next_actions.get("writesOrders") is False
        and next_actions.get("touchesBroker") is False
        and all(command_safe(action) for action in actions)
    )
    ready_for_research_loop = queue_safe and bool(continue_lanes) and bool(next_test)
    payload = {
        "command": "alpha-research-direction-audit",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "readyForResearchLoop": ready_for_research_loop,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "readyForPaper": False,
        "decision": "research-direction-clear-execution-locked" if queue_safe else "research-direction-needs-command-review",
        "queueSafe": queue_safe,
        "seedSummary": seed_summary,
        "frontierCount": len(frontier_items),
        "actionCount": len(actions),
        "actionIds": sorted(action_ids),
        "continueLanes": continue_lanes,
        "retireOrQuarantineLanes": retire_lanes,
        "missingEvidence": missing_evidence,
        "nextOneVariableTest": next_test,
        "hardRules": [
            "Do not rerun rejected current forms by loosening thresholds.",
            "Treat YT/paper/social gold as hypothesis seed only until rules, implementation, OOS, cost, and promotion gates pass.",
            "LLMs may summarize and rank research, but deterministic code owns execution gates.",
        ],
        "sourceHygiene": {
            "sourceClean": source_intake.get("sourceClean"),
            "dirtyStatusCount": source_intake.get("dirtyStatusCount"),
            "reviewBacklogCount": source_intake.get("reviewBacklogCount"),
            "executionLiveDirtyCount": source_intake.get("executionLiveDirtyCount"),
        },
    }
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    generated_at = str(payload.get("generatedAt") or "")
    audit_date = generated_at[:10] if len(generated_at) >= 10 else current_utc_date()
    lines = [
        f"# Alpha Research Direction Audit - {audit_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "This is a research-only direction note. It does not approve paper, demo, live, funding, orders, sizing, or broker routing.",
        "",
        "## Decision",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Queue safe: `{payload.get('queueSafe')}`",
        f"- Ready for research loop: `{payload.get('readyForResearchLoop')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        "",
        "## Continue",
        "",
    ]
    for item in payload.get("continueLanes") or []:
        lines.append(f"- `{item.get('id')}`: {item.get('reason')}")
    lines.extend(["", "## Retire Or Quarantine", ""])
    for item in payload.get("retireOrQuarantineLanes") or []:
        lines.append(f"- `{item.get('id')}`: {item.get('reason')}")
    lines.extend(["", "## Next One-Variable Test", ""])
    next_test = payload.get("nextOneVariableTest") if isinstance(payload.get("nextOneVariableTest"), dict) else {}
    lines.append(f"- `{next_test.get('id')}` one variable `{next_test.get('oneVariable')}`")
    lines.append(f"- First command: `{next_test.get('command')}`")
    lines.extend(["", "## Missing Evidence", ""])
    for item in payload.get("missingEvidence") or []:
        lines.append(f"- `{item.get('id')}`: {item.get('why')}")
    lines.append("")
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Audit Bill/Hermes alpha research direction.")
    p.add_argument("--seed-triage", default=str(STATE / "research-seed-triage.latest.json"))
    p.add_argument("--alpha-frontier", default=str(STATE / "alpha-frontier-queue.latest.json"))
    p.add_argument("--next-actions", default=str(STATE / "bill-next-research-actions.latest.json"))
    p.add_argument("--futures-no-edge", default=str(RESEARCH / "futures-no-edge-ledger/latest.json"))
    p.add_argument("--prediction-no-edge", default=str(RESEARCH / "prediction-no-edge-ledger/latest.json"))
    p.add_argument("--futures-cycle", default=str(STATE / "futures-nq-research-cycle.latest.json"))
    p.add_argument("--prediction-paper-gate", default=str(STATE / "prediction-event-paper-promotion-gate.latest.json"))
    p.add_argument("--source-intake", default=str(STATE / "bill-source-intake-manifest.latest.json"))
    p.add_argument("--output", default=str(OUT))
    p.add_argument("--markdown", default=str(default_markdown_path()))
    return p


def main() -> int:
    args = parser().parse_args()
    payload = build_audit(
        seed_triage=read_json(Path(args.seed_triage)),
        alpha_frontier=read_json(Path(args.alpha_frontier)),
        next_actions=read_json(Path(args.next_actions)),
        futures_no_edge=read_json(Path(args.futures_no_edge)),
        prediction_no_edge=read_json(Path(args.prediction_no_edge)),
        futures_cycle=read_json(Path(args.futures_cycle)),
        prediction_gate=read_json(Path(args.prediction_paper_gate)),
        source_intake=read_json(Path(args.source_intake)),
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
