#!/usr/bin/env python3
"""
COT Signal Generator — CFTC Commitment of Traders
==================================================
Government filing analysis for contrarian position-based signals.

Uses CFTC's TFF (Treasury & Finance) and Disaggregated data to track:
- Dealer (commercial) positioning → contrarian signal
- Asset Manager positioning → trend confirmation
- Leveraged Money (hedge fund) positioning → smart money signal
- Open Interest changes → participation flow

Theory:
- Dealers (commercials) are net short to hedge. When they're extremely
  net short, it means retail is extremely long → contrarian sell signal
- Leveraged Money (hedge funds) are the "smart money" — their net
  positioning has predictive power at extremes
- Asset Managers (pension funds, etc.) trend-follow

Output: ~/.rumbling-hedge/state/cot-signal.latest.json
"""

import csv, json, os, sys, statistics
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

STATE_DIR = Path(os.path.expanduser("~/.rumbling-hedge/state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "cot-signal.latest.json"

COT_DIR = Path("/Users/brain/hedge/.rumbling-hedge/research/cot")

# TFF format market names
MARKETS = {
    "ES": "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
    "NQ": "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
    "CL": "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
    "GC": "GOLD - COMMODITY EXCHANGE INC.",
}

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}")

def load_tff_records(csv_path: Path, market_name: str) -> List[Dict]:
    """Load TFF format records for a given market"""
    records = []
    if not csv_path.exists():
        return records
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Market_and_Exchange_Names", "").strip() == market_name:
                records.append(row)
    return records

def load_disagg_records(csv_path: Path, market_name: str) -> List[Dict]:
    """Load Disaggregated format records for a given market"""
    records = []
    if not csv_path.exists():
        return records
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Market_and_Exchange_Names", "").strip() == market_name:
                records.append(row)
    return records

def compute_z_score(values: List[float]) -> float:
    """Compute z-score of the latest value"""
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    std = statistics.stdev(values)
    if std == 0:
        return 0.0
    return (values[-1] - mean) / std

def analyze_tff(symbol: str, records: List[Dict]) -> Optional[Dict]:
    """Analyze TFF-format COT data for a single market"""
    if not records:
        return None
    
    last = records[-1]
    date = last.get("Report_Date_as_YYYY-MM-DD", "unknown")
    
    try:
        oi = float(last["Open_Interest_All"])
        d_long = float(last.get("Dealer_Positions_Long_All", 0))
        d_short = float(last.get("Dealer_Positions_Short_All", 0))
        d_spread = float(last.get("Dealer_Positions_Spread_All", 0))
        am_long = float(last.get("Asset_Mgr_Positions_Long_All", 0))
        am_short = float(last.get("Asset_Mgr_Positions_Short_All", 0))
        lm_long = float(last.get("Lev_Money_Positions_Long_All", 0))
        lm_short = float(last.get("Lev_Money_Positions_Short_All", 0))
    except (ValueError, KeyError) as e:
        log(f"  ⚠️ Parse error for {symbol}: {e}")
        return None
    
    # Net positions as % of OI
    net_dealer = (d_long - d_short) / oi * 100
    net_am = (am_long - am_short) / oi * 100
    net_lm = (lm_long - lm_short) / oi * 100
    
    # Compute z-scores over history
    dealer_nets = []
    am_nets = []
    lm_nets = []
    
    for r in records:
        try:
            oi_r = float(r["Open_Interest_All"])
            dl_r = float(r.get("Dealer_Positions_Long_All", 0))
            ds_r = float(r.get("Dealer_Positions_Short_All", 0))
            aml_r = float(r.get("Asset_Mgr_Positions_Long_All", 0))
            ams_r = float(r.get("Asset_Mgr_Positions_Short_All", 0))
            lml_r = float(r.get("Lev_Money_Positions_Long_All", 0))
            lms_r = float(r.get("Lev_Money_Positions_Short_All", 0))
            if oi_r > 0:
                dealer_nets.append((dl_r - ds_r) / oi_r * 100)
                am_nets.append((aml_r - ams_r) / oi_r * 100)
                lm_nets.append((lml_r - lms_r) / oi_r * 100)
        except:
            continue
    
    dealer_z = compute_z_score(dealer_nets) if len(dealer_nets) >= 5 else 0
    am_z = compute_z_score(am_nets) if len(am_nets) >= 5 else 0
    lm_z = compute_z_score(lm_nets) if len(lm_nets) >= 5 else 0
    
    # Generate signals
    signals = []
    
    # Dealer contrarian signal
    if dealer_z < -2.0:
        signals.append({"type": "DEALER_EXTREME_SHORT", "strength": 0.75,
                       "reason": f"Dealers extremely net short (z={dealer_z:+.1f}) — contrarian bullish"})
    elif dealer_z < -1.5:
        signals.append({"type": "DEALER_SHORT", "strength": 0.60,
                       "reason": f"Dealers net short (z={dealer_z:+.1f}) — mildly bullish"})
    elif dealer_z > 2.0:
        signals.append({"type": "DEALER_EXTREME_LONG", "strength": 0.75,
                       "reason": f"Dealers extremely net long (z={dealer_z:+.1f}) — contrarian bearish"})
    elif dealer_z > 1.5:
        signals.append({"type": "DEALER_LONG", "strength": 0.60,
                       "reason": f"Dealers net long (z={dealer_z:+.1f}) — mildly bearish"})
    
    # Leveraged Money (smart money) signal
    if lm_z > 1.5:
        signals.append({"type": "SMART_MONEY_BULLISH", "strength": 0.65,
                       "reason": f"Hedge funds net long (z={lm_z:+.1f}) — smart money bullish"})
    elif lm_z < -1.5:
        signals.append({"type": "SMART_MONEY_BEARISH", "strength": 0.65,
                       "reason": f"Hedge funds net short (z={lm_z:+.1f}) — smart money bearish"})
    
    # Asset manager trend confirmation
    if am_z > 1.0:
        signals.append({"type": "ASSET_MGR_TRENDING", "strength": 0.40,
                       "reason": f"Asset managers net long (z={am_z:+.1f}) — trend confirms"})
    
    # Determine net signal
    net_bullish = sum(1 for s in signals if "BULLISH" in s["type"] or "SHORT" in s["type"])
    net_bearish = sum(1 for s in signals if "BEARISH" in s["type"] or "LONG" in s["type"])
    
    if net_bullish > net_bearish:
        direction = "bullish"
    elif net_bearish > net_bullish:
        direction = "bearish"
    else:
        direction = "neutral"
    
    return {
        "symbol": symbol,
        "date": date,
        "records": len(records),
        "open_interest": round(oi, 0),
        "dealer": {
            "net_pct": round(net_dealer, 2),
            "z_score": round(dealer_z, 2),
            "long": round(d_long, 0),
            "short": round(d_short, 0),
        },
        "asset_manager": {
            "net_pct": round(net_am, 2),
            "z_score": round(am_z, 2),
        },
        "lev_money": {
            "net_pct": round(net_lm, 2),
            "z_score": round(lm_z, 2),
        },
        "signals": signals,
        "direction": direction,
        "source": "cot-cftc-tff",
    }

def run():
    log("COT Signal Generator — CFTC Commitment of Traders")
    
    tff_path = COT_DIR / "tff-2026.csv"
    disagg_path = COT_DIR / "disagg-2026.csv"
    
    if not tff_path.exists():
        log(f"❌ No COT data at {tff_path}")
        return None
    
    log(f"Using TFF data: {tff_path}")
    
    results = {}
    for symbol, market_name in MARKETS.items():
        records = load_tff_records(tff_path, market_name)
        if not records:
            log(f"  {symbol}: No records found (trying disagg...)")
            # Fallback: try disagg format
            records = load_disagg_records(disagg_path, market_name)
            if records:
                log(f"  {symbol}: {len(records)} records (disagg)")
            else:
                log(f"  {symbol}: ❌ No data")
                continue
        else:
            log(f"  {symbol}: {len(records)} records")
        
        result = analyze_tff(symbol, records)
        if result:
            results[symbol] = result
            log(f"    Dealer net: {result['dealer']['net_pct']:+.2f}% (z={result['dealer']['z_score']:+.1f})")
            log(f"    Smart money: {result['lev_money']['net_pct']:+.2f}% (z={result['lev_money']['z_score']:+.1f})")
            log(f"    Direction: {result['direction']}")
    
    if not results:
        log("❌ No COT data for any tracked market")
        return None
    
    # Compute net NQ bias
    nq_result = results.get("NQ", {})
    es_result = results.get("ES", {})
    
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "CFTC COT — Commitment of Traders",
        "data_source": "tff-2026.csv",
        "markets": results,
        "nq_bias": nq_result.get("direction", "neutral"),
        "es_bias": es_result.get("direction", "neutral"),
        "summary": {
            "nq": f"Dealer z={nq_result.get('dealer',{}).get('z_score','N/A')}, Smart Money z={nq_result.get('lev_money',{}).get('z_score','N/A')}" if nq_result else "No data",
            "es": f"Dealer z={es_result.get('dealer',{}).get('z_score','N/A')}, Smart Money z={es_result.get('lev_money',{}).get('z_score','N/A')}" if es_result else "No data",
        },
        "source": "cot-cftc-government-filing",
    }
    
    with open(STATE_FILE, "w") as f:
        json.dump(output, f, indent=2)
    
    log(f"\n✅ Written to {STATE_FILE}")
    for sym in results:
        r = results[sym]
        log(f"  {sym}: {r['direction']} (Dealer z={r['dealer']['z_score']:+.1f})")
    
    return output

if __name__ == "__main__":
    run()
