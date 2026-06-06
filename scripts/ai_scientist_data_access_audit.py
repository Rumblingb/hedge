#!/usr/bin/env python3
"""Audit which historical datasets AI-Scientist can see by default.

The financial_strategy template is intentionally safe and local-file-only, but
that also means it does not automatically consume the full Bill Data Master.
This audit makes the coverage gap explicit so research agents can wire more
data without confusing "available on disk" with "visible to AI-Scientist".
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
HERMES = Path.home() / "Documents" / "memorybrain" / "Agent-Hermes"
TEMPLATE = ROOT / "ai-scientist-templates" / "financial_strategy" / "experiment.py"
DATA_MASTER = STATE / "bill-data-master.latest.json"
DEFAULT_OUTPUT = STATE / "ai-scientist-data-access-audit.latest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"ai-scientist-data-access-audit-{current_utc_date()}.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_template_defaults(template_path: Path = TEMPLATE) -> dict[str, Path]:
    spec = importlib.util.spec_from_file_location("bill_ai_scientist_template", template_path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    defaults = getattr(module, "DEFAULT_DATA_BY_TIMEFRAME", {})
    return {str(key): Path(value) for key, value in defaults.items()} if isinstance(defaults, dict) else {}


def normalize_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def visible_dataset_keys(defaults: dict[str, Path]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for key, path in defaults.items():
        normalized = normalize_path(path).lower()
        symbol = "ES" if "-es" in key or "/es-" in normalized else "NQ" if "/nq-" in normalized else ""
        if not symbol:
            continue
        if "1min" in normalized or "1m" in key or "-1m-" in normalized:
            timeframe = "1min"
        elif "5m" in key or "-5m" in normalized:
            timeframe = "5min"
        elif "15m" in key or "-15m" in normalized:
            timeframe = "15min"
        elif "30m" in key or "-30m" in normalized:
            timeframe = "30min"
        elif "60m" in key or "-60m" in normalized:
            timeframe = "60min"
        else:
            continue
        keys.add((symbol, timeframe))
    return keys


def dataset_equivalent_visible(row: dict[str, Any], visible_keys: set[tuple[str, str]]) -> bool:
    timeframe = str(row.get("timeframe") or "")
    symbols = row.get("symbols")
    if not isinstance(symbols, list) or len(symbols) != 1:
        return False
    symbol = str(symbols[0]).upper()
    return (symbol, timeframe) in visible_keys


def data_master_rows(data_master: dict[str, Any]) -> list[dict[str, Any]]:
    top = data_master.get("topDatasets")
    rows = top if isinstance(top, list) else []
    return [row for row in rows if isinstance(row, dict)]


def build_audit(
    *,
    template_defaults: dict[str, Path] | None = None,
    data_master: dict[str, Any] | None = None,
) -> dict[str, Any]:
    defaults = template_defaults if template_defaults is not None else load_template_defaults()
    master = data_master if data_master is not None else read_json(DATA_MASTER)
    rows = data_master_rows(master)
    visible_paths = {normalize_path(path) for path in defaults.values()}
    visible_keys = visible_dataset_keys(defaults)
    top_paths = {str(row.get("path") or "") for row in rows}
    visible_top = [row for row in rows if str(row.get("path") or "") in visible_paths]
    gold_walkforward = [row for row in rows if row.get("trustTier") == "gold-walkforward"]
    visible_gold = [
        row
        for row in gold_walkforward
        if str(row.get("path") or "") in visible_paths
        or dataset_equivalent_visible(row, visible_keys)
    ]

    missing_high_value = []
    for row in gold_walkforward:
        path = str(row.get("path") or "")
        if path not in visible_paths and not dataset_equivalent_visible(row, visible_keys):
            missing_high_value.append(
                {
                    "path": path,
                    "rows": row.get("rows"),
                    "timeframe": row.get("timeframe"),
                    "symbols": row.get("symbols") if isinstance(row.get("symbols"), list) else [],
                    "reason": "gold-walkforward-dataset-not-in-template-defaults",
                }
            )

    one_minute_symbols = {symbol for symbol, timeframe in visible_keys if timeframe == "1min"}
    one_minute_status = (
        "selectable-1m-research-only"
        if {"ES", "NQ"}.issubset(one_minute_symbols)
        else "partially-visible"
        if one_minute_symbols
        else "not-default-visible"
    )
    one_minute_next = (
        {
            "id": "ai-scientist-3m-derived-entry-bars",
            "oneVariable": "derive 3m entry bars from selectable 1m ES/NQ with complete-bar no-lookahead proof",
            "blockedFromExecution": True,
        }
        if one_minute_status == "selectable-1m-research-only"
        else {
            "id": "ai-scientist-1m-entry-data",
            "oneVariable": "add NQ/ES 1m datasets as selectable research inputs only",
            "blockedFromExecution": True,
        }
    )

    feature_gaps = [
        {
            "id": "one-minute-entry-data",
            "status": one_minute_status,
            "why": "1m/3m entry timing research needs lower-timeframe data. 1m defaults can support this; 3m derived bars still need explicit no-lookahead resampling.",
        },
        {
            "id": "six-market-cross-asset-data",
            "status": "not-default-visible",
            "why": "All-6-market ES/NQ/CL/GC/6E/ZN datasets are in Data Master but not default AI-Scientist inputs.",
        },
        {
            "id": "leading-indicator-data",
            "status": "not-default-visible",
            "why": "VIX/PCR/options/sector features are separate research overlays and not joined into AI-Scientist runs.",
        },
        {
            "id": "external-drive-cache",
            "status": "not-default-visible",
            "why": "Seagate/Kaggle caches require explicit source-parity and path wiring before template use.",
        },
    ]

    blocked = bool(missing_high_value or feature_gaps)
    return {
        "command": "ai-scientist-data-access-audit",
        "generatedAt": now_iso(),
        "decision": "research-only-ai-scientist-data-access-incomplete" if blocked else "research-only-ai-scientist-data-access-visible",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForDemoExpansion": False,
        "templatePath": str(TEMPLATE),
        "dataMasterPath": str(DATA_MASTER),
        "dataMasterDatasetCount": master.get("datasetCount"),
        "dataMasterTierCounts": master.get("tierCounts") if isinstance(master.get("tierCounts"), dict) else {},
        "templateDefaultCount": len(defaults),
        "templateDefaults": [
            {
                "key": key,
                "path": normalize_path(path),
                "exists": path.exists(),
                "inDataMasterTopDatasets": normalize_path(path) in top_paths,
            }
            for key, path in sorted(defaults.items())
        ],
        "visibleGoldWalkforwardCount": len(visible_gold),
        "goldWalkforwardCount": len(gold_walkforward),
        "visibleTopDatasetCount": len(visible_top),
        "missingHighValueDatasets": missing_high_value,
        "featureGaps": feature_gaps,
        "nextOneVariableWiring": [
            one_minute_next,
            {
                "id": "ai-scientist-cross-asset-profile",
                "oneVariable": "add one all-6-market dataset profile without changing strategy rules",
                "blockedFromExecution": True,
            },
            {
                "id": "ai-scientist-leading-indicator-join",
                "oneVariable": "join PCR/VIX daily regime tag after proving no-lookahead timestamps",
                "blockedFromExecution": True,
            },
        ],
        "operatorRead": (
            "AI-Scientist is running, but it sees a curated default subset. "
            "Use Data Master to add datasets one variable at a time; do not give the template every file at once."
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# AI-Scientist Data Access Audit - {str(payload.get('generatedAt') or current_utc_date())[:10]}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Ready for execution: `{payload.get('readyForExecution')}`",
        f"- Data Master datasets: `{payload.get('dataMasterDatasetCount')}`",
        f"- Data Master tier counts: `{payload.get('dataMasterTierCounts')}`",
        f"- Template defaults: `{payload.get('templateDefaultCount')}`",
        f"- Visible gold walk-forward: `{payload.get('visibleGoldWalkforwardCount')}/{payload.get('goldWalkforwardCount')}`",
        "",
        "## Template Defaults",
        "",
    ]
    for row in payload.get("templateDefaults") or []:
        lines.append(f"- `{row.get('key')}` -> `{row.get('path')}` exists `{row.get('exists')}`")
    lines.extend(["", "## Missing High-Value Historical Data", ""])
    for row in payload.get("missingHighValueDatasets") or []:
        lines.append(f"- `{row.get('path')}` rows `{row.get('rows')}` timeframe `{row.get('timeframe')}`")
    lines.extend(["", "## Feature Gaps", ""])
    for gap in payload.get("featureGaps") or []:
        lines.append(f"- `{gap.get('id')}`: `{gap.get('status')}` - {gap.get('why')}")
    lines.extend(["", "## Next One-Variable Wiring", ""])
    for item in payload.get("nextOneVariableWiring") or []:
        lines.append(f"- `{item.get('id')}`: {item.get('oneVariable')}")
    lines.extend(["", payload.get("operatorRead") or "", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit AI-Scientist historical data visibility.")
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
