#!/usr/bin/env python3
"""Research-only NQ session-structure audit for external 1m data.

This checks whether the verified Seagate NQ 1m feature file is suitable for
session/ORB research. It does not optimize parameters, route orders, or approve
demo expansion.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
DEFAULT_INPUT = Path("/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_1_minute.parquet")
DEFAULT_EXTERNAL_AUDIT = STATE / "external-alpha-data-audit.latest.json"
DEFAULT_CURRENT_PARITY = STATE / "futures-nq-current-data-parity.latest.json"
OUT = STATE / "futures-nq-session-structure-audit.latest.json"
VAULT = Path.home() / "Documents/memorybrain"
OUT_MD = VAULT / "Agent-Hermes" / "futures-nq-session-structure-audit-2026-05-30.md"

UTC = ZoneInfo("UTC")
NEW_YORK = ZoneInfo("America/New_York")
NY_SESSION_START = time(9, 30)
NY_SESSION_END = time(16, 0)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_rows(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    if path.suffix == ".parquet":
        return (
            pl.scan_parquet(path)
            .select(["ts", "open", "high", "low", "close", "volume"])
            .sort("ts")
            .collect()
        )
    frame = pl.scan_csv(path)
    columns = frame.collect_schema().names()
    lower_map = {column.lower(): column for column in columns}
    selected = frame
    symbol_col = lower_map.get("symbol")
    if symbol_col:
        selected = selected.filter(pl.col(symbol_col).cast(pl.Utf8) == "NQ")
    return (
        selected
        .select([
            pl.col(lower_map.get("ts") or lower_map.get("datetime") or "ts").str.to_datetime(strict=False, time_zone="UTC").alias("ts"),
            pl.col(lower_map.get("open", "open")).cast(pl.Float64).alias("open"),
            pl.col(lower_map.get("high", "high")).cast(pl.Float64).alias("high"),
            pl.col(lower_map.get("low", "low")).cast(pl.Float64).alias("low"),
            pl.col(lower_map.get("close", "close")).cast(pl.Float64).alias("close"),
            pl.col(lower_map.get("volume", "volume")).cast(pl.Float64).alias("volume"),
        ])
        .sort("ts")
        .collect()
    )


def infer_cadence_minutes(frame: pl.DataFrame, fallback: int = 1) -> int:
    if frame.height < 2:
        return fallback
    values = [
        row["ts"]
        for row in frame.head(min(frame.height, 200)).to_dicts()
        if isinstance(row.get("ts"), datetime)
    ]
    deltas = sorted(
        int((right - left).total_seconds() / 60)
        for left, right in zip(values, values[1:])
        if int((right - left).total_seconds() / 60) > 0
    )
    if not deltas:
        return fallback
    return deltas[len(deltas) // 2]


def as_new_york(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(NEW_YORK)


def in_ny_session(ts: datetime) -> bool:
    stamp = as_new_york(ts).time()
    return NY_SESSION_START <= stamp <= NY_SESSION_END


def session_date(ts: datetime) -> str:
    return as_new_york(ts).date().isoformat()


def summarize_session(day: str, rows: list[dict[str, Any]], orb_minutes: int) -> dict[str, Any]:
    rows = sorted(rows, key=lambda item: item["ts"])
    opening_end = rows[0]["ts"] + timedelta(minutes=orb_minutes)
    opening = [row for row in rows if row["ts"] < opening_end]
    if not opening:
        opening = rows[:1]
    session_open = float(rows[0]["open"])
    session_close = float(rows[-1]["close"])
    session_high = max(float(row["high"]) for row in rows)
    session_low = min(float(row["low"]) for row in rows)
    opening_high = max(float(row["high"]) for row in opening)
    opening_low = min(float(row["low"]) for row in opening)
    after_opening = [row for row in rows if row["ts"] >= opening_end]
    first_break: dict[str, Any] | None = None
    for row in after_opening:
        high = float(row["high"])
        low = float(row["low"])
        if high > opening_high:
            first_break = {"direction": "long", "ts": str(row["ts"]), "level": opening_high}
            break
        if low < opening_low:
            first_break = {"direction": "short", "ts": str(row["ts"]), "level": opening_low}
            break
    close_location = (session_close - session_low) / (session_high - session_low) if session_high > session_low else None
    orb_close_r = None
    if first_break:
        risk = opening_high - opening_low
        if risk > 0:
            if first_break["direction"] == "long":
                orb_close_r = (session_close - opening_high) / risk
            else:
                orb_close_r = (opening_low - session_close) / risk
    return {
        "date": day,
        "rows": len(rows),
        "sessionOpen": round(session_open, 4),
        "sessionClose": round(session_close, 4),
        "sessionHigh": round(session_high, 4),
        "sessionLow": round(session_low, 4),
        "sessionRangePoints": round(session_high - session_low, 4),
        "openingRangeMinutes": orb_minutes,
        "openingRangePoints": round(opening_high - opening_low, 4),
        "firstBreak": first_break,
        "orbCloseR": round(orb_close_r, 6) if orb_close_r is not None else None,
        "closeLocation": round(close_location, 6) if close_location is not None else None,
        "trendDay": close_location is not None and (close_location >= 0.75 or close_location <= 0.25),
    }


def choose_input(args: argparse.Namespace, current_parity: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    explicit = Path(args.input)
    if getattr(args, "input_was_explicit", False) or not current_parity:
        return explicit, {
            "kind": "explicit-or-default",
            "path": str(explicit),
            "cadenceMinutes": args.cadence_minutes or None,
        }
    best_pair = current_parity.get("bestCurrentLocalResearchPair") if isinstance(current_parity.get("bestCurrentLocalResearchPair"), dict) else {}
    left_path = str(best_pair.get("leftPath") or "")
    if left_path and Path(left_path).exists() and bool(best_pair.get("researchClean")):
        return Path(left_path), {
            "kind": "current-local-clean-pair",
            "pairId": best_pair.get("pairId"),
            "path": left_path,
            "cadenceMinutes": best_pair.get("cadenceMinutes"),
        }
    return explicit, {
        "kind": "explicit-or-default",
        "path": str(explicit),
        "cadenceMinutes": args.cadence_minutes or None,
    }


def default_min_session_rows(cadence_minutes: int) -> int:
    if cadence_minutes <= 1:
        return 120
    if cadence_minutes <= 5:
        return 60
    return 18


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    current_parity = read_json(Path(args.current_parity))
    input_path, input_source = choose_input(args, current_parity)
    frame = load_rows(input_path)
    external_audit = read_json(Path(args.external_audit))
    source_parity = external_audit.get("nqSourceParity") if isinstance(external_audit.get("nqSourceParity"), dict) else {}
    local_parity = external_audit.get("nqLocalParity") if isinstance(external_audit.get("nqLocalParity"), dict) else {}
    best_pair = current_parity.get("bestCurrentLocalResearchPair") if isinstance(current_parity.get("bestCurrentLocalResearchPair"), dict) else {}
    current_internal_ok = int(current_parity.get("cleanLocalResearchPairCount") or 0) > 0
    broker_parity_checked = bool(current_parity.get("brokerParityChecked"))
    source_ok = bool(source_parity.get("ok")) or (input_source.get("kind") == "current-local-clean-pair" and current_internal_ok)
    if frame.is_empty():
        sessions: list[dict[str, Any]] = []
        ranges = {}
        cadence_minutes = int(input_source.get("cadenceMinutes") or args.cadence_minutes or 1)
    else:
        cadence_minutes = int(args.cadence_minutes or input_source.get("cadenceMinutes") or infer_cadence_minutes(frame))
        min_session_rows = args.min_session_rows or default_min_session_rows(cadence_minutes)
        ranges = {
            "min": str(frame.select(pl.min("ts")).item()),
            "max": str(frame.select(pl.max("ts")).item()),
            "rows": frame.height,
        }
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in frame.to_dicts():
            ts = row["ts"]
            if not isinstance(ts, datetime) or not in_ny_session(ts):
                continue
            buckets.setdefault(session_date(ts), []).append(row)
        sessions = [
            summarize_session(day, rows, args.opening_range_minutes)
            for day, rows in sorted(buckets.items())
            if len(rows) >= min_session_rows
        ]
    breakout_sessions = [item for item in sessions if item.get("firstBreak")]
    orb_values = [float(item["orbCloseR"]) for item in breakout_sessions if item.get("orbCloseR") is not None]
    trend_days = sum(1 for item in sessions if item.get("trendDay"))
    blockers = []
    if not source_ok:
        blockers.append("nq-source-parity-not-cleared")
    if not current_internal_ok:
        blockers.append("current-internal-local-parity-not-cleared")
    if not local_parity.get("ok"):
        blockers.append("current-local-or-broker-parity-not-cleared")
    if len(sessions) < args.min_oos_sessions:
        blockers.append("too-few-sessions-for-oos-research-contract")
    return {
        "command": "futures-nq-session-structure-audit",
        "generatedAt": now_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForDemoExpansion": False,
        "inputPath": str(input_path.resolve()),
        "inputSource": input_source,
        "range": ranges,
        "cadenceMinutes": cadence_minutes,
        "minSessionRows": args.min_session_rows or default_min_session_rows(cadence_minutes),
        "sourceParityOk": source_ok,
        "currentInternalParityOk": current_internal_ok,
        "bestCurrentLocalResearchPair": best_pair.get("pairId"),
        "brokerParityChecked": broker_parity_checked,
        "localParityOk": bool(local_parity.get("ok")),
        "sessionDefinition": {
            "sourceTimestampAssumption": "naive parquet timestamps are treated as UTC",
            "timezone": "America/New_York",
            "start": NY_SESSION_START.isoformat(),
            "end": NY_SESSION_END.isoformat(),
            "openingRangeMinutes": args.opening_range_minutes,
        },
        "sessionCount": len(sessions),
        "breakoutSessionCount": len(breakout_sessions),
        "trendDayCount": trend_days,
        "meanOrbCloseR": round(sum(orb_values) / len(orb_values), 6) if orb_values else None,
        "sessions": sessions,
        "decision": "research-only-insufficient-history-for-oos" if blockers else "research-only-session-smoke-ready",
        "blockers": blockers,
        "nextAction": (
            "Use this only as a source-build smoke test; obtain a longer/current NQ 1m dataset before OOS/Topstep demo evidence."
            if blockers
            else "Proceed to purged OOS session-structure replay, still research-only."
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Futures NQ Session Structure Audit - 2026-05-30",
        "",
        "Parent hub: [[BILL-CONTROL-HUB]]",
        "",
        "Research-only audit. This page does not approve Topstep demo or live trading.",
        "",
        "## Summary",
        "",
        f"- Decision: `{payload.get('decision')}`",
        f"- Source parity OK: `{payload.get('sourceParityOk')}`",
        f"- Local/current parity OK: `{payload.get('localParityOk')}`",
        f"- Input range: `{payload.get('range')}`",
        f"- Session count: `{payload.get('sessionCount')}`",
        f"- Breakout sessions: `{payload.get('breakoutSessionCount')}`",
        f"- Trend days: `{payload.get('trendDayCount')}`",
        f"- Mean ORB close R: `{payload.get('meanOrbCloseR')}`",
        f"- Blockers: `{payload.get('blockers')}`",
        "",
        "## Sessions",
        "",
    ]
    for item in payload.get("sessions") or []:
        first_break = item.get("firstBreak") or {}
        lines.append(
            f"- `{item.get('date')}` rows `{item.get('rows')}`, range `{item.get('sessionRangePoints')}`, "
            f"OR `{item.get('openingRangePoints')}`, break `{first_break.get('direction')}`, closeR `{item.get('orbCloseR')}`, trend `{item.get('trendDay')}`"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit external NQ 1m session structure.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--external-audit", default=str(DEFAULT_EXTERNAL_AUDIT))
    parser.add_argument("--current-parity", default=str(DEFAULT_CURRENT_PARITY))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--markdown-output", default=str(OUT_MD))
    parser.add_argument("--cadence-minutes", type=int, default=0)
    parser.add_argument("--opening-range-minutes", type=int, default=30)
    parser.add_argument("--min-session-rows", type=int, default=0)
    parser.add_argument("--min-oos-sessions", type=int, default=20)
    args = parser.parse_args()
    args.input_was_explicit = "--input" in __import__("sys").argv
    payload = build_report(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md = Path(args.markdown_output)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_markdown(payload))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
