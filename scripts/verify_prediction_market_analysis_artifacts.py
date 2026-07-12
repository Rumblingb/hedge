#!/usr/bin/env python3
"""Verify compact prediction-market analysis artifacts have sane scales.

This is a research-data guard. It does not read credentials, call networks, or
touch execution paths.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / ".rumbling-hedge" / "research" / "prediction-market-analysis"


def read_json(path: Path):
    return json.loads(path.read_text())


def assert_rate_rows(path: Path) -> int:
    payload = read_json(path)
    rows = payload.get("rows") or []
    if not rows:
        raise AssertionError(f"{path} has no rows")
    for index, row in enumerate(rows):
        rate = row.get("win_rate")
        pct = row.get("win_rate_pct")
        if not isinstance(rate, (int, float)) or not 0 <= rate <= 1:
            raise AssertionError(f"{path} row {index} win_rate must be a 0..1 fraction, got {rate!r}")
        if pct is None:
            raise AssertionError(f"{path} row {index} missing win_rate_pct")
        if not isinstance(pct, (int, float)) or not 0 <= pct <= 100:
            raise AssertionError(f"{path} row {index} win_rate_pct must be a 0..100 percent, got {pct!r}")
        if abs((rate * 100) - pct) > 0.01:
            raise AssertionError(f"{path} row {index} win_rate_pct does not match win_rate: {rate!r}, {pct!r}")
    return len(rows)


def assert_maker_taker(path: Path) -> int:
    payload = read_json(path)
    rows = payload.get("rows") or []
    if not rows:
        raise AssertionError(f"{path} has no rows")
    roles = {row.get("role") for row in rows}
    if roles != {"maker", "taker"}:
        raise AssertionError(f"{path} expected maker and taker roles, got {roles!r}")
    for index, row in enumerate(rows):
        rate = row.get("win_rate")
        implied = row.get("implied_rate")
        excess = row.get("excess_return")
        for key, value in [("win_rate", rate), ("implied_rate", implied)]:
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise AssertionError(f"{path} row {index} {key} must be 0..1, got {value!r}")
        if not isinstance(excess, (int, float)) or not -1 <= excess <= 1:
            raise AssertionError(f"{path} row {index} excess_return must be -1..1, got {excess!r}")
        if abs((rate - implied) - excess) > 0.0001:
            raise AssertionError(f"{path} row {index} excess_return does not match win_rate-implied_rate")
    return len(rows)


def main() -> int:
    summary = read_json(ANALYSIS_DIR / "summary.json")
    if summary.get("status") != "ok":
        raise AssertionError(f"summary status is not ok: {summary.get('status')!r}")

    checked = {
        "kalshiWinRateRows": assert_rate_rows(ANALYSIS_DIR / "kalshi-win-rate-by-price.json"),
        "polymarketWinRateRows": assert_rate_rows(ANALYSIS_DIR / "polymarket-win-rate-by-price.json"),
        "kalshiMakerTakerRows": assert_maker_taker(ANALYSIS_DIR / "kalshi-maker-taker-returns.json"),
    }
    print(json.dumps({
        "ok": True,
        "checked": checked,
        "artifactDir": str(ANALYSIS_DIR),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
