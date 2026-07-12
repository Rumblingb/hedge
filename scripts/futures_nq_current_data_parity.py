#!/usr/bin/env python3
"""Audit current local NQ data parity across Bill research files.

This is a research-only local-file consistency check. It compares individual NQ
CSV files against the normalized universe CSVs. It does not query a broker and
does not approve execution.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge/state"
OUT = STATE / "futures-nq-current-data-parity.latest.json"
VAULT = Path.home() / "Documents/memorybrain"


@dataclass(frozen=True)
class ParityPair:
    pairId: str
    cadenceMinutes: int
    leftPath: Path
    rightPath: Path
    symbol: str = "NQ"


DEFAULT_PAIRS = [
    ParityPair("nq-1m-5d-vs-all-6markets-1m-5d", 1, ROOT / "data/free/NQ-1m-5d.csv", ROOT / "data/free/ALL-6MARKETS-1m-5d-normalized.csv"),
    ParityPair("nq-5m-60d-vs-all-6markets-5m-60d", 5, ROOT / "data/free/NQ-5m-60d.csv", ROOT / "data/free/ALL-6MARKETS-5m-60d-normalized.csv"),
    ParityPair("nq-15m-60d-vs-all-6markets-15m-60d", 15, ROOT / "data/free/NQ-15m-60d.csv", ROOT / "data/free/ALL-6MARKETS-15m-60d-normalized.csv"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_markdown_path() -> Path:
    return VAULT / "Agent-Hermes" / f"futures-nq-current-data-parity-{current_utc_date()}.md"


def csv_rows(path: Path, symbol: str) -> pl.LazyFrame:
    frame = pl.scan_csv(path)
    columns = frame.collect_schema().names()
    if "symbol" in columns:
        frame = frame.filter(pl.col("symbol") == symbol)
    return frame.select([
        pl.col("ts"),
        pl.col("open").cast(pl.Float64).alias("open"),
        pl.col("high").cast(pl.Float64).alias("high"),
        pl.col("low").cast(pl.Float64).alias("low"),
        pl.col("close").cast(pl.Float64).alias("close"),
        pl.col("volume").cast(pl.Float64).alias("volume"),
    ])


def compare_pair(pair: ParityPair, price_tolerance: float = 0.01, volume_tolerance: float = 0.01) -> dict[str, Any]:
    out: dict[str, Any] = {
        "pairId": pair.pairId,
        "cadenceMinutes": pair.cadenceMinutes,
        "leftPath": str(pair.leftPath),
        "rightPath": str(pair.rightPath),
        "exists": pair.leftPath.exists() and pair.rightPath.exists(),
        "ok": False,
        "researchClean": False,
        "brokerParity": False,
    }
    if not out["exists"]:
        out["reason"] = "missing-left-or-right-file"
        return out
    left = csv_rows(pair.leftPath, pair.symbol).rename({column: f"{column}_left" for column in ["open", "high", "low", "close", "volume"]})
    right = csv_rows(pair.rightPath, pair.symbol).rename({column: f"{column}_right" for column in ["open", "high", "low", "close", "volume"]})
    joined = left.join(right, on="ts", how="inner")
    stats = joined.select([
        pl.len().alias("overlapRows"),
        (pl.col("open_left") - pl.col("open_right")).abs().max().alias("maxOpenAbsDiff"),
        (pl.col("high_left") - pl.col("high_right")).abs().max().alias("maxHighAbsDiff"),
        (pl.col("low_left") - pl.col("low_right")).abs().max().alias("maxLowAbsDiff"),
        (pl.col("close_left") - pl.col("close_right")).abs().max().alias("maxCloseAbsDiff"),
        (pl.col("volume_left") - pl.col("volume_right")).abs().max().alias("maxVolumeAbsDiff"),
    ]).collect().to_dicts()[0]
    left_count = int(left.select(pl.len()).collect().item())
    right_count = int(right.select(pl.len()).collect().item())
    left_range = left.select(pl.min("ts").alias("min"), pl.max("ts").alias("max")).collect().to_dicts()[0]
    right_range = right.select(pl.min("ts").alias("min"), pl.max("ts").alias("max")).collect().to_dicts()[0]
    price_max = max(float(stats["maxOpenAbsDiff"] or 0), float(stats["maxHighAbsDiff"] or 0), float(stats["maxLowAbsDiff"] or 0), float(stats["maxCloseAbsDiff"] or 0))
    volume_max = float(stats["maxVolumeAbsDiff"] or 0)
    mismatch_sample = (
        joined
        .with_columns([
            (pl.col("close_left") - pl.col("close_right")).abs().alias("closeDiff"),
            (pl.col("volume_left") - pl.col("volume_right")).abs().alias("volumeDiff"),
        ])
        .filter((pl.col("closeDiff") > price_tolerance) | (pl.col("volumeDiff") > volume_tolerance))
        .select(["ts", "close_left", "close_right", "volume_left", "volume_right", "closeDiff", "volumeDiff"])
        .head(8)
        .collect()
        .to_dicts()
    )
    missing_left = right.join(left, on="ts", how="anti").select("ts").head(8).collect().to_dicts()
    missing_right = left.join(right, on="ts", how="anti").select("ts").head(8).collect().to_dicts()
    ok = (
        int(stats["overlapRows"] or 0) >= min(left_count, right_count) - 5
        and price_max <= price_tolerance
        and volume_max <= volume_tolerance
    )
    out.update({
        "leftRows": left_count,
        "rightRows": right_count,
        "overlapRows": int(stats["overlapRows"] or 0),
        "leftRange": left_range,
        "rightRange": right_range,
        "maxPriceAbsDiff": round(price_max, 6),
        "maxVolumeAbsDiff": round(volume_max, 6),
        "mismatchSample": mismatch_sample,
        "missingFromLeftSample": missing_left,
        "missingFromRightSample": missing_right,
        "ok": ok,
        "researchClean": ok,
        "reason": "ok" if ok else "local-file-parity-mismatch",
    })
    return out


def build_audit(pairs: list[ParityPair] | None = None) -> dict[str, Any]:
    comparisons = [compare_pair(pair) for pair in (pairs or DEFAULT_PAIRS)]
    clean = [item for item in comparisons if item.get("researchClean")]

    def best_key(item: dict[str, Any]) -> tuple[str, int, int]:
        right_range = item.get("rightRange") if isinstance(item.get("rightRange"), dict) else {}
        left_range = item.get("leftRange") if isinstance(item.get("leftRange"), dict) else {}
        freshest = str(right_range.get("max") or left_range.get("max") or "")
        return (freshest, -int(item.get("cadenceMinutes") or 999), int(item.get("overlapRows") or 0))

    best = sorted(clean, key=best_key, reverse=True)[0] if clean else None
    blockers: list[str] = []
    if not clean:
        blockers.append("no-current-local-nq-file-pair-is-internally-clean")
    blockers.append("broker-parity-not-checked-by-this-artifact")
    return {
        "command": "futures-nq-current-data-parity",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForDemoExpansion": False,
        "readyForExecution": False,
        "comparisons": comparisons,
        "cleanLocalResearchPairCount": len(clean),
        "bestCurrentLocalResearchPair": best,
        "brokerParityChecked": False,
        "blockers": blockers,
        "decision": "research-only-current-local-parity-ready" if clean else "research-only-current-local-parity-blocked",
        "hardRules": [
            "Local file parity is not broker parity.",
            "A clean local research pair cannot approve Topstep demo expansion.",
            "Realtime execution-grade data must still pass data freshness and broker reconciliation.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    generated_date = str(payload.get("generatedAt") or current_utc_date())[:10]
    lines = [
        f"# Futures NQ Current Data Parity - {generated_date}",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only local current-data parity audit. This page does not approve Topstep demo or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Clean local research pairs: `{payload.get('cleanLocalResearchPairCount')}`",
        f"- Best pair: `{(payload.get('bestCurrentLocalResearchPair') or {}).get('pairId')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Comparisons",
        "",
    ]
    for item in payload.get("comparisons") or []:
        lines.append(
            f"- `{item.get('pairId')}` ok `{item.get('ok')}`, overlap `{item.get('overlapRows')}`, "
            f"max price diff `{item.get('maxPriceAbsDiff')}`, max volume diff `{item.get('maxVolumeAbsDiff')}`, reason `{item.get('reason')}`"
        )
    lines.extend(["", "## Hard Rules", ""])
    for rule in payload.get("hardRules") or []:
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit current local NQ file parity.")
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
