#!/usr/bin/env python3
"""Build a one-variable AI-Scientist research queue for strategy-factory blockers.

This script does not run trades, change promotion gates, or modify strategy
entry code. It converts the current strategy-factory failure shape into a
research-only queue where each experiment changes exactly one AI-Scientist
template argument from the baseline known-baselines run.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_OUTPUT = STATE / "strategy-factory-one-variable-research.latest.json"
DEFAULT_FACTORY = STATE / "strategy-factory.latest.json"
TEMPLATE = ROOT / "ai-scientist-templates" / "financial_strategy" / "experiment.py"
DEFAULT_DATA = ROOT / "data" / "free" / "NQ-2022-2025-15m.csv"
DEFAULT_OUT_ROOT = ROOT / ".rumbling-hedge" / "research" / "ai-scientist-one-variable"


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def base_command(out_dir: Path, *, data: Path = DEFAULT_DATA) -> list[str]:
    return [
        ".venv/bin/python",
        str(TEMPLATE),
        "--strategy",
        "known_baselines",
        "--timeframe",
        "15m",
        "--data",
        str(data),
        "--out_dir",
        str(out_dir),
        "--sessions",
        "ny_morning,ny_afternoon",
        "--skip_sessions",
        "london,premarket",
        "--folds",
        "5",
        "--min_oos_trades",
        "10",
        "--max_trades_per_session",
        "3",
        "--min_timeframe_agreement",
        "2",
    ]


def replace_arg(command: list[str], flag: str, value: str) -> list[str]:
    updated = list(command)
    index = updated.index(flag)
    updated[index + 1] = value
    return updated


def add_or_replace_arg(command: list[str], flag: str, value: str) -> list[str]:
    if flag in command:
        return replace_arg(command, flag, value)
    return [*command, flag, value]


def experiment(
    *,
    experiment_id: str,
    baseline: list[str],
    out_root: Path,
    one_variable: str,
    changed_flag: str | None,
    changed_value: str | None,
    rationale: str,
    success: list[str],
    reject: list[str],
) -> dict[str, Any]:
    command = list(baseline)
    out_dir = out_root / experiment_id
    command = replace_arg(command, "--out_dir", str(out_dir))
    if changed_flag and changed_value is not None:
        command = add_or_replace_arg(command, changed_flag, changed_value)
    return {
        "id": experiment_id,
        "oneVariable": one_variable,
        "changedFlag": changed_flag,
        "changedValue": changed_value,
        "command": command,
        "commandText": " ".join(command),
        "outputDir": str(out_dir),
        "rationale": rationale,
        "successCriteria": success,
        "rejectionCriteria": reject,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
    }


def classify_factory(factory: dict[str, Any]) -> dict[str, Any]:
    no_edge = (((factory.get("researchContext") or {}).get("noEdgeLedger") or {}) if isinstance(factory.get("researchContext"), dict) else {})
    gates = factory.get("gates") if isinstance(factory.get("gates"), dict) else {}
    quant = factory.get("quantCoverage") if isinstance(factory.get("quantCoverage"), dict) else {}
    return {
        "status": factory.get("status"),
        "walkforwardDeployable": gates.get("walkforwardDeployable"),
        "rollingOosWindows": gates.get("rollingOosWindows"),
        "rollingOosDeployableWindows": gates.get("rollingOosDeployableWindows"),
        "sampleSizeOk": quant.get("sampleSizeOk"),
        "inSampleBars": quant.get("inSampleBars"),
        "oosBars": quant.get("oosBars"),
        "profilesEvaluated": quant.get("profilesEvaluated"),
        "selectedProfileIds": ((quant.get("profileSelection") or {}).get("selectedIds") if isinstance(quant.get("profileSelection"), dict) else []),
        "needsMoreDataProfiles": no_edge.get("needsMoreDataProfiles"),
        "promotableProfiles": no_edge.get("promotableProfiles"),
        "blockers": factory.get("blockers") if isinstance(factory.get("blockers"), list) else [],
    }


def build_queue(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    factory_path = Path(args.factory).resolve()
    output_path = Path(args.output).resolve()
    out_root = Path(args.out_root).resolve()
    data = Path(args.data).resolve()
    factory = read_json(factory_path)
    baseline = base_command(out_root / "baseline", data=data)
    common_success = [
        "final_info.json is written with researchOnly/ready_for_execution false",
        "known_baselines run produces enough OOS trades to compare against baseline",
        "improvement is attributable to the single changed variable only",
    ]
    common_reject = [
        "any output implies paper, demo, live, route, broker, or execution approval",
        "improvement appears only by changing multiple variables",
        "positive result lacks OOS fold support or is driven by a tiny trade count",
    ]
    experiments = [
        experiment(
            experiment_id="baseline-known-baselines-15m",
            baseline=baseline,
            out_root=out_root,
            one_variable="none-baseline",
            changed_flag=None,
            changed_value=None,
            rationale="Establish the AI-Scientist known-baselines result before changing any gate or constraint.",
            success=common_success,
            reject=common_reject,
        ),
        experiment(
            experiment_id="min-oos-trades-5",
            baseline=baseline,
            out_root=out_root,
            one_variable="walkforward minimum OOS trade threshold only",
            changed_flag="--min_oos_trades",
            changed_value="5",
            rationale=(
                "Tests whether the strategy-factory failure is a statistical gate-density problem, "
                "not an entry-signal problem. This is sensitivity evidence only; it must not loosen production gates."
            ),
            success=[*common_success, "same strategies improve only because OOS fold count crosses the diagnostic threshold"],
            reject=[*common_reject, "lower threshold creates paper/demo promotion language"],
        ),
        experiment(
            experiment_id="folds-3",
            baseline=baseline,
            out_root=out_root,
            one_variable="walkforward fold count only",
            changed_flag="--folds",
            changed_value="3",
            rationale=(
                "Tests whether too many walkforward folds fragment trades below significance. "
                "Keeps entries, sessions, max trades, costs, and OOS threshold unchanged."
            ),
            success=[*common_success, "trade counts per fold rise while OOS positivity remains visible"],
            reject=[*common_reject, "fewer folds merely hides a bad fold or negative OOS segment"],
        ),
        experiment(
            experiment_id="max-trades-per-session-5",
            baseline=baseline,
            out_root=out_root,
            one_variable="max trades per session only",
            changed_flag="--max_trades_per_session",
            changed_value="5",
            rationale=(
                "Tests whether the trade cap, rather than signal generation, is starving windows. "
                "This diagnoses the cap; it does not approve higher live/demo frequency."
            ),
            success=[*common_success, "additional trades improve OOS fold depth without degrading expectancy after costs"],
            reject=[*common_reject, "higher cap increases trades but worsens expectancy, PF, or drawdown"],
        ),
        experiment(
            experiment_id="timeframe-agreement-1",
            baseline=baseline,
            out_root=out_root,
            one_variable="minimum timeframe agreement only",
            changed_flag="--min_timeframe_agreement",
            changed_value="1",
            rationale=(
                "Tests whether multi-timeframe confirmation is over-filtering otherwise valid baseline signals. "
                "Keeps sessions, folds, trade caps, and OOS threshold unchanged."
            ),
            success=[*common_success, "more trades appear without turning the result into a noisy no-edge replay"],
            reject=[*common_reject, "agreement relaxation increases count but destroys OOS expectancy or stability"],
        ),
        experiment(
            experiment_id="ny-morning-only",
            baseline=baseline,
            out_root=out_root,
            one_variable="allowed session set only",
            changed_flag="--sessions",
            changed_value="ny_morning",
            rationale=(
                "Tests session stratification directly: use the same baseline strategies and gates, "
                "but isolate the session most relevant to Topstep NQ execution."
            ),
            success=[*common_success, "morning-only OOS folds show cleaner expectancy or lower drawdown than mixed sessions"],
            reject=[*common_reject, "session narrowing only reduces sample size or cherry-picks a small winner"],
        ),
    ]
    return {
        "command": "strategy-factory-one-variable-research",
        "generatedAt": generated_at,
        "decision": "research-only-one-variable-queue",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "factoryPath": str(factory_path),
        "factoryDiagnosis": classify_factory(factory),
        "aiScientistTemplate": str(TEMPLATE),
        "baselineData": str(data),
        "outputPath": str(output_path),
        "hypothesis": (
            "Data volume is not the primary blocker. Strategy-factory needs one-variable "
            "diagnostics around walkforward fold density, OOS trade thresholds, session stratification, "
            "trade caps, and timeframe agreement before any entry constraints are loosened."
        ),
        "whyNotIndividualStrategiesFirst": (
            "The known_baselines AI-Scientist mode evaluates the proven ORB/WQ baseline family together, "
            "so the first pass diagnoses factory/gate variables instead of overfitting one strategy by hand."
        ),
        "experimentCount": len(experiments),
        "recommendedOrder": [item["id"] for item in experiments],
        "experiments": experiments,
        "promotionBlockers": [
            "template-output-is-not-paper-demo-or-execution-promotion",
            "one-variable-results-are-research-sensitivity-only",
            "requires broker/current parity, source hygiene, OOS, cost stress, and daily route gates before any demo/live use",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory", default=str(DEFAULT_FACTORY))
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_queue(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
