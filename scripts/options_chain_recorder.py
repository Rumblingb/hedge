#!/usr/bin/env python3
"""Options chain recorder — research-only foundation for the options-us lane.

Goal blocker: "options-us: missing-options-chain-history-and-paper-router"
closeWith: "build options chain recorder before strategies"

This script:
  - pulls free option chains for QQQ and SPY (liquid NQ/ES proxies) via yfinance
  - for each symbol, records the 3 nearest expiries, strikes within +/-5% of spot
  - appends one JSON line per snapshot (full chain) to
      .rumbling-hedge/state/options-chain/YYYY-MM-DD/{SYMBOL}.jsonl
  - writes a summary artifact to
      .rumbling-hedge/state/options-chain-snapshot.latest.json
  - rotates dated directories older than 30 days

Strictly research-only: no broker access, no order routing, no trading env
changes. researchOnly=true / writesOrders=false / touchesBroker=false in all
artifacts.
"""
import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

STATE_DIR = Path(".rumbling-hedge/state")
CHAIN_DIR = STATE_DIR / "options-chain"
SUMMARY_PATH = STATE_DIR / "options-chain-snapshot.latest.json"

SYMBOLS = ["QQQ", "SPY"]
NEAREST_EXPIRIES = 3
STRIKE_BAND_PCT = 0.05  # +/- 5% of spot
RETENTION_DAYS = 30


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def to_float(value):
    try:
        if value is None:
            return None
        f = float(value)
        if f != f:  # NaN check
            return None
        return f
    except (TypeError, ValueError):
        return None


def to_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_spot(ticker):
    try:
        fast_info = ticker.fast_info
        for key in ("lastPrice", "last_price", "regularMarketPreviousClose", "previousClose"):
            value = None
            try:
                value = fast_info[key]
            except (KeyError, TypeError):
                value = getattr(fast_info, key, None)
            value = to_float(value)
            if value is not None:
                return value
    except Exception:
        pass
    try:
        info = ticker.info
        for key in ("regularMarketPrice", "previousClose", "currentPrice"):
            value = to_float(info.get(key))
            if value is not None:
                return value
    except Exception:
        pass
    return None


def contract_to_dict(row, contract_type, expiry):
    return {
        "expiry": expiry,
        "strike": to_float(row.get("strike")),
        "type": contract_type,
        "bid": to_float(row.get("bid")),
        "ask": to_float(row.get("ask")),
        "last": to_float(row.get("lastPrice")),
        "volume": to_int(row.get("volume")),
        "openInterest": to_int(row.get("openInterest")),
        "impliedVolatility": to_float(row.get("impliedVolatility")),
    }


def nearest_strike_iv(contracts, target_strike, contract_type):
    candidates = [
        c for c in contracts
        if c["type"] == contract_type and c["impliedVolatility"] is not None and c["strike"] is not None
    ]
    if not candidates:
        return None
    best = min(candidates, key=lambda c: abs(c["strike"] - target_strike))
    return best["impliedVolatility"]


def atm_iv_for_expiry(contracts, spot, expiry):
    expiry_contracts = [c for c in contracts if c["expiry"] == expiry]
    call_iv = nearest_strike_iv(expiry_contracts, spot, "call")
    put_iv = nearest_strike_iv(expiry_contracts, spot, "put")
    ivs = [v for v in (call_iv, put_iv) if v is not None]
    if not ivs:
        return None
    return sum(ivs) / len(ivs)


def skew_proxy(contracts, spot, expiry):
    """25-delta-ish proxy: IV at ~97.5% strike (put) minus IV at ~102.5% strike (call)."""
    expiry_contracts = [c for c in contracts if c["expiry"] == expiry]
    low_strike = spot * 0.975
    high_strike = spot * 1.025
    low_iv = nearest_strike_iv(expiry_contracts, low_strike, "put")
    high_iv = nearest_strike_iv(expiry_contracts, high_strike, "call")
    if low_iv is None or high_iv is None:
        return None
    return low_iv - high_iv


def put_call_volume_ratio(contracts):
    put_vol = sum(c["volume"] or 0 for c in contracts if c["type"] == "put")
    call_vol = sum(c["volume"] or 0 for c in contracts if c["type"] == "call")
    if call_vol == 0:
        return None
    return put_vol / call_vol


def record_symbol(yf_module, symbol, snapshot_dir):
    ticker = yf_module.Ticker(symbol)

    spot = fetch_spot(ticker)
    if spot is None:
        return {
            "symbol": symbol,
            "status": "no-data",
            "reason": "could not determine spot price",
        }

    try:
        all_expiries = list(ticker.options or [])
    except Exception as exc:
        return {
            "symbol": symbol,
            "status": "no-data",
            "reason": "options() failed: %s" % exc,
            "spot": spot,
        }

    if not all_expiries:
        return {
            "symbol": symbol,
            "status": "no-data",
            "reason": "no expiries returned",
            "spot": spot,
        }

    expiries = all_expiries[:NEAREST_EXPIRIES]
    low_strike = spot * (1 - STRIKE_BAND_PCT)
    high_strike = spot * (1 + STRIKE_BAND_PCT)

    contracts = []
    for expiry in expiries:
        try:
            chain = ticker.option_chain(expiry)
        except Exception:
            continue

        for contract_type, df in (("call", chain.calls), ("put", chain.puts)):
            for _, row in df.iterrows():
                strike = to_float(row.get("strike"))
                if strike is None:
                    continue
                if not (low_strike <= strike <= high_strike):
                    continue
                contracts.append(contract_to_dict(row, contract_type, expiry))

    if not contracts:
        return {
            "symbol": symbol,
            "status": "no-data",
            "reason": "no contracts within strike band",
            "spot": spot,
            "expiries": expiries,
        }

    atm_iv_by_expiry = {expiry: atm_iv_for_expiry(contracts, spot, expiry) for expiry in expiries}
    atm_iv = atm_iv_by_expiry.get(expiries[0])

    skew = skew_proxy(contracts, spot, expiries[0])

    pc_ratio = put_call_volume_ratio(contracts)

    term_slope = None
    if len(expiries) >= 2:
        iv1 = atm_iv_by_expiry.get(expiries[0])
        iv2 = atm_iv_by_expiry.get(expiries[1])
        if iv1 is not None and iv2 is not None:
            term_slope = iv2 - iv1

    snapshot = {
        "generatedAt": now_utc_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "symbol": symbol,
        "spot": spot,
        "expiries": expiries,
        "strikeBand": {"low": low_strike, "high": high_strike, "pct": STRIKE_BAND_PCT},
        "contracts": contracts,
        "derived": {
            "atm_iv": atm_iv,
            "atm_iv_by_expiry": atm_iv_by_expiry,
            "skew_proxy": skew,
            "pc_volume_ratio": pc_ratio,
            "term_slope": term_slope,
        },
    }

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = snapshot_dir / ("%s.jsonl" % symbol)
    with jsonl_path.open("a") as f:
        f.write(json.dumps(snapshot) + "\n")

    return {
        "symbol": symbol,
        "status": "ok",
        "spot": spot,
        "atm_iv": atm_iv,
        "skew": skew,
        "pc_volume_ratio": pc_ratio,
        "term_slope": term_slope,
        "contracts_recorded": len(contracts),
        "expiries": expiries,
    }


def rotate_old_snapshots(retention_days=RETENTION_DAYS):
    if not CHAIN_DIR.exists():
        return
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=retention_days)
    for entry in CHAIN_DIR.iterdir():
        if not entry.is_dir():
            continue
        try:
            entry_date = datetime.strptime(entry.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if entry_date < cutoff:
            shutil.rmtree(entry, ignore_errors=True)


def count_history_days():
    if not CHAIN_DIR.exists():
        return 0
    count = 0
    for entry in CHAIN_DIR.iterdir():
        if entry.is_dir():
            try:
                datetime.strptime(entry.name, "%Y-%m-%d")
                count += 1
            except ValueError:
                continue
    return count


def main():
    try:
        import yfinance as yf
    except ImportError:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps({
            "generatedAt": now_utc_iso(),
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "status": "no-data",
            "reason": "yfinance not available",
            "symbols": {},
            "history_days_accumulated": count_history_days(),
        }, indent=2) + "\n")
        return 0

    snapshot_dir = CHAIN_DIR / today_str()
    symbols_summary = {}

    for symbol in SYMBOLS:
        try:
            result = record_symbol(yf, symbol, snapshot_dir)
        except Exception as exc:
            result = {"symbol": symbol, "status": "no-data", "reason": "unexpected error: %s" % exc}
        symbols_summary[symbol] = result

    rotate_old_snapshots()

    overall_status = "ok" if any(v.get("status") == "ok" for v in symbols_summary.values()) else "no-data"

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps({
        "generatedAt": now_utc_iso(),
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "status": overall_status,
        "symbols": symbols_summary,
        "history_days_accumulated": count_history_days(),
    }, indent=2) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
