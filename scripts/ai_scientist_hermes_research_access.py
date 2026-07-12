#!/usr/bin/env python3
"""Build a Hermes-facing AI-Scientist research access packet.

Hermes and cheaper models can help propose one-variable strategy ideas, but the
deterministic AI-Scientist runner remains the evaluator. This script summarizes
current 5m/15m/30m/3m evidence, automation posture, and the allowed research
commands without approving demo/live execution.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
AI_TEMPLATE = ROOT / "ai-scientist-templates" / "financial_strategy"
HERMES = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "ai-scientist-hermes-research-access.latest.json"


TIMEFRAME_RUNS = {
    "5m-legacy-orb": AI_TEMPLATE / "test_run" / "final_info.json",
    "15m-legacy-orb": AI_TEMPLATE / "test_run_15m" / "final_info.json",
    "30m-legacy-orb": AI_TEMPLATE / "test_run_30m" / "final_info.json",
    "3m-nq-orb": AI_TEMPLATE / "test_run_3m_orb_2026_06_06" / "final_info.json",
    "3m-es-orb": AI_TEMPLATE / "test_run_3m_es_orb_2026_06_06" / "final_info.json",
    "known-baselines": AI_TEMPLATE / "test_run_known_baselines_2026_06_06_132026" / "final_info.json",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"ai-scientist-hermes-research-access-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def template_payload(path: Path) -> dict[str, Any]:
    return read_json(path).get("AlphaStrategyTemplate", {})


def safety_ok(safety: dict[str, Any]) -> bool:
    return bool(safety.get("research_only")) and not any(
        bool(safety.get(key))
        for key in ("writes_orders", "touches_broker", "moves_funds")
    )


def summarize_direct_run(run_id: str, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    experiment = payload.get("experiment") if isinstance(payload.get("experiment"), dict) else {}
    means = payload.get("means") if isinstance(payload.get("means"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    return {
        "id": run_id,
        "path": str(path),
        "exists": path.exists(),
        "safetyOk": safety_ok(safety),
        "strategy": experiment.get("strategy"),
        "timeframe": experiment.get("timeframe"),
        "symbol": experiment.get("symbol"),
        "decision": experiment.get("decision"),
        "rawTradeCount": experiment.get("raw_trade_count"),
        "keptTradeCount": (experiment.get("gate") or {}).get("kept") if isinstance(experiment.get("gate"), dict) else None,
        "oosTradeCount": means.get("oos_trade_count"),
        "oosNetPoints": means.get("oos_total_net_points"),
        "oosProfitFactor": means.get("oos_profit_factor"),
        "oosWinRate": means.get("oos_win_rate"),
        "walkforwardPositiveFoldShare": means.get("walkforward_positive_fold_share"),
        "metricBlockers": experiment.get("metric_blockers") if isinstance(experiment.get("metric_blockers"), list) else [],
        "readyForPaper": bool(means.get("ready_for_paper")),
        "readyForExecution": bool(means.get("ready_for_execution")),
    }


def summarize_known_baselines(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    experiment = payload.get("experiment") if isinstance(payload.get("experiment"), dict) else {}
    rows = experiment.get("baseline_results") if isinstance(experiment.get("baseline_results"), list) else []
    summaries = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        baseline = row.get("baseline") if isinstance(row.get("baseline"), dict) else {}
        summaries.append(summarize_direct_run(
            str(baseline.get("id") or "unknown-baseline"),
            path,
            {
                "safety": payload.get("safety", {}),
                "means": row.get("means", {}),
                "experiment": row.get("experiment", {}),
            },
        ))
    return summaries


def classify_research_posture(summary: dict[str, Any]) -> str:
    blockers = summary.get("metricBlockers") or []
    if summary.get("readyForExecution"):
        return "invalid-output-review"
    if summary.get("decision") == "research-only-template-candidate" and not blockers:
        return "watch-research-candidate"
    if summary.get("oosTradeCount") in (None, 0) or (isinstance(summary.get("oosTradeCount"), int) and summary["oosTradeCount"] < 10):
        return "thin-or-no-edge"
    if "oos-net-not-positive-after-costs" in blockers or "oos-profit-factor-too-low" in blockers:
        return "blocked-no-edge-current-settings"
    return "blocked-watch-only"


def strategy_evidence() -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for run_id, path in TIMEFRAME_RUNS.items():
        payload = template_payload(path)
        if run_id == "known-baselines":
            summaries.extend(summarize_known_baselines(path, payload))
        else:
            summaries.append(summarize_direct_run(run_id, path, payload))
    for summary in summaries:
        summary["researchPosture"] = classify_research_posture(summary)
    return summaries


def load_automation_posture() -> dict[str, Any]:
    audit = read_json(STATE / "codex-automation-audit.latest.json")
    return {
        "path": str(STATE / "codex-automation-audit.latest.json"),
        "decision": audit.get("decision"),
        "status": audit.get("status"),
        "activeBillAutomationCount": audit.get("activeBillAutomationCount"),
        "activeFuturesOpenSessionProofIds": audit.get("activeFuturesOpenSessionProofIds") or [],
        "activePredictionCaptureIds": audit.get("activePredictionCaptureIds") or [],
        "pausedPredictionCaptureIds": audit.get("pausedPredictionCaptureIds") or [],
        "blockers": audit.get("blockers") if isinstance(audit.get("blockers"), list) else [],
        "researchOnly": bool(audit.get("researchOnly")),
        "readyForExecution": bool(audit.get("readyForExecution")),
    }


def build_packet() -> dict[str, Any]:
    evidence = strategy_evidence()
    automation = load_automation_posture()
    unsafe_outputs = [row["id"] for row in evidence if row.get("readyForExecution") or not row.get("safetyOk")]
    watch = [row for row in evidence if row["researchPosture"] == "watch-research-candidate"]
    blocked_watch = [row for row in evidence if row["researchPosture"] == "blocked-watch-only"]
    no_edge = [row for row in evidence if row["researchPosture"] in {"blocked-no-edge-current-settings", "thin-or-no-edge"}]
    return {
        "command": "ai-scientist-hermes-research-access",
        "generatedAt": now_iso(),
        "decision": "hermes-ai-scientist-research-access-ready" if not unsafe_outputs else "hermes-ai-scientist-access-review-required",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForPaper": False,
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "unsafeOutputIds": unsafe_outputs,
        "automationPosture": automation,
        "strategyEvidence": evidence,
        "portfolioRead": {
            "watchResearchCandidates": [row["id"] for row in watch],
            "blockedWatchOnly": [row["id"] for row in blocked_watch],
            "noEdgeOrThinCurrentSettings": [row["id"] for row in no_edge],
        },
        "hermesAccessPolicy": {
            "allowed": [
                "summarize final_info.json and state artifacts",
                "propose one-variable seed ideas",
                "run deterministic local research commands under lock env",
                "write research-only Obsidian notes",
            ],
            "forbidden": [
                "enable BILL_ENABLE_FUTURES_DEMO_EXECUTION",
                "set RH_TOPSTEP_READ_ONLY=false",
                "write orders or route broker signals",
                "mark paper/demo/live readiness",
                "relax gates and call the result deployable",
            ],
            "cheapModelUse": (
                "Cheaper models may draft one-variable hypotheses and summarize outputs. "
                "The Python template and goal/command gates remain the judge."
            ),
        },
        "safeCommands": [
            "npm run --silent bill:ai-scientist-data-access-audit",
            "npm run --silent bill:strategy-factory-one-variable-research",
            (
                "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true "
                "RH_LIVE_EXECUTION_ENABLED=false .venv/bin/python "
                "ai-scientist-templates/financial_strategy/experiment.py "
                "--strategy orb --timeframe 3m --sessions ny_morning,ny_afternoon "
                "--skip_sessions london,premarket --range_window_bars 10 --hold_bars 10 "
                "--volume_threshold 1.3 --entry_offset_ticks 8 --min_timeframe_agreement 2 "
                "--agreement_timeframes 15m,30m,60m --max_trades_per_session 3"
            ),
        ],
        "nextOneVariableResearch": [
            "Stress NQ 3m ORB by year/regime and by higher cost/slippage.",
            "Run long-vs-short asymmetry for 3m ORB and 15m NY-morning ORB.",
            "Add one ALL-6MARKETS cross-asset profile without changing strategy rules.",
            "Keep ES 3m ORB in no-edge memory for the current configuration.",
        ],
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        f"# AI-Scientist Hermes Research Access - {str(packet.get('generatedAt') or current_utc_date())[:10]}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        f"- Decision: `{packet.get('decision')}`",
        f"- Ready for execution: `{packet.get('readyForExecution')}`",
        f"- Writes orders: `{packet.get('writesOrders')}`",
        f"- Touches broker: `{packet.get('touchesBroker')}`",
        "",
        "## Automation Posture",
        "",
    ]
    automation = packet.get("automationPosture") or {}
    lines.extend([
        f"- Status: `{automation.get('status')}`",
        f"- Decision: `{automation.get('decision')}`",
        f"- Active Bill automations: `{automation.get('activeBillAutomationCount')}`",
        f"- Futures proof: `{automation.get('activeFuturesOpenSessionProofIds')}`",
        f"- Prediction capture: `{automation.get('activePredictionCaptureIds')}`",
        "",
        "## Strategy Evidence",
        "",
    ])
    for row in packet.get("strategyEvidence") or []:
        lines.append(
            f"- `{row.get('id')}` {row.get('strategy')} {row.get('timeframe')} "
            f"posture `{row.get('researchPosture')}` OOS `{row.get('oosNetPoints')}` "
            f"PF `{row.get('oosProfitFactor')}` blockers `{row.get('metricBlockers')}`"
        )
    lines.extend(["", "## Hermes Access Policy", ""])
    policy = packet.get("hermesAccessPolicy") or {}
    lines.append(policy.get("cheapModelUse") or "")
    lines.extend(["", "Allowed:"])
    for item in policy.get("allowed") or []:
        lines.append(f"- {item}")
    lines.extend(["", "Forbidden:"])
    for item in policy.get("forbidden") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Safe Commands", ""])
    for command in packet.get("safeCommands") or []:
        lines.append(f"```bash\n{command}\n```")
    lines.extend(["", "## Next One-Variable Research", ""])
    for item in packet.get("nextOneVariableResearch") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Hermes-safe AI-Scientist research access packet.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(default_markdown_path()))
    args = parser.parse_args()

    packet = build_packet()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")

    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(packet))

    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
