#!/usr/bin/env python3
"""Append current local NQ OHLCV slices onto Seagate feature parquet for parity audits.

Research-only. Does not touch broker or arm execution.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
SEAGATE_FEATURES = Path("/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures")

LOCAL_BY_CADENCE = {
    1: ROOT / "data/free/NQ-1m-5d.csv",
    5: ROOT / "data/free/ALL-6MARKETS-15m-60d-normalized.csv",  # resampled below when needed
}

PARQUET_BY_CADENCE = {
    1: SEAGATE_FEATURES / "nq_1_minute.parquet",
    5: SEAGATE_FEATURES / "nq_5_minute.parquet",
    60: SEAGATE_FEATURES / "nq_1_hour.parquet",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_local_nq_csv(path: Path, *, cadence_minutes: int) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    frame = pl.scan_csv(path)
    columns = frame.collect_schema().names()
    if "symbol" in columns:
        frame = frame.filter(pl.col("symbol").cast(pl.Utf8) == "NQ")
    out = (
        frame.select([
            pl.col("ts").str.to_datetime(strict=False, time_zone="UTC").alias("ts"),
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64).fill_null(0.0),
        ])
        .sort("ts")
        .collect()
    )
    if cadence_minutes == 1 or out.is_empty():
        return out
    if cadence_minutes == 5:
        return (
            out.group_by_dynamic("ts", every="5m")
            .agg([
                pl.col("open").first(),
                pl.col("high").max(),
                pl.col("low").min(),
                pl.col("close").last(),
                pl.col("volume").sum(),
            ])
            .sort("ts")
        )
    if cadence_minutes == 60:
        return (
            out.group_by_dynamic("ts", every="1h")
            .agg([
                pl.col("open").first(),
                pl.col("high").max(),
                pl.col("low").min(),
                pl.col("close").last(),
                pl.col("volume").sum(),
            ])
            .sort("ts")
        )
    return out


def load_parquet(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.scan_parquet(path).select(["ts", "open", "high", "low", "close", "volume"]).sort("ts").collect()


def merge_frames(existing: pl.DataFrame, local: pl.DataFrame) -> pl.DataFrame:
    if local.is_empty():
        return existing
    if existing.is_empty():
        return local
    existing = existing.with_columns(pl.col("ts").dt.replace_time_zone("UTC"))
    local = local.with_columns(pl.col("ts").dt.replace_time_zone("UTC"))
    local_min = local["ts"].min()
    trimmed = existing.filter(pl.col("ts") < local_min) if local_min is not None else existing
    merged = pl.concat([trimmed, local], how="vertical_relaxed").unique(subset=["ts"], keep="last").sort("ts")
    return merged


def export_csv(frame: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    (
        frame.with_columns(pl.col("ts").dt.strftime("%Y-%m-%dT%H:%M:%S.000Z").alias("ts"))
        .select(["ts", "open", "high", "low", "close", "volume"])
        .write_csv(path)
    )


def sync_cadence(cadence_minutes: int, *, export_dir: Path | None, write_parquet: bool) -> dict[str, Any]:
    local_path = LOCAL_BY_CADENCE[1]
    parquet_path = PARQUET_BY_CADENCE[cadence_minutes]
    local = load_local_nq_csv(local_path, cadence_minutes=cadence_minutes)
    existing = load_parquet(parquet_path)
    merged = merge_frames(existing, local)
    result: dict[str, Any] = {
        "cadenceMinutes": cadence_minutes,
        "parquet": str(parquet_path),
        "localRows": int(local.height),
        "existingRows": int(existing.height),
        "mergedRows": int(merged.height),
        "localMin": str(local["ts"].min()) if local.height else None,
        "localMax": str(local["ts"].max()) if local.height else None,
        "mergedMin": str(merged["ts"].min()) if merged.height else None,
        "mergedMax": str(merged["ts"].max()) if merged.height else None,
        "written": False,
        "error": None,
    }
    if merged.is_empty():
        result["error"] = "no-rows-to-write"
        return result
    try:
        if export_dir is not None:
            export_csv(merged, export_dir / f"nq_{cadence_minutes}m_seagate_merged.csv")
            result["exportCsv"] = str(export_dir / f"nq_{cadence_minutes}m_seagate_merged.csv")
        if write_parquet:
            parquet_path.parent.mkdir(parents=True, exist_ok=True)
            merged.write_parquet(parquet_path)
            result["written"] = True
        else:
            result["written"] = bool(result.get("exportCsv"))
            result["parquetWriteSkipped"] = True
    except Exception as exc:
        result["error"] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync local NQ slices onto Seagate feature parquet")
    parser.add_argument("--cadences", default="1,5,60", help="Comma-separated minute cadences to export")
    parser.add_argument("--write-parquet", default="1", help="Cadences to write back to Seagate parquet (default: 1m only)")
    parser.add_argument("--export-dir", default=str(ROOT / ".rumbling-hedge/research/seagate-exports"))
    args = parser.parse_args()
    export_dir = Path(args.export_dir)
    cadences = [int(item.strip()) for item in str(args.cadences).split(",") if item.strip()]
    write_parquet = {int(item.strip()) for item in str(args.write_parquet).split(",") if item.strip()}
    slices = [sync_cadence(c, export_dir=export_dir, write_parquet=c in write_parquet) for c in cadences]
    payload = {
        "command": "sync-seagate-nq-local-parity-slice",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "slices": slices,
        "ok": all(item.get("written") for item in slices),
    }
    out = STATE / "seagate-nq-local-parity-sync.latest.json"
    out.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
