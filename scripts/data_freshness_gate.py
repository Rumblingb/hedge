#!/usr/bin/env python3
"""
Data Freshness Gate — blocks trading if NQ/ES data is stale.
Reads from the real-time quote state file (realtime-quote.latest.json)
written by realtime_data_bridge.py (TradingView WebSocket, ~600ms delay).

Previously used Yahoo Finance (2-10min delay) — now uses sub-second TV data.
Falls back to Yahoo if real-time state file is missing/corrupted.
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

CANONICAL_STATE_DIR = Path.home() / "hedge" / ".rumbling-hedge" / "state"
LEGACY_STATE_DIR = Path.home() / ".rumbling-hedge" / "state"
STATE_DIR = CANONICAL_STATE_DIR
REALTIME_STATE = CANONICAL_STATE_DIR / "realtime-quote.latest.json"
LEGACY_REALTIME_STATE = LEGACY_STATE_DIR / "realtime-quote.latest.json"
MAX_DATA_AGE_SECONDS = 60  # Must be < 60s (cron runs every 30s)
FALLBACK_MAX_AGE = 300     # Yahoo fallback allows up to 5 min
EXECUTION_GRADE_SOURCES = {
    "tradingview_pro",
    "tradingview_ws",
    "broker_realtime",
    "topstep_realtime",
    "databento_realtime",
}


def non_execution_grade_reason(source, update_mode):
    source = str(source or "unknown")
    update_mode = str(update_mode or "unknown").lower()
    if source == "yahoo_fallback" or source == "yahoo":
        return "fallback quote is delayed/research-only, not execution-grade realtime data"
    if source == "tradingview_public":
        return "public TradingView quote is delayed/research-only, not execution-grade realtime data"
    if "delayed" in update_mode:
        return f"quote update_mode={update_mode} is delayed/research-only, not execution-grade realtime data"
    if source not in EXECUTION_GRADE_SOURCES:
        return f"quote source={source} is not in the execution-grade source allowlist"
    return None


def check_freshness_from_realtime(symbol="nq", max_age=MAX_DATA_AGE_SECONDS):
    """
    Check freshness from realtime-quote.latest.json (TradingView WebSocket data).
    Returns same format as the old Yahoo-based check_freshness().
    """
    sym_field = f"price_{symbol}"
    mode_field = f"update_mode_{symbol}"

    state_path = REALTIME_STATE if REALTIME_STATE.exists() else LEGACY_REALTIME_STATE

    if not state_path.exists():
        return {"status": "STALE", "symbol": symbol, "reason": "no_realtime_state",
                "age_seconds": None, "last_price": None, "max_age": max_age}

    try:
        data = json.loads(state_path.read_text())
        price = data.get(sym_field)
        ts_str = data.get("timestamp") or data.get("bridge_generated_at")

        if price is None:
            return {"status": "BLOCK", "symbol": symbol, "reason": "no_price_in_state",
                    "age_seconds": None, "last_price": None, "max_age": max_age}

        if not ts_str:
            return {"status": "BLOCK", "symbol": symbol, "reason": "no_timestamp",
                    "age_seconds": None, "last_price": price, "max_age": max_age}

        source = data.get("source", "unknown")
        update_mode = data.get(mode_field, "unknown")
        blocked_reason = non_execution_grade_reason(source, update_mode)
        if blocked_reason:
            return {
                "status": "STALE",
                "symbol": symbol,
                "last_price": price,
                "last_bar_ts": ts_str,
                "age_seconds": None,
                "max_age": max_age,
                "source": source,
                "state_path": str(state_path),
                "update_mode": update_mode,
                "reason": blocked_reason,
            }

        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - ts).total_seconds()

        status = "PASS" if age < max_age else "STALE"
        reason = "ok" if age < max_age else f"data {age:.0f}s old (max {max_age}s)"

        return {
            "status": status,
            "symbol": symbol,
            "last_price": price,
            "last_bar_ts": ts_str,
            "age_seconds": round(age, 1),
            "max_age": max_age,
            "source": source,
            "state_path": str(state_path),
            "update_mode": update_mode,
            "reason": reason,
        }
    except Exception as e:
        return {"status": "BLOCK", "symbol": symbol, "reason": f"error_reading_state: {e}",
                "age_seconds": None, "last_price": None, "max_age": max_age}


def check_freshness_yahoo(symbol="NQ=F", max_age=FALLBACK_MAX_AGE):
    """
    Fallback: check freshness via Yahoo Finance (2-10min delay).
    Only used when real-time state file is unavailable.
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d", interval="1m")
        if hist.empty:
            return {"status": "BLOCK", "symbol": symbol, "reason": "no_data", "age_seconds": None}
        last_ts = hist.index[-1]
        age = (datetime.now(timezone.utc) - last_ts).total_seconds()
        last_price = float(hist.iloc[-1]["Close"])
        return {
            "status": "PASS" if age < max_age else "STALE",
            "symbol": symbol,
            "last_price": last_price,
            "last_bar_ts": last_ts.isoformat(),
            "age_seconds": round(age, 1),
            "max_age": max_age,
            "source": "yahoo",
            "reason": "ok" if age < max_age else f"data {age:.0f}s old (max {max_age}s)"
        }
    except Exception as e:
        return {"status": "BLOCK", "symbol": symbol, "reason": f"error: {e}", "age_seconds": None}


def check_freshness(symbol="NQ=F", max_age=MAX_DATA_AGE_SECONDS):
    """
    Primary entry point for master bridge.
    Tries realtime state first, falls back to Yahoo.
    Maps symbol names: "NQ=F" → "nq", "ES=F" → "es"
    """
    sym_map = {"NQ=F": "nq", "ES=F": "es", "MNQ=F": "nq", "MES=F": "es"}
    rt_symbol = sym_map.get(symbol, "nq")

    # Try realtime state first
    result = check_freshness_from_realtime(rt_symbol, max_age)
    if result["status"] != "BLOCK":
        return result

    # Fall back to Yahoo on BLOCK
    yahoo_result = check_freshness_yahoo(symbol, max_age)
    return yahoo_result


def main():
    checks = [check_freshness("NQ=F"), check_freshness("ES=F")]
    verdict = "PASS"
    for c in checks:
        if c["status"] == "BLOCK":
            verdict = "BLOCK"
            break
        if c["status"] == "STALE":
            verdict = "STALE"

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "checks": checks,
        "action": "block_all_trades" if verdict in ("BLOCK", "STALE") else "allow_trades"
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = STATE_DIR / "data-freshness-gate.latest.json"
    output_path.write_text(json.dumps(result, indent=2))
    LEGACY_STATE_DIR.mkdir(parents=True, exist_ok=True)
    (LEGACY_STATE_DIR / "data-freshness-gate.latest.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
