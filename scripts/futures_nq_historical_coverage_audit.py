#!/usr/bin/env python3
"""Audit NQ historical data coverage for research-only OOS work.

The current external 1m NQ feature file is source-clean but too short for an
OOS session contract. This artifact inventories nearby NQ candidates and marks
which, if any, are suitable for historical research. It does not approve current
Topstep demo expansion or execution routing.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
OUT = STATE / "futures-nq-historical-coverage-audit.latest.json"
VAULT = Path.home() / "Documents/memorybrain"

UTC = ZoneInfo("UTC")
NEW_YORK = ZoneInfo("America/New_York")
NY_SESSION_START = time(9, 30)
NY_SESSION_END = time(16, 0)


@dataclass(frozen=True)
class CandidateSpec:
    datasetId: str
    path: Path
    cadenceMinutes: int
    source: str
    sourceCsv: Path | None = None
    localCsv: Path | None = None
    timestampColumn: str = "ts"
    archiveOnly: bool = False


SEAGATE_ROOT = Path("/Volumes/Seagate Expansion Drive/hedge-data")
NQ_FEATURES = SEAGATE_ROOT / "features/nq_futures"
NQ_SOURCE = SEAGATE_ROOT / "external-alpha-2026-05-25/kaggle/youneseloiarm__nasdaq-cme-future-nq"

DEFAULT_CANDIDATES = [
    CandidateSpec("seagate_nq_1m", NQ_FEATURES / "nq_1_minute.parquet", 1, "seagate-feature", NQ_SOURCE / "NQ_in_1_minute.csv", ROOT / "data/free/NQ-1m-5d.csv"),
    CandidateSpec("seagate_nq_5m", NQ_FEATURES / "nq_5_minute.parquet", 5, "seagate-feature", NQ_SOURCE / "NQ_in_5_minute.csv", ROOT / "data/free/NQ-5m-60d.csv"),
    CandidateSpec("seagate_nq_15m", NQ_FEATURES / "nq_15_minute.parquet", 15, "seagate-feature", NQ_SOURCE / "NQ_in_15_minute.csv", ROOT / "data/free/NQ-15m-60d.csv"),
    CandidateSpec("local_nq_1m_30d_archive", ROOT / "data/free/NQ-1m-30d.csv", 1, "local-yfinance-legacy", archiveOnly=True),
    CandidateSpec("local_nq_5m_60d", ROOT / "data/free/NQ-5m-60d.csv", 5, "local-yfinance-research"),
    CandidateSpec("local_nq_15m_60d", ROOT / "data/free/NQ-15m-60d.csv", 15, "local-yfinance-research"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"futures-nq-historical-coverage-audit-{current_utc_date()}.md"


def as_new_york(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(NEW_YORK)


def in_ny_session(value: datetime) -> bool:
    stamp = as_new_york(value).time()
    return NY_SESSION_START <= stamp <= NY_SESSION_END


def session_date(value: datetime) -> str:
    return as_new_york(value).date().isoformat()


def min_rows_for_session(cadence_minutes: int) -> int:
    if cadence_minutes <= 1:
        return 120
    if cadence_minutes <= 5:
        return 50
    if cadence_minutes <= 15:
        return 18
    return 6


def read_candidate_frame(spec: CandidateSpec) -> pl.DataFrame:
    if not spec.path.exists():
        return pl.DataFrame()
    if spec.path.suffix == ".parquet":
        return pl.scan_parquet(spec.path).select(["ts", "open", "high", "low", "close", "volume"]).sort("ts").collect()
    frame = pl.scan_csv(spec.path)
    columns = frame.collect_schema().names()
    lower_map = {column.lower(): column for column in columns}
    ts_col = lower_map.get("ts") or lower_map.get("datetime") or lower_map.get(spec.timestampColumn.lower()) or spec.timestampColumn
    open_col = lower_map.get("open", "open")
    high_col = lower_map.get("high", "high")
    low_col = lower_map.get("low", "low")
    close_col = lower_map.get("close", "close")
    volume_col = lower_map.get("volume", "volume")
    return (
        frame
        .select([
            pl.col(ts_col).str.to_datetime(strict=False, time_zone="UTC").alias("ts"),
            pl.col(open_col).cast(pl.Float64).alias("open"),
            pl.col(high_col).cast(pl.Float64).alias("high"),
            pl.col(low_col).cast(pl.Float64).alias("low"),
            pl.col(close_col).cast(pl.Float64).alias("close"),
            pl.col(volume_col).cast(pl.Float64).alias("volume"),
        ])
        .sort("ts")
        .collect()
    )


def source_parity(spec: CandidateSpec) -> dict[str, Any]:
    out: dict[str, Any] = {"checked": False, "ok": None, "sourceCsv": str(spec.sourceCsv) if spec.sourceCsv else None}
    if spec.sourceCsv is None:
        return out
    out["checked"] = True
    out["ok"] = False
    if not spec.path.exists() or not spec.sourceCsv.exists():
        out["error"] = "missing-feature-or-source-csv"
        return out
    try:
        pq = pl.scan_parquet(spec.path).select([
            pl.col("ts").dt.strftime("%Y-%m-%d %H:%M:%S").alias("ts_key"),
            pl.col("open").alias("open_feature"),
            pl.col("high").alias("high_feature"),
            pl.col("low").alias("low_feature"),
            pl.col("close").alias("close_feature"),
            pl.col("volume").alias("volume_feature"),
        ])
        csv = pl.scan_csv(spec.sourceCsv).select([
            pl.col("datetime").alias("ts_key"),
            pl.col("open").cast(pl.Float64).alias("open_source"),
            pl.col("high").cast(pl.Float64).alias("high_source"),
            pl.col("low").cast(pl.Float64).alias("low_source"),
            pl.col("close").cast(pl.Float64).alias("close_source"),
            pl.col("volume").cast(pl.Float64).alias("volume_source"),
        ])
        joined = pq.join(csv, on="ts_key", how="inner")
        stats = joined.select([
            pl.len().alias("overlapRows"),
            (pl.col("open_feature") - pl.col("open_source")).abs().max().alias("maxOpenAbsDiff"),
            (pl.col("high_feature") - pl.col("high_source")).abs().max().alias("maxHighAbsDiff"),
            (pl.col("low_feature") - pl.col("low_source")).abs().max().alias("maxLowAbsDiff"),
            (pl.col("close_feature") - pl.col("close_source")).abs().max().alias("maxCloseAbsDiff"),
            (pl.col("volume_feature") - pl.col("volume_source")).abs().max().alias("maxVolumeAbsDiff"),
        ]).collect().to_dicts()[0]
        source_rows = int(csv.select(pl.len()).collect().item())
        feature_rows = int(pq.select(pl.len()).collect().item())
        max_price_diff = max(float(stats["maxOpenAbsDiff"] or 0), float(stats["maxHighAbsDiff"] or 0), float(stats["maxLowAbsDiff"] or 0), float(stats["maxCloseAbsDiff"] or 0))
        out.update({
            "overlapRows": int(stats["overlapRows"] or 0),
            "sourceRows": source_rows,
            "featureRows": feature_rows,
            "maxPriceAbsDiff": max_price_diff,
            "maxVolumeAbsDiff": float(stats["maxVolumeAbsDiff"] or 0),
        })
        out["ok"] = out["overlapRows"] == source_rows == feature_rows and max_price_diff <= 0.01 and float(out["maxVolumeAbsDiff"]) <= 0.01
        if not out["ok"]:
            out["reason"] = "source-feature-row-or-value-mismatch"
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def canonical_ohlcv_scan(path: Path) -> pl.LazyFrame:
    if path.suffix == ".parquet":
        frame = pl.scan_parquet(path)
        columns = frame.collect_schema().names()
        if "symbol" in columns:
            frame = frame.filter(pl.col("symbol") == "NQ")
        return frame.select([
            pl.col("ts").cast(pl.Datetime).dt.strftime("%Y-%m-%d %H:%M:%S").alias("ts_key"),
            pl.col("open").cast(pl.Float64).alias("open"),
            pl.col("high").cast(pl.Float64).alias("high"),
            pl.col("low").cast(pl.Float64).alias("low"),
            pl.col("close").cast(pl.Float64).alias("close"),
            pl.col("volume").cast(pl.Float64).alias("volume"),
        ])
    frame = pl.scan_csv(path)
    columns = frame.collect_schema().names()
    lower_map = {column.lower(): column for column in columns}
    ts_col = lower_map.get("ts") or lower_map.get("datetime") or "ts"
    if "symbol" in columns:
        frame = frame.filter(pl.col("symbol") == "NQ")
    return frame.select([
        pl.col(ts_col).str.to_datetime(strict=False, time_zone="UTC").dt.strftime("%Y-%m-%d %H:%M:%S").alias("ts_key"),
        pl.col(lower_map.get("open", "open")).cast(pl.Float64).alias("open"),
        pl.col(lower_map.get("high", "high")).cast(pl.Float64).alias("high"),
        pl.col(lower_map.get("low", "low")).cast(pl.Float64).alias("low"),
        pl.col(lower_map.get("close", "close")).cast(pl.Float64).alias("close"),
        pl.col(lower_map.get("volume", "volume")).cast(pl.Float64).alias("volume"),
    ])


def local_csv_parity(spec: CandidateSpec) -> dict[str, Any]:
    out: dict[str, Any] = {"checked": False, "ok": None, "localCsv": str(spec.localCsv) if spec.localCsv else None}
    if spec.localCsv is None:
        return out
    out["checked"] = True
    out["ok"] = False
    if not spec.path.exists() or not spec.localCsv.exists():
        out["error"] = "missing-feature-or-local-csv"
        return out
    try:
        feature = canonical_ohlcv_scan(spec.path).rename({
            "open": "open_feature",
            "high": "high_feature",
            "low": "low_feature",
            "close": "close_feature",
            "volume": "volume_feature",
        })
        local = canonical_ohlcv_scan(spec.localCsv).rename({
            "open": "open_local",
            "high": "high_local",
            "low": "low_local",
            "close": "close_local",
            "volume": "volume_local",
        })
        joined = feature.join(local, on="ts_key", how="inner")
        stats = joined.select([
            pl.len().alias("overlapRows"),
            (pl.col("open_feature") - pl.col("open_local")).abs().max().alias("maxOpenAbsDiff"),
            (pl.col("high_feature") - pl.col("high_local")).abs().max().alias("maxHighAbsDiff"),
            (pl.col("low_feature") - pl.col("low_local")).abs().max().alias("maxLowAbsDiff"),
            (pl.col("close_feature") - pl.col("close_local")).abs().max().alias("maxCloseAbsDiff"),
            (pl.col("volume_feature") - pl.col("volume_local")).abs().max().alias("maxVolumeAbsDiff"),
        ]).collect().to_dicts()[0]
        feature_range = feature.select([pl.min("ts_key").alias("min"), pl.max("ts_key").alias("max"), pl.len().alias("rows")]).collect().to_dicts()[0]
        local_range = local.select([pl.min("ts_key").alias("min"), pl.max("ts_key").alias("max"), pl.len().alias("rows")]).collect().to_dicts()[0]
        max_price_diff = max(
            float(stats["maxOpenAbsDiff"] or 0),
            float(stats["maxHighAbsDiff"] or 0),
            float(stats["maxLowAbsDiff"] or 0),
            float(stats["maxCloseAbsDiff"] or 0),
        )
        max_volume_diff = float(stats["maxVolumeAbsDiff"] or 0)
        overlap_rows = int(stats["overlapRows"] or 0)
        out.update({
            "overlapRows": overlap_rows,
            "featureRange": feature_range,
            "localCsvRange": local_range,
            "maxPriceAbsDiff": max_price_diff,
            "maxVolumeAbsDiff": max_volume_diff,
        })
        out["ok"] = overlap_rows > 0 and max_price_diff <= 0.01 and max_volume_diff <= 0.01
        if overlap_rows <= 0:
            out["reason"] = "no-overlapping-bars-with-current-local-csv"
        elif not out["ok"]:
            out["reason"] = "local-csv-feature-value-mismatch"
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def summarize_candidate(spec: CandidateSpec) -> dict[str, Any]:
    item: dict[str, Any] = {
        "datasetId": spec.datasetId,
        "path": str(spec.path),
        "exists": spec.path.exists(),
        "cadenceMinutes": spec.cadenceMinutes,
        "source": spec.source,
        "archiveOnly": spec.archiveOnly,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
    }
    if not spec.path.exists():
        item.update({"rowCount": 0, "sessionCount": 0, "usableForHistoricalOosResearch": False, "blockers": ["missing-file"]})
        return item
    try:
        frame = read_candidate_frame(spec)
        ts_min = frame.select(pl.min("ts")).item()
        ts_max = frame.select(pl.max("ts")).item()
        min_rows = min_rows_for_session(spec.cadenceMinutes)
        buckets: dict[str, int] = {}
        for row in frame.select("ts").to_dicts():
            ts = row["ts"]
            if isinstance(ts, datetime) and in_ny_session(ts):
                key = session_date(ts)
                buckets[key] = buckets.get(key, 0) + 1
        complete_sessions = {day: rows for day, rows in buckets.items() if rows >= min_rows}
        parity = source_parity(spec)
        blockers: list[str] = []
        if spec.archiveOnly:
            blockers.append("archive-only-source-not-demo-evidence")
        if parity.get("checked") and not parity.get("ok"):
            blockers.append("source-parity-not-cleared")
        local_parity = local_csv_parity(spec)
        if local_parity.get("checked") and not local_parity.get("ok"):
            blockers.append("current-local-csv-parity-not-cleared")
        if len(complete_sessions) < 20:
            blockers.append("too-few-sessions-for-research")
        if len(complete_sessions) < 60:
            blockers.append("below-preferred-promotion-depth")
        usable = not spec.archiveOnly and "source-parity-not-cleared" not in blockers and len(complete_sessions) >= 20
        item.update({
            "rowCount": frame.height,
            "timeRange": {"min": str(ts_min), "max": str(ts_max)},
            "nySessionMinRows": min_rows,
            "sessionCount": len(complete_sessions),
            "sampleSessions": [{"date": day, "rows": rows} for day, rows in sorted(complete_sessions.items())[:8]],
            "sourceParity": parity,
            "currentLocalCsvParity": local_parity,
            "usableForHistoricalOosResearch": usable,
            "preferredForPromotionReview": usable and len(complete_sessions) >= 60,
            "blockers": blockers,
        })
    except Exception as exc:
        item.update({"rowCount": 0, "sessionCount": 0, "usableForHistoricalOosResearch": False, "blockers": [f"{type(exc).__name__}: {exc}"]})
    return item


def build_audit(candidates: list[CandidateSpec] | None = None) -> dict[str, Any]:
    rows = [summarize_candidate(spec) for spec in (candidates or DEFAULT_CANDIDATES)]
    usable = [row for row in rows if row.get("usableForHistoricalOosResearch")]
    preferred = [row for row in usable if row.get("preferredForPromotionReview")]
    local_parity_checked = [row for row in rows if (row.get("currentLocalCsvParity") or {}).get("checked")]
    local_parity_cleared = [row for row in local_parity_checked if (row.get("currentLocalCsvParity") or {}).get("ok")]
    best = sorted(usable, key=lambda row: (not bool(row.get("preferredForPromotionReview")), -int(row.get("sessionCount") or 0), int(row.get("cadenceMinutes") or 999)))[0] if usable else None
    blockers: list[str] = []
    if not usable:
        blockers.append("no-historical-nq-source-meets-minimum-oos-depth")
    if not preferred:
        blockers.append("no-historical-nq-source-meets-preferred-promotion-depth")
    if local_parity_checked and not local_parity_cleared:
        blockers.append("no-seagate-nq-source-overlaps-current-local-csv-bars")
    return {
        "command": "futures-nq-historical-coverage-audit",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "candidates": rows,
        "usableHistoricalOosCount": len(usable),
        "preferredPromotionDepthCount": len(preferred),
        "currentLocalCsvParityCheckedCount": len(local_parity_checked),
        "currentLocalCsvParityClearedCount": len(local_parity_cleared),
        "bestHistoricalOosCandidate": best,
        "blockers": blockers,
        "decision": "research-only-historical-nq-source-ready" if usable else "research-only-historical-nq-source-blocked",
        "nextAction": (
            "Run research-only replay on the best historical candidate; do not use it as current Topstep demo evidence."
            if usable
            else "Acquire longer broker-grade/current NQ history before replay."
        ),
        "hardRules": [
            "Historical source coverage can unblock research, not demo execution.",
            "Current Topstep demo expansion still requires broker/current parity and execution-grade realtime data.",
            "A Seagate historical source with no overlap against current local CSV bars cannot be used as current-data parity evidence.",
            "Archive-only local files are context, not promotion evidence.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Futures NQ Historical Coverage Audit - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only inventory for NQ historical data coverage. This page does not approve Topstep demo or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Usable historical OOS sources: `{payload.get('usableHistoricalOosCount')}`",
        f"- Preferred promotion-depth sources: `{payload.get('preferredPromotionDepthCount')}`",
        f"- Current local CSV parity: `{payload.get('currentLocalCsvParityClearedCount')}/{payload.get('currentLocalCsvParityCheckedCount')}`",
        f"- Best candidate: `{(payload.get('bestHistoricalOosCandidate') or {}).get('datasetId')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Candidates",
        "",
    ]
    for item in payload.get("candidates") or []:
        lines.append(
            f"- `{item.get('datasetId')}` cadence `{item.get('cadenceMinutes')}m`, rows `{item.get('rowCount')}`, "
            f"sessions `{item.get('sessionCount')}`, usable `{item.get('usableForHistoricalOosResearch')}`, "
            f"preferred `{item.get('preferredForPromotionReview')}`, currentCsvParity `{(item.get('currentLocalCsvParity') or {}).get('ok')}`, "
            f"currentCsvReason `{(item.get('currentLocalCsvParity') or {}).get('reason')}`, blockers `{item.get('blockers')}`"
        )
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit NQ historical data coverage for research-only OOS work.")
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown", default=str(default_markdown_path()))
    args = parser.parse_args()
    payload = build_audit()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md = Path(args.markdown)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
