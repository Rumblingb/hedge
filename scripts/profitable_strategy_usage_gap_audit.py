#!/usr/bin/env python3
"""Explain why profitable-looking strategy research is not being used.

This audit separates three things that keep getting blended together:

1. profitable research output,
2. promoted strategy contract,
3. broker/demo route permission.

The first can exist without the other two. This script scans AI-Scientist
`final_info.json` outputs, ranks positive OOS evidence, and records why each
claim is not automatically usable in Bill/Hermes demo execution.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
HERMES = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"
DEFAULT_OUTPUT = STATE / "profitable-strategy-usage-gap-audit.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"profitable-strategy-usage-gap-audit-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def git_status_rows() -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return [line for line in output.splitlines() if line.strip()]


def final_info_paths() -> list[Path]:
    paths: set[Path] = set()
    for base in [ROOT, ROOT / "ai-scientist-templates" / "financial_strategy"]:
        if base.exists():
            for path in base.rglob("final_info.json"):
                if "/venv/" in str(path):
                    continue
                paths.add(path.resolve())
    return sorted(paths)


def safety_ok(payload: dict[str, Any]) -> bool:
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    return bool(safety.get("research_only") or payload.get("researchOnly")) and not any(
        bool(safety.get(key) or payload.get(key))
        for key in ("writes_orders", "touches_broker", "moves_funds", "writesOrders", "touchesBroker", "movesFunds")
    )


def row_from_result(path: Path, payload: dict[str, Any], result: dict[str, Any], result_id: str) -> dict[str, Any]:
    experiment = result.get("experiment") if isinstance(result.get("experiment"), dict) else {}
    means = result.get("means") if isinstance(result.get("means"), dict) else {}
    safety_payload = {"safety": result.get("safety") or payload.get("safety") or {}}
    blockers = experiment.get("metric_blockers") if isinstance(experiment.get("metric_blockers"), list) else []
    return {
        "id": result_id,
        "path": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
        "strategy": experiment.get("strategy"),
        "timeframe": experiment.get("timeframe"),
        "symbol": experiment.get("symbol"),
        "decision": experiment.get("decision"),
        "safeResearchOutput": safety_ok(safety_payload),
        "readyForExecutionFlag": bool(means.get("ready_for_execution")),
        "readyForPaperFlag": bool(means.get("ready_for_paper")),
        "rawTradeCount": experiment.get("raw_trade_count"),
        "keptTradeCount": (experiment.get("gate") or {}).get("kept") if isinstance(experiment.get("gate"), dict) else None,
        "oosTradeCount": means.get("oos_trade_count"),
        "oosNetPoints": means.get("oos_total_net_points"),
        "oosProfitFactor": means.get("oos_profit_factor"),
        "oosWinRate": means.get("oos_win_rate"),
        "walkforwardPositiveFoldShare": means.get("walkforward_positive_fold_share"),
        "blockers": blockers,
    }


def extract_rows(path: Path) -> list[dict[str, Any]]:
    raw = read_json(path)
    template = raw.get("AlphaStrategyTemplate") if isinstance(raw.get("AlphaStrategyTemplate"), dict) else raw
    if not isinstance(template, dict):
        return []
    experiment = template.get("experiment") if isinstance(template.get("experiment"), dict) else {}
    baseline_results = experiment.get("baseline_results") if isinstance(experiment.get("baseline_results"), list) else []
    if baseline_results:
        rows = []
        for item in baseline_results:
            if not isinstance(item, dict):
                continue
            baseline = item.get("baseline") if isinstance(item.get("baseline"), dict) else {}
            result_id = str(baseline.get("id") or path.parent.name)
            rows.append(row_from_result(path, template, item, result_id))
        return rows
    return [row_from_result(path, template, template, path.parent.name)]


def profitable_enough(row: dict[str, Any]) -> bool:
    oos = row.get("oosNetPoints")
    pf = row.get("oosProfitFactor")
    trades = row.get("oosTradeCount") or 0
    return (
        isinstance(oos, (int, float))
        and isinstance(pf, (int, float))
        and oos > 0
        and pf >= 1.2
        and trades >= 10
    )


def non_use_reasons(row: dict[str, Any], status_rows: list[str]) -> list[str]:
    reasons: list[str] = []
    if not row.get("safeResearchOutput"):
        reasons.append("output-safety-metadata-missing-or-unsafe")
    if row.get("readyForExecutionFlag"):
        reasons.append("invalid-research-output-claims-execution-ready")
    if row.get("blockers"):
        reasons.extend([f"metric-blocker:{blocker}" for blocker in row["blockers"]])
    if row.get("decision") != "research-only-template-candidate":
        reasons.append("not-template-research-candidate")
    if any("ai-scientist-templates/financial_strategy/experiment.py" in line for line in status_rows):
        reasons.append("ai-scientist-template-dirty-review-required")
    if any("src/live/" in line or "demoExecution" in line for line in status_rows):
        reasons.append("live-adjacent-code-dirty-review-required")
    if any("src/engine/strategyFusion.ts" in line or "src/strategies/" in line for line in status_rows):
        reasons.append("strategy-routing-code-dirty-review-required")
    reasons.append("no-promoted-strategy-contract-or-route-permission")
    reasons.append("daily-plan-says-no-new-bill-hermes-orders-approved")
    return sorted(set(reasons))


def build_audit() -> dict[str, Any]:
    status_rows = git_status_rows()
    rows: list[dict[str, Any]] = []
    for path in final_info_paths():
        rows.extend(extract_rows(path))
    for row in rows:
        row["profitableResearchClaim"] = profitable_enough(row)
        row["whyNotUsed"] = non_use_reasons(row, status_rows) if row["profitableResearchClaim"] else []
    profitable = [row for row in rows if row["profitableResearchClaim"]]
    profitable.sort(
        key=lambda row: (
            1 if row.get("decision") == "research-only-template-candidate" and not row.get("blockers") else 0,
            float(row.get("oosProfitFactor") or 0),
            float(row.get("oosNetPoints") or 0),
        ),
        reverse=True,
    )
    top = profitable[:25]
    execution_ready = [row for row in profitable if not row["whyNotUsed"]]
    return {
        "command": "profitable-strategy-usage-gap-audit",
        "generatedAt": now_iso(),
        "decision": "research-profitable-but-not-route-ready" if profitable else "no-profitable-research-claims-found",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "finalInfoCount": len(final_info_paths()),
        "resultRowCount": len(rows),
        "profitableResearchClaimCount": len(profitable),
        "executionReadyProfitableCount": len(execution_ready),
        "dirtyStatusCount": len(status_rows),
        "dirtyStatusSample": status_rows[:40],
        "topProfitableResearchClaims": top,
        "answer": (
            "We are not using every profitable-looking strategy because profitability in a research file is not the "
            "same as a promoted broker-safe strategy. Current blockers include dirty/unreviewed AI-Scientist and "
            "live-adjacent code, metric blockers such as negative walk-forward folds, missing promoted strategy "
            "contracts/routes, and the daily plan explicitly saying no new Bill/Hermes orders are approved."
        ),
        "nextPromotionWork": [
            "Pick one NQ candidate, preferably the strongest 3m ORB variant, and run year/regime/cost stress.",
            "Review the dirty AI-Scientist template changes before trusting new PJI/VWAP/GC/CL results.",
            "Create a promoted strategy contract only after OOS, stress, broker parity, daily plan, and route gates clear.",
            "Keep GC/CL/6E profitable-looking outputs in research watch until Topstep product sizing/risk rules are explicit.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Profitable Strategy Usage Gap Audit - {str(payload.get('generatedAt') or current_utc_date())[:10]}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Final info files: `{payload.get('finalInfoCount')}`",
        f"- Result rows: `{payload.get('resultRowCount')}`",
        f"- Profitable research claims: `{payload.get('profitableResearchClaimCount')}`",
        f"- Execution-ready profitable claims: `{payload.get('executionReadyProfitableCount')}`",
        "",
        "## Direct Answer",
        "",
        str(payload.get("answer")),
        "",
        "## Top Profitable Research Claims",
        "",
    ]
    for row in payload.get("topProfitableResearchClaims") or []:
        reasons = "; ".join((row.get("whyNotUsed") or [])[:5])
        lines.append(
            f"- `{row.get('id')}` {row.get('strategy')} {row.get('symbol')} {row.get('timeframe')} "
            f"OOS `{row.get('oosNetPoints')}` PF `{row.get('oosProfitFactor')}` "
            f"decision `{row.get('decision')}` not used because: {reasons}"
        )
    lines.extend(["", "## Next Promotion Work", ""])
    for item in payload.get("nextPromotionWork") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Dirty Status Sample", ""])
    for row in payload.get("dirtyStatusSample") or []:
        lines.append(f"- `{row}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit why profitable-looking strategy claims are not routed.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(default_markdown_path()))
    args = parser.parse_args()

    payload = build_audit()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload))

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
