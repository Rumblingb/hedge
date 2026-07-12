#!/usr/bin/env python3
"""
Normalize the Kaggle Seagate NQ 1-minute futures dataset (2022-2025) into the
repo's standard bar schema: ts,symbol,open,high,low,close,volume

Input schema (ET local timestamps, M/D/YYYY H:MM, no DST info):
  timestamp ET,open,high,low,close,volume,Vwap_RTH,Vwap_ETH

Output:
  data/free/NQ-1m-2022-2025-normalized.csv   (1-minute bars)
  data/free/NQ-15m-2022-2025-normalized.csv  (resampled to 15-minute)
  data/free/NQ-60m-2022-2025-normalized.csv  (resampled to 60-minute)

All output timestamps are UTC ISO-8601 (e.g. 2022-12-26T23:01:00.000Z), with
the input ET wall-clock time converted via zoneinfo (handles DST correctly).
"""

import csv
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = REPO_ROOT / "data/kaggle-seagate/nq-futures-1min-2022-2025/Dataset_NQ_1min_2022_2025.csv"
OUT_1M = REPO_ROOT / "data/free/NQ-1m-2022-2025-normalized.csv"
OUT_15M = REPO_ROOT / "data/free/NQ-15m-2022-2025-normalized.csv"
OUT_60M = REPO_ROOT / "data/free/NQ-60m-2022-2025-normalized.csv"

SYMBOL = "NQ"


def parse_et_to_utc_iso(ts_str: str) -> str:
    """Parse 'M/D/YYYY H:MM' as US/Eastern wall-clock time and return UTC ISO-8601 ms."""
    dt_naive = datetime.strptime(ts_str.strip(), "%m/%d/%Y %H:%M")
    dt_et = dt_naive.replace(tzinfo=ET)
    dt_utc = dt_et.astimezone(UTC)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def load_and_normalize():
    rows = []
    with open(INPUT_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            ts_iso = parse_et_to_utc_iso(r["timestamp ET"])
            rows.append({
                "ts": ts_iso,
                "symbol": SYMBOL,
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["volume"]),
            })

    # Sort by ts, dedup on ts (keep last occurrence)
    rows.sort(key=lambda x: x["ts"])
    deduped = {}
    for r in rows:
        deduped[r["ts"]] = r
    out_rows = [deduped[k] for k in sorted(deduped.keys())]
    return out_rows


def fmt_num(v):
    if float(v).is_integer():
        return f"{v:.2f}"
    return repr(float(v))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ts", "symbol", "open", "high", "low", "close", "volume"])
        for r in rows:
            writer.writerow([
                r["ts"], r["symbol"],
                fmt_num(r["open"]), fmt_num(r["high"]), fmt_num(r["low"]), fmt_num(r["close"]),
                fmt_num(r["volume"]),
            ])


def resample(rows, minutes: int):
    """Resample 1m bars to N-minute bars, bucketed by floor(epoch_seconds / bucket_size_s) in UTC."""
    bucket_size_s = minutes * 60
    buckets = {}
    order = []
    for r in rows:
        dt = datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=UTC)
        epoch = int(dt.timestamp())
        bucket_start = (epoch // bucket_size_s) * bucket_size_s
        if bucket_start not in buckets:
            buckets[bucket_start] = []
            order.append(bucket_start)
        buckets[bucket_start].append(r)

    order.sort()
    out_rows = []
    for bucket_start in order:
        bars_sorted = sorted(buckets[bucket_start], key=lambda x: x["ts"])
        ts_iso = datetime.fromtimestamp(bucket_start, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        out_rows.append({
            "ts": ts_iso,
            "symbol": SYMBOL,
            "open": bars_sorted[0]["open"],
            "high": max(b["high"] for b in bars_sorted),
            "low": min(b["low"] for b in bars_sorted),
            "close": bars_sorted[-1]["close"],
            "volume": sum(b["volume"] for b in bars_sorted),
        })
    return out_rows


def main():
    print(f"Reading {INPUT_PATH} ...")
    rows = load_and_normalize()
    print(f"1m rows after sort/dedup: {len(rows)}")
    print(f"Range: {rows[0]['ts']} -> {rows[-1]['ts']}")

    write_csv(OUT_1M, rows)
    print(f"Wrote {OUT_1M} ({len(rows)} rows)")

    rows_15m = resample(rows, 15)
    write_csv(OUT_15M, rows_15m)
    print(f"Wrote {OUT_15M} ({len(rows_15m)} rows)")

    rows_60m = resample(rows, 60)
    write_csv(OUT_60M, rows_60m)
    print(f"Wrote {OUT_60M} ({len(rows_60m)} rows)")

    print("\nSanity checks:")
    print(f"First 1m bar: {rows[0]}")
    print(f"Last 1m bar: {rows[-1]}")
    expected_first_ts = "2022-12-26T23:01:00.000Z"
    if rows[0]["ts"] == expected_first_ts:
        print(f"OK: first ts matches expected {expected_first_ts}")
    else:
        print(f"WARN: first ts {rows[0]['ts']} != expected {expected_first_ts}")


if __name__ == "__main__":
    sys.exit(main())
