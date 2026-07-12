#!/usr/bin/env python3
"""
Whale Flow Signal Generator — Institutional Money Flow Overlay

Treats large-position moves as information signals: when whales buy/sell
in size, they may have information the market hasn't priced.

Data sources:
  1. Options unusual activity (NQ/SPX — volume/OI > 3×)
  2. Insider trades (SEC Form 4 — executives buying own stock)
  3. Institutional holdings changes (13F — hedge fund position changes)
  4. CME COT data (futures — commercial vs speculative positioning)

Output: ~/hedge/.rumbling-hedge/state/whale-flow-signal.latest.json
Research/shadow only until real COT/options/block-trade data is wired.
"""

import csv
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

# ── Config ──────────────────────────────────────────────────────────────
STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", os.path.expanduser("~/hedge/.rumbling-hedge/state")))
STATE_FILE = STATE_DIR / "whale-flow-signal.latest.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Symbols to scan for options unusual activity
SCAN_SYMBOLS = ["SPY", "QQQ", "SPX", "NDX", "IWM"]
CFTC_TFF_URL = "https://www.cftc.gov/dea/newcot/FinFutWk.txt"
COT_MARKETS = {
    "NQ": ["NASDAQ-100 Consolidated", "NASDAQ MINI", "MICRO E-MINI NASDAQ-100 INDEX"],
    "ES": ["S&P 500 Consolidated", "E-MINI S&P 500", "MICRO E-MINI S&P 500 INDEX"],
}

TFF_COLUMNS = {
    "open_interest": 7,
    "dealer_long": 8,
    "dealer_short": 9,
    "asset_mgr_long": 11,
    "asset_mgr_short": 12,
    "lev_long": 14,
    "lev_short": 15,
    "nonrep_long": 22,
    "nonrep_short": 23,
    "change_open_interest": 24,
    "change_dealer_long": 25,
    "change_dealer_short": 26,
    "change_asset_mgr_long": 28,
    "change_asset_mgr_short": 29,
    "change_lev_long": 31,
    "change_lev_short": 32,
    "change_nonrep_long": 39,
    "change_nonrep_short": 40,
}

# ── Helper ──────────────────────────────────────────────────────────────

def run_tool(tool_name: str, args: dict) -> dict:
    """Call a Hermes MCP tool via subprocess JSON-RPC pattern.
    Falls back gracefully on failure — this script is informational, not critical.
    """
    # Try using the hermes_tools pattern from execute_code
    try:
        # Build a mini-script that calls the tool
        import_cmd = f"from hermes_tools import {tool_name}"
        exec(import_cmd)
    except ImportError:
        pass
    return {"error": f"Cannot call {tool_name} directly — using fallback"}


def fetch_options_unusual() -> dict:
    """Collect options unusual activity across scan symbols."""
    results = {"calls": [], "puts": [], "symbols_scanned": SCAN_SYMBOLS}
    
    for symbol in SCAN_SYMBOLS:
        # We'll use a REST call pattern — can't import hermes_tools directly in script
        # so we use the available MCP tools indirectly
        try:
            result = subprocess.run(
                ["curl", "-s",
                 f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d",
                 "-H", "User-Agent: Mozilla/5.0"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                results[f"{symbol}_price_data"] = "fetched"
        except:
            pass
    
    return results


def calculate_whale_composite(options_signal: float, insider_signal: float,
                               institutional_signal: float = 0.0) -> dict:
    """Combine multiple whale flow signals into a composite.
    
    Returns:
        direction: "bullish" | "bearish" | "neutral"
        confidence: 0.0-1.0
        components: breakdown of individual signals
    """
    signals = [
        ("options_unusual", options_signal, 0.5),   # 50% weight
        ("insider_trades", insider_signal, 0.3),      # 30% weight
        ("institutional_13f", institutional_signal, 0.2),  # 20% weight
    ]
    
    composite = sum(s * w for _, s, w in signals) / sum(w for _, _, w in signals)
    
    if composite > 0.3:
        direction = "bullish"
        confidence = min(abs(composite), 1.0)
    elif composite < -0.3:
        direction = "bearish"
        confidence = min(abs(composite), 1.0)
    else:
        direction = "neutral"
        confidence = 0.0
    
    return {
        "direction": direction,
        "confidence": round(confidence, 3),
        "composite_score": round(composite, 3),
        "components": {name: {"score": round(s, 3), "weight": w}
                       for name, s, w in signals},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def as_number(row: list[str], key: str) -> float:
    idx = TFF_COLUMNS[key]
    try:
        return float(str(row[idx]).strip().replace(",", ""))
    except Exception:
        return 0.0


def cot_record_score(row: list[str]) -> dict:
    open_interest = max(as_number(row, "open_interest"), 1.0)
    asset_net = as_number(row, "asset_mgr_long") - as_number(row, "asset_mgr_short")
    lev_net = as_number(row, "lev_long") - as_number(row, "lev_short")
    dealer_net = as_number(row, "dealer_long") - as_number(row, "dealer_short")
    nonrep_net = as_number(row, "nonrep_long") - as_number(row, "nonrep_short")

    asset_net_change = as_number(row, "change_asset_mgr_long") - as_number(row, "change_asset_mgr_short")
    lev_net_change = as_number(row, "change_lev_long") - as_number(row, "change_lev_short")
    dealer_net_change = as_number(row, "change_dealer_long") - as_number(row, "change_dealer_short")

    # Slow weekly context: asset managers are treated as structural flow,
    # leveraged funds as faster risk appetite, and dealers as contra-flow.
    flow_raw = (0.55 * asset_net_change + 0.35 * lev_net_change - 0.10 * dealer_net_change) / open_interest
    positioning_raw = (0.55 * asset_net + 0.35 * lev_net - 0.10 * dealer_net) / open_interest
    score = max(-1.0, min(1.0, flow_raw * 20.0 + positioning_raw * 0.75))

    return {
        "market": row[0].strip(),
        "reportDate": row[2].strip(),
        "openInterest": int(open_interest),
        "assetManagerNet": int(asset_net),
        "leveragedFundsNet": int(lev_net),
        "dealerNet": int(dealer_net),
        "nonReportableNet": int(nonrep_net),
        "assetManagerNetChange": int(asset_net_change),
        "leveragedFundsNetChange": int(lev_net_change),
        "dealerNetChange": int(dealer_net_change),
        "weeklyFlowScore": round(score, 4),
    }


def fetch_cftc_tff_cot() -> dict:
    """Fetch and score current CFTC Traders in Financial Futures report.

    This is weekly positioning context only. It is slow, delayed, and not an
    execution signal.
    """
    # Use curl via subprocess to avoid macOS LibreSSL CA cert issues
    try:
        import subprocess
        result = subprocess.run(
            ["curl", "-s", "--max-time", "20", CFTC_TFF_URL],
            capture_output=True, text=True, timeout=25
        )
        if result.returncode == 0 and result.stdout:
            raw = result.stdout
        else:
            raise RuntimeError(f"curl failed: {result.stderr[:100]}")
    except Exception as curl_err:
        # Fallback: try with ssl_context that uses certifi
        try:
            import certifi, ssl
            ctx = ssl.create_default_context(cafile=certifi.where())
            raw = urlopen(CFTC_TFF_URL, timeout=20, context=ctx).read().decode("utf-8", "replace")
        except Exception:
            raise RuntimeError(f"CFTC fetch failed (curl + ssl fallback): {curl_err}")
    return build_cftc_tff_signal(raw, CFTC_TFF_URL)


def build_cftc_tff_signal(raw: str, source: str = CFTC_TFF_URL) -> dict:
    """Parse and score CFTC TFF text into a shadow-only whale-flow signal."""
    rows = list(csv.reader(io.StringIO(raw.replace('" "', '"\n"'))))
    markets = {}
    for symbol, wanted_names in COT_MARKETS.items():
        match = None
        for wanted in wanted_names:
            match = next((row for row in rows if row and row[0].strip().upper().startswith(wanted.upper())), None)
            if match:
                break
        if match:
            markets[symbol] = cot_record_score(match)
    if not markets:
        raise RuntimeError("No NQ/ES TFF rows found in CFTC report")
    score = sum(item["weeklyFlowScore"] for item in markets.values()) / len(markets)
    if score > 0.15:
        direction = "bullish"
        confidence = min(abs(score), 0.5)
    elif score < -0.15:
        direction = "bearish"
        confidence = min(abs(score), 0.5)
    else:
        direction = "neutral"
        confidence = 0.0
    return {
        "direction": direction,
        "confidence": round(confidence, 3),
        "composite_score": round(score, 4),
        "components": {
            "cftc_tff_cot": {
                "score": round(score, 4),
                "weight": 1.0,
                "status": "ok",
                "source": source,
                "markets": markets,
            },
            "options_unusual": {"score": 0.0, "weight": 0.0, "status": "not_connected"},
            "insider_trades": {"score": 0.0, "weight": 0.0, "status": "not_connected"},
            "institutional_13f": {"score": 0.0, "weight": 0.0, "status": "not_connected"},
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "cftc_tff_cot_weekly",
        "evidence_level": "weekly_cot_shadow_only",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "execution_role": "diagnostic_only",
        "operator_read": (
            "Research-only weekly COT context. This is delayed positioning data, "
            "not live money-flow confirmation or execution authority."
        ),
        "limitations": [
            "CFTC TFF COT is weekly Tuesday positioning, usually released Friday, not real-time flow",
            "COT context may inform research/regime review but must not size or confirm Topstep orders",
            "Options unusual activity, insider, 13F, and CME block-trade data are still not connected",
        ],
    }


def compute_fallback_signal() -> dict:
    """Compute a reasonable signal using available data.
    
    When direct API calls aren't available, use price action + volume
    extremes as a proxy for institutional interest.
    """
    # Default: neutral — no data means no signal
    return {
        "direction": "neutral",
        "confidence": 0.0,
        "composite_score": 0.0,
        "components": {
            "options_unusual": {"score": 0.0, "weight": 0.5, "status": "no_data"},
            "insider_trades": {"score": 0.0, "weight": 0.3, "status": "no_data"},
            "institutional_13f": {"score": 0.0, "weight": 0.2, "status": "no_data"},
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "fallback_no_data",
        "evidence_level": "no_live_data_shadow_only",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "execution_role": "diagnostic_only",
        "operator_read": (
            "No live flow data is connected. This neutral fallback is a blocker/diagnostic, "
            "not confirmation."
        ),
        "limitations": [
            "No live unusual-options, insider, 13F, COT, or CME block-trade data is currently connected",
            "Neutral fallback must not be interpreted as confirmation"
        ],
    }


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("🐋 Whale Flow Signal Generator — running...")
    
    # Try to fetch options unusual activity
    options_data = fetch_options_unusual()
    
    try:
        signal = fetch_cftc_tff_cot()
    except Exception as exc:
        signal = compute_fallback_signal()
        signal["error"] = str(exc)
    
    # Save state
    with open(STATE_FILE, "w") as f:
        json.dump(signal, f, indent=2)
    
    print(f"✅ Signal written to {STATE_FILE}")
    print(f"   Direction: {signal['direction']}")
    print(f"   Confidence: {signal['confidence']}")
    print(f"   Method: {signal.get('method', 'live')}")
    print(f"   Operator read: {signal.get('operator_read', 'research-only diagnostic')}")
    print()
    print("── Integration Note ──")
    print("This script runs standalone via cron and is shadow/research only.")
    print("  Current:           CFTC TFF weekly COT context when available")
    print("  Fallback:          neutral no-data artifact, never confirmation")
    print("  Next research:     add CME block-trade/options flow evidence")
    print("  Execution rule:    ignored by bridges unless promoted_for_execution=true")
    print()
    print("NOT A TRADE SIGNAL: writesOrders=false, promoted_for_execution=false")
    print("Role: research/shadow diagnostic only")
    print("Execution rule: ignored unless promoted_for_execution=true after real data is wired")


if __name__ == "__main__":
    main()
