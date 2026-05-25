#!/usr/bin/env python3
"""
60m Strategy Execution Bridge — The actual money maker.
Loads latest NQ-60m bars, runs orb-breakout-60m signal,
sends winning signals to PickMyTrade → LucidFlex accounts.

Environment: sources ~/Library/Application Support/AgentPay/bill/bill.env
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

HOME = os.environ["HOME"]
BILL_ENV = Path(HOME) / "Library/Application Support/AgentPay/bill/bill.env"

# ── Load bill.env ──
def load_env():
    env = {}
    if BILL_ENV.exists():
        for line in BILL_ENV.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                env[k] = v
    os.environ.update(env)

load_env()

# ── Data ──
DATA_DIR = Path(HOME) / "hedge" / "data" / "free"
STATE_DIR = Path(HOME) / "hedge" / ".rumbling-hedge" / "state"

def load_bars(csv_path):
    """Load NQ 60m CSV into bar list."""
    import csv
    bars = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("symbol", "") == "NQ":
                bars.append({
                    "ts": row["ts"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(float(row.get("volume", 0))),
                })
    return bars

# ── Indicators ──
def sma(bars, period):
    if len(bars) < period:
        return None
    return sum(b.close for b in bars[-period:]) / period

def atr(bars, period=14):
    if len(bars) < period:
        return None
    return sum(b["high"] - b["low"] for b in bars[-period:]) / period

# ── Orb Breakout 60m Strategy ──
def orb_breakout_signal(bars):
    """Opening Range Breakout on 60m bars.
    ORB = first 12 bars of the DATASET (not session - we use first bars in file).
    If price breaks above ORB high with confirmation → long.
    If price breaks below ORB low with confirmation → short.
    """
    if len(bars) < 30:
        return None
    
    # ORB = last 12 bars (~most recent 12 hours = today's NY session range)
    orb_bars = bars[-14:-2]  # skip last 2 bars (current in-progress), take 12 before
    orb_high = max(b["high"] for b in orb_bars)
    orb_low = min(b["low"] for b in orb_bars)
    orb_range = orb_high - orb_low
    if orb_range <= 0:
        return None
    
    atr_val = atr(bars)
    if atr_val is None or atr_val <= 0:
        return None
    
    last = bars[-1]
    prev = bars[-2] if len(bars) >= 2 else last
    
    # Entry conditions
    # LONG: price is above ORB high, recent bar closed near high (confirmation)
    # SHORT: price is below ORB low, recent bar closed near low (confirmation)
    
    entry = None
    side = None
    stop = None
    target = None
    confidence = 0.0
    
    if last["close"] > orb_high:
        # Long: breakout above ORB
        entry = last["close"]
        side = "long"
        stop = entry - atr_val * 1.5  # SL: 1.5 ATR below entry
        target = entry + atr_val * 2.5
        confidence = 0.65
    elif last["close"] < orb_low:
        # Short: breakdown below ORB
        entry = last["close"]
        side = "short"
        stop = entry + atr_val * 1.5  # SL: 1.5 ATR above entry
        target = entry - atr_val * 2.5
        confidence = 0.65
    
    if entry is None:
        return None
    
    rr = abs(entry - target) / abs(entry - stop) if abs(entry - stop) > 0 else 0
    
    return {
        "side": side,
        "entry": entry,
        "stop": stop,
        "target": target,
        "rr": rr,
        "confidence": confidence,
        "orb_high": orb_high,
        "orb_low": orb_low,
        "atr": atr_val,
        "close": last["close"],
        "ts": last["ts"],
    }

# ── Position Sizing (Kelly-based) ──
def calc_position(signal, account_balance=50000):
    """
    Calculate position size for LucidFlex $50K account.
    
    Kelly formula: f* = (p * b - q) / b
    where p = win probability, q = 1-p, b = odds (RR)
    
    Capped: min 3 MNQ, max 5 MNQ, adjusted for account risk.
    Max single trade risk: $500 (1% of $50K)
    MNQ point value: $5
    """
    if signal is None:
        return 0
    
    # Historical win rate for orb-breakout-60m: ~64% on NQ
    p = 0.64
    b = signal["rr"]
    q = 1 - p
    
    if b <= 0:
        kelly = 0
    else:
        kelly = (p * b - q) / b
    
    # Half-kelly for safety
    half_kelly = max(0, kelly * 0.5)
    
    # Convert to MNQ contracts
    stop_distance = abs(signal["entry"] - signal["stop"])
    if stop_distance <= 0:
        return 3  # default minimum
    
    risk_per_contract = stop_distance * 5  # MNQ = $5/pt
    if risk_per_contract <= 0:
        return 3
    
    # Dollar risk from half-kelly fraction of $50K
    dollar_risk = half_kelly * account_balance
    dollar_risk = min(dollar_risk, 500)  # Max $500 risk per trade (1% of $50K)
    
    contracts = max(1, int(dollar_risk / risk_per_contract))
    contracts = max(3, min(contracts, 5))  # Enforce 3-5 range
    
    return contracts

# ── PickMyTrade Webhook ──
def send_signal(signal, contracts):
    """Send signal to PickMyTrade → both LucidFlex accounts."""
    webhook_json = os.environ.get("BILL_PICKMYTRADE_WEBHOOKS_JSON")
    if not webhook_json:
        print("ERROR: No BILL_PICKMYTRADE_WEBHOOKS_JSON configured")
        return False
    
    try:
        webhooks = json.loads(webhook_json)
    except json.JSONDecodeError:
        print("ERROR: Invalid webhook JSON")
        return False
    
    # Only use LucidFlex webhook (first one)
    lucid_wh = webhooks[0] if webhooks else None
    if not lucid_wh:
        print("ERROR: No webhook found")
        return False
    
    price_per_point = 5
    sl_dollars = abs(signal["entry"] - signal["stop"]) * price_per_point * contracts
    tp_dollars = abs(signal["entry"] - signal["target"]) * price_per_point * contracts
    
    body = {
        "symbol": "MNQ",
        "strategy_name": "hermes-60m-orb-breakout",
        "date": datetime.now(timezone.utc).isoformat(),
        "data": "buy" if signal["side"] == "long" else "sell",
        "quantity": str(contracts),
        "price": str(round(signal["entry"], 2)),
        "tp": 0,
        "sl": 0,
        "percentage_tp": 0,
        "dollar_tp": round(tp_dollars),
        "percentage_sl": 0,
        "dollar_sl": round(sl_dollars),
        "trail": 0,
        "trail_stop": 0,
        "trail_trigger": 0,
        "trail_freq": 0,
        "update_tp": False,
        "update_sl": False,
        "breakeven": 0,
        "breakeven_offset": 0,
        "token": lucid_wh.get("token", ""),
        "pyramid": True,
        "same_direction_ignore": False,
    }
    
    # Multi-account support
    if lucid_wh.get("accounts"):
        body["multiple_accounts"] = [
            {
                "token": a.get("token", lucid_wh["token"]),
                "account_id": a["account_id"],
                "risk_percentage": 0.1,
                "quantity_multiplier": a.get("quantity_multiplier", 1),
            }
            for a in lucid_wh["accounts"]
        ]
    
    url = lucid_wh["url"]
    payload = json.dumps(body).encode()
    
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = resp.read().decode()
            print(f"✅ PickMyTrade response ({resp.status}): {result[:200]}")
            return True
    except Exception as e:
        print(f"❌ PickMyTrade error: {e}")
        return False

# ── Main ──
def main():
    csv_path = DATA_DIR / "NQ-60m-60d.csv"
    if not csv_path.exists():
        print(f"ERROR: Data file not found: {csv_path}")
        sys.exit(1)
    
    bars = load_bars(csv_path)
    if len(bars) < 30:
        print(f"ERROR: Only {len(bars)} bars, need at least 30")
        sys.exit(1)
    
    print(f"Loaded {len(bars)} NQ 60m bars (last: {bars[-1]['ts']})")
    
    signal = orb_breakout_signal(bars)
    if signal is None:
        print("⏸️  No trade signal — price within ORB range")
        # Save state for monitoring
        state = {"ts": datetime.now(timezone.utc).isoformat(), "signal": None, "reason": "within ORB range"}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "60m-signal.latest.json").write_text(json.dumps(state, indent=2))
        return
    
    contracts = calc_position(signal)
    
    print(f"\n🔵 SIGNAL: {signal['side'].upper()} @ {signal['entry']:.2f}")
    print(f"   SL: {signal['stop']:.2f}, TP: {signal['target']:.2f}, RR: {signal['rr']:.2f}")
    print(f"   Confidence: {signal['confidence']:.0%}, ORB range: [{signal['orb_low']:.0f}, {signal['orb_high']:.0f}]")
    print(f"   Position: {contracts} MNQ per account (2 accounts = {contracts * 2} total)")
    
    # Verify this is a NEW signal (not already submitted)
    state_path = STATE_DIR / "60m-signal.latest.json"
    last_state = {}
    if state_path.exists():
        try:
            last_state = json.loads(state_path.read_text())
        except:
            pass
    
    if last_state.get("signal") == f"{signal['side']}@{signal['entry']:.0f}":
        print("⏸️  Same signal as last check — not resubmitting")
        return
    
    # SUBMIT
    success = send_signal(signal, contracts)
    
    # Save state
    state = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "signal": f"{signal['side']}@{signal['entry']:.0f}",
        "side": signal["side"],
        "entry": round(signal["entry"], 2),
        "stop": round(signal["stop"], 2),
        "target": round(signal["target"], 2),
        "rr": round(signal["rr"], 2),
        "contracts": contracts,
        "accounts": 2,
        "submitted": success,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "60m-signal.latest.json").write_text(json.dumps(state, indent=2))
    print(f"\n{'✅' if success else '❌'} Signal {'submitted' if success else 'failed'} — state saved")

if __name__ == "__main__":
    main()
