#!/usr/bin/env python3
"""Read-only audit for external alpha feature datasets on Seagate."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.alpha_frontier_queue import CATALOG, HERMES, read_catalog  # noqa: E402

STATE = ROOT / ".rumbling-hedge/state"
OUT = STATE / "external-alpha-data-audit.latest.json"

DATASETS = [
    "nq_futures_1m",
    "nq_futures_5m",
    "sp500_options_daily_regime",
    "equities_5m_breadth_2026_03",
    "polymarket_btc_updown_5m_resolved_all",
]

NQ_SOURCE_CSVS = {
    "nq_futures_1m": Path("/Volumes/Seagate Expansion Drive/hedge-data/external-alpha-2026-05-25/kaggle/youneseloiarm__nasdaq-cme-future-nq/NQ_in_1_minute.csv"),
    "nq_futures_5m": Path("/Volumes/Seagate Expansion Drive/hedge-data/external-alpha-2026-05-25/kaggle/youneseloiarm__nasdaq-cme-future-nq/NQ_in_5_minute.csv"),
}

GOLD_FEATURE_ALIASES = {
    "atm_iv_5_45d": ["near_atm_call_iv_5_45d", "near_atm_put_iv_5_45d"],
    "skew_25d_proxy": ["skew_25d_put_minus_call"],
    "call_volume_wall": ["call_wall_volume"],
    "put_volume_wall": ["put_wall_volume"],
    "call_wall_distance_pct": ["call_wall_distance_points"],
    "put_wall_distance_pct": ["put_wall_distance_points"],
    "up_depth": ["up_bid_depth", "up_ask_depth"],
    "down_depth": ["down_bid_depth", "down_ask_depth"],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return HERMES / f"external-alpha-data-audit-{current_utc_date()}.md"


def dataset_config(catalog: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    datasets = catalog.get("datasets") if isinstance(catalog.get("datasets"), dict) else {}
    item = datasets.get(dataset_id)
    return item if isinstance(item, dict) else {}


def numeric_nulls(frame: pl.LazyFrame, columns: list[str]) -> dict[str, int]:
    if not columns:
        return {}
    row = frame.select([pl.col(column).null_count().alias(column) for column in columns]).collect().to_dicts()[0]
    return {key: int(value or 0) for key, value in row.items()}


def min_max_value(frame: pl.LazyFrame, column: str) -> dict[str, Any]:
    if column not in frame.collect_schema().names():
        return {}
    row = frame.select(pl.min(column).alias("min"), pl.max(column).alias("max")).collect().to_dicts()[0]
    return {key: str(value) for key, value in row.items()}


def summarize_parquet(dataset_id: str, config: dict[str, Any]) -> dict[str, Any]:
    path_text = str(config.get("path") or "")
    path = Path(path_text) if path_text else Path("__missing_external_alpha_dataset__")
    out: dict[str, Any] = {
        "id": dataset_id,
        "path": str(path) if path_text else "missing",
        "exists": path.exists(),
        "ok": False,
        "rowCount": 0,
        "columns": [],
        "missingGoldFeatures": [],
        "timeRange": {},
        "nullCounts": {},
        "error": None,
    }
    if not path.exists():
        out["error"] = "missing-dataset"
        return out
    out["sizeBytes"] = path.stat().st_size
    try:
        frame = pl.scan_parquet(path)
        schema = frame.collect_schema()
        columns = schema.names()
        out["columns"] = columns
        out["rowCount"] = int(frame.select(pl.len()).collect().item())
        gold = config.get("gold_features") if isinstance(config.get("gold_features"), list) else []
        missing = []
        aliases_used = {}
        for feature in gold:
            if feature in columns:
                continue
            aliases = GOLD_FEATURE_ALIASES.get(str(feature), [])
            present_aliases = [alias for alias in aliases if alias in columns]
            if present_aliases:
                aliases_used[str(feature)] = present_aliases
            else:
                missing.append(feature)
        out["missingGoldFeatures"] = missing
        out["goldFeatureAliasesUsed"] = aliases_used
        time_col = "ts" if "ts" in columns else "quote_date" if "quote_date" in columns else "end_ts" if "end_ts" in columns else ""
        out["timeColumn"] = time_col or None
        out["timeRange"] = min_max_value(frame, time_col) if time_col else {}
        numeric_cols = [
            name
            for name, dtype in zip(columns, schema.dtypes())
            if dtype.is_numeric()
        ][:24]
        out["nullCounts"] = numeric_nulls(frame, numeric_cols)
        out["ok"] = out["rowCount"] > 0 and not out["missingGoldFeatures"]
    except Exception as exc:
        out["error"] = str(exc)
    return out


def compare_nq_1m_to_local_csv(parquet_path: Path, csv_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "parquet": str(parquet_path),
        "csv": str(csv_path),
        "ok": False,
        "overlapRows": 0,
        "maxCloseAbsDiff": None,
        "maxVolumeAbsDiff": None,
        "error": None,
    }
    if not parquet_path.exists() or not csv_path.exists():
        out["error"] = "missing-parquet-or-csv"
        return out
    try:
        pq = (
            pl.scan_parquet(parquet_path)
            .select([
                pl.col("ts").dt.strftime("%Y-%m-%dT%H:%M:%S").alias("ts_key"),
                pl.col("close").alias("close_parquet"),
                pl.col("volume").alias("volume_parquet"),
            ])
        )
        csv = (
            pl.scan_csv(csv_path)
            .filter(pl.col("symbol") == "NQ")
            .select([
                pl.col("ts").str.slice(0, 19).alias("ts_key"),
                pl.col("close").cast(pl.Float64).alias("close_csv"),
                pl.col("volume").cast(pl.Float64).alias("volume_csv"),
            ])
        )
        joined = pq.join(csv, on="ts_key", how="inner")
        stats = joined.select([
            pl.len().alias("overlapRows"),
            (pl.col("close_parquet") - pl.col("close_csv")).abs().max().alias("maxCloseAbsDiff"),
            (pl.col("volume_parquet") - pl.col("volume_csv")).abs().max().alias("maxVolumeAbsDiff"),
        ]).collect().to_dicts()[0]
        out.update({
            "overlapRows": int(stats["overlapRows"] or 0),
            "maxCloseAbsDiff": float(stats["maxCloseAbsDiff"] or 0),
            "maxVolumeAbsDiff": float(stats["maxVolumeAbsDiff"] or 0),
        })
        out["ok"] = out["overlapRows"] > 100 and out["maxCloseAbsDiff"] <= 0.01
        if out["overlapRows"] == 0:
            out["reason"] = "date-range-mismatch-or-no-overlap"
        elif not out["ok"]:
            out["reason"] = "price-or-volume-diff-above-contract"
    except Exception as exc:
        out["error"] = str(exc)
    return out


def compare_nq_feature_to_source_csv(dataset_id: str, parquet_path: Path, csv_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "datasetId": dataset_id,
        "parquet": str(parquet_path),
        "sourceCsv": str(csv_path),
        "ok": False,
        "overlapRows": 0,
        "sourceRows": 0,
        "featureRows": 0,
        "maxOpenAbsDiff": None,
        "maxHighAbsDiff": None,
        "maxLowAbsDiff": None,
        "maxCloseAbsDiff": None,
        "maxVolumeAbsDiff": None,
        "error": None,
    }
    if not parquet_path.exists() or not csv_path.exists():
        out["error"] = "missing-parquet-or-source-csv"
        return out
    try:
        pq = (
            pl.scan_parquet(parquet_path)
            .select([
                pl.col("ts").dt.strftime("%Y-%m-%d %H:%M:%S").alias("ts_key"),
                pl.col("open").alias("open_parquet"),
                pl.col("high").alias("high_parquet"),
                pl.col("low").alias("low_parquet"),
                pl.col("close").alias("close_parquet"),
                pl.col("volume").alias("volume_parquet"),
            ])
        )
        csv = (
            pl.scan_csv(csv_path)
            .select([
                pl.col("datetime").alias("ts_key"),
                pl.col("open").cast(pl.Float64).alias("open_csv"),
                pl.col("high").cast(pl.Float64).alias("high_csv"),
                pl.col("low").cast(pl.Float64).alias("low_csv"),
                pl.col("close").cast(pl.Float64).alias("close_csv"),
                pl.col("volume").cast(pl.Float64).alias("volume_csv"),
            ])
        )
        joined = pq.join(csv, on="ts_key", how="inner")
        stats = joined.select([
            pl.len().alias("overlapRows"),
            (pl.col("open_parquet") - pl.col("open_csv")).abs().max().alias("maxOpenAbsDiff"),
            (pl.col("high_parquet") - pl.col("high_csv")).abs().max().alias("maxHighAbsDiff"),
            (pl.col("low_parquet") - pl.col("low_csv")).abs().max().alias("maxLowAbsDiff"),
            (pl.col("close_parquet") - pl.col("close_csv")).abs().max().alias("maxCloseAbsDiff"),
            (pl.col("volume_parquet") - pl.col("volume_csv")).abs().max().alias("maxVolumeAbsDiff"),
        ]).collect().to_dicts()[0]
        source_rows = int(csv.select(pl.len()).collect().item())
        feature_rows = int(pq.select(pl.len()).collect().item())
        out.update({
            "overlapRows": int(stats["overlapRows"] or 0),
            "sourceRows": source_rows,
            "featureRows": feature_rows,
            "maxOpenAbsDiff": float(stats["maxOpenAbsDiff"] or 0),
            "maxHighAbsDiff": float(stats["maxHighAbsDiff"] or 0),
            "maxLowAbsDiff": float(stats["maxLowAbsDiff"] or 0),
            "maxCloseAbsDiff": float(stats["maxCloseAbsDiff"] or 0),
            "maxVolumeAbsDiff": float(stats["maxVolumeAbsDiff"] or 0),
        })
        max_price_diff = max(
            out["maxOpenAbsDiff"],
            out["maxHighAbsDiff"],
            out["maxLowAbsDiff"],
            out["maxCloseAbsDiff"],
        )
        out["ok"] = (
            out["overlapRows"] == source_rows == feature_rows
            and max_price_diff <= 0.01
            and out["maxVolumeAbsDiff"] <= 0.01
        )
        if out["overlapRows"] == 0:
            out["reason"] = "date-range-mismatch-or-no-overlap"
        elif not out["ok"]:
            out["reason"] = "source-feature-diff-above-contract-or-row-mismatch"
    except Exception as exc:
        out["error"] = str(exc)
    return out


def nq_source_parity(by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    checks = []
    for dataset_id, source_csv in NQ_SOURCE_CSVS.items():
        parquet_path = Path(str(by_id.get(dataset_id, {}).get("path") or ""))
        checks.append(compare_nq_feature_to_source_csv(dataset_id, parquet_path, source_csv))
    return {
        "ok": bool(checks) and all(item.get("ok") for item in checks),
        "checks": checks,
        "read": "Validates Seagate feature parquet against its downloaded Kaggle source CSV. This is not current broker/local parity.",
    }


def nq_historical_research_usability(by_id: dict[str, dict[str, Any]], source_parity: dict[str, Any]) -> dict[str, Any]:
    dataset_ids = ["nq_futures_1m", "nq_futures_5m"]
    datasets_ok = all(bool(by_id.get(dataset_id, {}).get("ok")) for dataset_id in dataset_ids)
    source_ok = bool(source_parity.get("ok"))
    return {
        "usableForHistoricalResearch": datasets_ok and source_ok,
        "usableForExecutionParity": False,
        "datasetIds": dataset_ids,
        "read": (
            "Seagate NQ files may seed historical research when source parity passes, "
            "but they cannot clear demo/live current/broker parity without overlap against current broker/local data."
        ),
        "blockers": [] if datasets_ok and source_ok else ["nq historical datasets or source parity failed"],
    }


def local_csv_ranges() -> dict[str, dict[str, Any]]:
    paths = {
        "nq_1m_5d": ROOT / "data/free/NQ-1m-5d.csv",
        "all_15m_60d_nq": ROOT / "data/free/ALL-6MARKETS-15m-60d-normalized.csv",
        "all_30m_60d_nq": ROOT / "data/free/ALL-6MARKETS-30m-60d-normalized.csv",
        "all_60m_60d_nq": ROOT / "data/free/ALL-6MARKETS-60m-60d-normalized.csv",
    }
    out: dict[str, dict[str, Any]] = {}
    for key, path in paths.items():
        item: dict[str, Any] = {"path": str(path), "exists": path.exists(), "rows": 0, "min": None, "max": None}
        if not path.exists():
            out[key] = item
            continue
        try:
            frame = pl.scan_csv(path)
            if key.startswith("all_"):
                frame = frame.filter(pl.col("symbol") == "NQ")
            row = frame.select([
                pl.min("ts").alias("min"),
                pl.max("ts").alias("max"),
                pl.len().alias("rows"),
            ]).collect().to_dicts()[0]
            item.update({"min": row["min"], "max": row["max"], "rows": int(row["rows"] or 0)})
        except Exception as exc:
            item["error"] = str(exc)
        out[key] = item
    return out


def build_audit(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    catalog = catalog or read_catalog(CATALOG)
    datasets = [summarize_parquet(dataset_id, dataset_config(catalog, dataset_id)) for dataset_id in DATASETS]
    by_id = {item["id"]: item for item in datasets}
    nq_1m_path = Path(str(by_id.get("nq_futures_1m", {}).get("path") or ""))
    parity = compare_nq_1m_to_local_csv(nq_1m_path, ROOT / "data/free/NQ-1m-5d.csv")
    source_parity = nq_source_parity(by_id)
    historical_usability = nq_historical_research_usability(by_id, source_parity)
    local_ranges = local_csv_ranges()
    blockers: list[str] = []
    for item in datasets:
        if not item.get("ok"):
            blockers.append(f"{item['id']} not usable: {item.get('error') or 'missing gold features'}")
    if not parity.get("ok"):
        if parity.get("reason") == "date-range-mismatch-or-no-overlap":
            blockers.append("nq_futures_1m has no overlap with current local CSV; execution/current parity is not proven")
        else:
            blockers.append("nq_futures_1m does not yet pass local CSV parity")
    if not source_parity.get("ok"):
        blockers.append("nq_futures Seagate feature files do not pass source CSV parity")
    return {
        "command": "external-alpha-data-audit",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "catalog": str(CATALOG),
        "datasets": datasets,
        "localFuturesRanges": local_ranges,
        "nqLocalParity": parity,
        "nqSourceParity": source_parity,
        "nqHistoricalResearchUsability": historical_usability,
        "status": "PASS" if not blockers else "NEEDS_REVIEW",
        "blockers": blockers,
        "hardRules": [
            "External feature files are research inputs, not broker truth.",
            "No strategy replay may use external futures data before parity against local/broker bars is documented.",
            "Historical source parity can seed research, but only current/broker parity can seed execution readiness.",
            "Prediction datasets need walk-forward labels, fee/spread stress, and fillability before paper candidates.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# External Alpha Data Audit - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        f"Status: `{payload.get('status')}`",
        f"Generated: `{payload.get('generatedAt')}`",
        "",
        "Research-only. This page does not approve orders.",
        "",
        "## Datasets",
        "",
        "| Dataset | OK | Rows | Time range | Missing gold features | Path |",
        "|---|---:|---:|---|---|---|",
    ]
    for item in payload.get("datasets") or []:
        lines.append(
            f"| `{item.get('id')}` | `{item.get('ok')}` | `{item.get('rowCount')}` | "
            f"`{item.get('timeRange')}` | `{item.get('missingGoldFeatures')}` | `{item.get('path')}` |"
        )
    lines.extend([
        "",
        "## NQ Local Parity",
        "",
        f"- OK: `{payload.get('nqLocalParity', {}).get('ok')}`",
        f"- Overlap rows: `{payload.get('nqLocalParity', {}).get('overlapRows')}`",
        f"- Max close diff: `{payload.get('nqLocalParity', {}).get('maxCloseAbsDiff')}`",
        f"- Max volume diff: `{payload.get('nqLocalParity', {}).get('maxVolumeAbsDiff')}`",
        f"- Reason: `{payload.get('nqLocalParity', {}).get('reason', 'missing')}`",
        "",
        "## NQ Source Parity",
        "",
        f"- OK: `{payload.get('nqSourceParity', {}).get('ok')}`",
        f"- Read: {payload.get('nqSourceParity', {}).get('read')}",
    ])
    for check in (payload.get("nqSourceParity", {}) or {}).get("checks", []) or []:
        lines.append(
            f"- `{check.get('datasetId')}` overlap `{check.get('overlapRows')}` / source `{check.get('sourceRows')}` / feature `{check.get('featureRows')}`, "
            f"max close diff `{check.get('maxCloseAbsDiff')}`, max volume diff `{check.get('maxVolumeAbsDiff')}`, ok `{check.get('ok')}`"
        )
    usability = payload.get("nqHistoricalResearchUsability") or {}
    lines.extend([
        "",
        "## NQ Historical Usability",
        "",
        f"- Usable for historical research: `{usability.get('usableForHistoricalResearch')}`",
        f"- Usable for execution/current parity: `{usability.get('usableForExecutionParity')}`",
        f"- Read: {usability.get('read')}",
    ])
    lines.extend([
        "",
        "## Blockers",
        "",
    ])
    for blocker in payload.get("blockers") or ["none"]:
        lines.append(f"- {blocker}")
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    payload = build_audit()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    HERMES.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    default_markdown_path().write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
