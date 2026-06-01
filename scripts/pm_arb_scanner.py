#!/usr/bin/env python3
"""QUARANTINED legacy prediction-market placeholder.

This file used to present itself as a Polymarket/Kalshi arb scanner, but it only
fetched CoinGecko BTC/ETH prices and wrote a placeholder max_edge_pct=0.0. Keep
it non-executable for trading decisions so Hermes cron cannot turn a stub into a
false green signal. Use the guarded TypeScript prediction cycle instead.
"""
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
try:
    import requests
except ImportError:
    requests = None

ROOT = Path(os.path.expanduser("~/.rumbling-hedge"))
STATE_DIR = ROOT / "state"

def scan_crypto_prices():
    """Scan crypto prices for prediction market arb signals."""
    opportunities = []
    try:
        if requests:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd", timeout=10)
            if r.status_code == 200:
                data = r.json()
                opportunities.append({
                    "source": "coingecko",
                    "btc_usd": data.get("bitcoin", {}).get("usd", 0),
                    "eth_usd": data.get("ethereum", {}).get("usd", 0),
                })
    except Exception:
        pass
    return opportunities

def main():
    ts = datetime.now(timezone.utc).isoformat()
    output = {
        "ts": ts,
        "status": "quarantined",
        "researchOnly": True,
        "promotedForExecution": False,
        "arb_opportunities": [],
        "total_found": 0,
        "max_edge_pct": 0.0,
        "warnings": [
            "Legacy placeholder; not a real Polymarket/Kalshi arbitrage scanner.",
            "Use npm run bill:prediction-review, bill:prediction-evidence-triage, and bill:prediction-no-edge-ledger.",
        ],
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_DIR / "pm-arb-scanner.latest.json", "w") as f:
        json.dump(output, f, indent=2)
    print("  PM Arb Scanner: quarantined legacy placeholder; 0 executable opportunities")
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
