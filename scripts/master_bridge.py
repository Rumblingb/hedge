#!/usr/bin/env python3
"""
Master Strategy Execution Bridge — 60m + 15m Edges
Runs all proven edge strategies on NQ, selects best signal,
applies trailing SL/TP, sends to PickMyTrade → both LucidFlex accounts.

Strategies (6 proven edges):
  60m: orb-breakout (68%), wq-trend-mom (61.5%), wq-vol-regime (57.1%), wq-alpha-001 (58.2%)
  15m: orb-breakout (55.1%), wq-alpha-012 (53.1%)
"""

import json, os, sys, csv
import urllib.request
from datetime import datetime, timezone, date
from pathlib import Path
from math import floor

HOME = os.environ["HOME"]

# ── Import macro context engine ──
sys.path.insert(0, str(Path(__file__).parent))
import macro_context as mc
from new_arsenal_gate import new_arsenal_gate

    # ── Confluence signal readers ──
def read_rolling_window_params():
    """Read rolling window optimizer output for adaptive lookback."""
    try:
        p = Path(os.environ["HOME"]) / ".rumbling-hedge/state/rolling-window-params.latest.json"
        if p.exists():
            with open(p) as f:
                d = json.load(f)
            return d.get("parameters", {}), d.get("regime", "unknown")
    except:
        pass
    return {}, "unknown"

def read_dom_proxy_signal():
    """Read DOM proxy OHLCV signal for pre-trade confirmation."""
    try:
        p = Path(os.environ["HOME"]) / ".rumbling-hedge/state/dom-proxy-signal.latest.json"
        if p.exists():
            with open(p) as f:
                d = json.load(f)
            return d.get("direction", "neutral"), d.get("confidence", 0.0)
    except:
        pass
    return "neutral", 0.0

def read_kalman_pairs_signal():
    """Read Kalman filter NQ/ES pairs signal."""
    try:
        p = Path(os.environ["HOME"]) / ".rumbling-hedge/state/kalman-pairs-signal.latest.json"
        if p.exists():
            with open(p) as f:
                d = json.load(f)
            return d.get("action", "HOLD"), d.get("direction", "neutral"), d.get("stats", {})
    except:
        pass
    return "HOLD", "neutral", {}

def read_whale_flow_signal():
    """Read whale flow overlay signal."""
    try:
        p = Path(os.environ["HOME"]) / ".rumbling-hedge/state/whale-flow-signal.latest.json"
        if p.exists():
            with open(p) as f:
                d = json.load(f)
            return d.get("direction", "neutral"), d.get("confidence", 0.0)
    except:
        pass
    return "neutral", 0.0

# ── FOMC Calendar 2026 (known scheduled dates) ──
FOMC_DATES = {
    date(2026, 1, 28), date(2026, 1, 29),
    date(2026, 3, 17), date(2026, 3, 18),
    date(2026, 5, 6), date(2026, 5, 7),
    date(2026, 5, 19),  # <-- today
    date(2026, 6, 16), date(2026, 6, 17),
    date(2026, 7, 28), date(2026, 7, 29),
    date(2026, 9, 15), date(2026, 9, 16),
    date(2026, 11, 3), date(2026, 11, 4),
    date(2026, 12, 15), date(2026, 12, 16),
}

def is_fomc_day():
    return date.today() in FOMC_DATES
BILL_ENV = Path(HOME) / "Library/Application Support/AgentPay/bill/bill.env"
DATA_DIR = Path(HOME) / "hedge" / "data" / "free"
STATE_DIR = Path(HOME) / "hedge" / ".rumbling-hedge" / "state"

# ── Load credentials ──
def load_env():
    env = {}
    if BILL_ENV.exists():
        for line in BILL_ENV.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    os.environ.update(env)

load_env()

# ── Bar loader ──
def load_bars(csv_path, symbol="NQ"):
    bars = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("symbol", "") == symbol:
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
    return sum(b["close"] for b in bars[-period:]) / period

def atr(bars, period=14):
    if len(bars) < period:
        return None
    return sum(b["high"] - b["low"] for b in bars[-period:]) / period

def rsi(bars, period=14):
    if len(bars) < period + 1:
        return 50
    gains = losses = 0
    for i in range(-period, 0):
        change = bars[i]["close"] - bars[i-1]["close"]
        if change > 0:
            gains += change
        else:
            losses -= change
    if losses == 0:
        return 100
    rs = gains / losses
    return 100 - (100 / (1 + rs))

# ── Strategy: Orb Breakout (60m & 15m versions) ──
def orb_breakout(bars, orb_window=12, atr_period=14):
    """Opening Range Breakout. Uses last orb_window bars as ORB."""
    if len(bars) < max(orb_window + 2, atr_period + 2):
        return None
    orb_bars = bars[-(orb_window + 2):-2]  # skip last 2 (in-progress)
    if len(orb_bars) < orb_window:
        orb_bars = bars[-orb_window:]
    orb_high = max(b["high"] for b in orb_bars)
    orb_low = min(b["low"] for b in orb_bars)
    orb_range = orb_high - orb_low
    if orb_range <= 0:
        return None
    a = atr(bars, atr_period)
    if a is None or a <= 0:
        return None
    last = bars[-1]
    entry = stop = target = None
    side = None
    if last["close"] > orb_high:
        entry = last["close"]
        side = "long"
        stop = entry - a * 1.5
        target = entry + a * 2.5
    elif last["close"] < orb_low:
        entry = last["close"]
        side = "short"
        stop = entry + a * 1.5
        target = entry - a * 2.5
    if entry is None:
        return None
    rr = abs(entry - target) / abs(entry - stop) if abs(entry - stop) > 0 else 0
    return {"side": side, "entry": entry, "stop": stop, "target": target, "rr": rr,
            "confidence": 0.65, "atr": a, "close": last["close"], "ts": last["ts"],
            "strategy": "orb-breakout"}

# ── Strategy: WQ Trend Momentum ──
def wq_trend_momentum(bars):
    """SMA(5) vs SMA(20) crossover with volume confirmation."""
    if len(bars) < 25:
        return None
    a = atr(bars)
    if a is None or a <= 0:
        return None
    s5 = sma(bars, 5)
    s20 = sma(bars, 20)
    if s5 is None or s20 is None:
        return None
    p5 = sma(bars[:-1], 5) if len(bars) > 25 else s5
    p20 = sma(bars[:-1], 20) if len(bars) > 25 else s20
    if p5 is None or p20 is None:
        return None
    last = bars[-1]
    crossed_up = s5 > s20 and p5 <= p20
    crossed_down = s5 < s20 and p5 >= p20
    # Volume confirmation
    avg_vol = sum(b["volume"] for b in bars[-10:]) / 10 if len(bars) >= 10 else 1
    vol_ok = last["volume"] > avg_vol * 1.2 if avg_vol > 0 else True
    if crossed_up and vol_ok:
        entry = last["close"]
        return {"side": "long", "entry": entry, "stop": entry - a * 1.5,
                "target": entry + a * 2.5, "rr": 2.5/1.5, "confidence": 0.58,
                "atr": a, "close": entry, "ts": last["ts"], "strategy": "wq-trend-mom"}
    if crossed_down and vol_ok:
        entry = last["close"]
        return {"side": "short", "entry": entry, "stop": entry + a * 1.5,
                "target": entry - a * 2.5, "rr": 2.5/1.5, "confidence": 0.58,
                "atr": a, "close": entry, "ts": last["ts"], "strategy": "wq-trend-mom"}
    return None

# ── Strategy: WQ Volatility Regime ──
def wq_vol_regime(bars):
    """Short-term ATR vs long-term ATR ratio — trade volatility expansion."""
    if len(bars) < 35:
        return None
    short_vol = sum(b["high"] - b["low"] for b in bars[-10:]) / 10
    long_vol = sum(b["high"] - b["low"] for b in bars[-30:]) / 30
    if long_vol <= 0:
        return None
    vr = short_vol / long_vol
    a = atr(bars)
    if a is None or a <= 0:
        return None
    last = bars[-1]
    s50 = sma(bars, 20) or last["close"]
    if vr > 1.5:
        # Volatility expansion — fade direction that didn't work
        if last["close"] > s50:
            entry = last["close"]
            return {"side": "short", "entry": entry, "stop": entry + a * 1.5,
                    "target": entry - a * 2.0, "rr": 2.0/1.5, "confidence": 0.52,
                    "atr": a, "close": entry, "ts": last["ts"], "strategy": "wq-vol-regime"}
    elif vr < 0.7:
        if last["close"] < s50:
            entry = last["close"]
            return {"side": "long", "entry": entry, "stop": entry - a * 1.5,
                    "target": entry + a * 2.0, "rr": 2.0/1.5, "confidence": 0.52,
                    "atr": a, "close": entry, "ts": last["ts"], "strategy": "wq-vol-regime"}
    return None

# ── Strategy: WQ Alpha 001 (3-bar momentum) ──
def wq_alpha_001(bars):
    if len(bars) < 25:
        return None
    a = atr(bars)
    if a is None or a <= 0:
        return None
    last = bars[-1]
    roc = (last["close"] - bars[-4]["close"]) / bars[-4]["close"] if bars[-4]["close"] > 0 else 0
    avg_vol = sum(b["volume"] for b in bars[-10:]) / 10 if len(bars) >= 10 else 1
    vol_ok = last["volume"] > avg_vol * 1.2 if avg_vol > 0 else True
    if roc > 0.002 and vol_ok:
        return {"side": "long", "entry": last["close"], "stop": last["close"] - a * 1.2,
                "target": last["close"] + a * 2.0, "rr": 2.0/1.2, "confidence": 0.55,
                "atr": a, "close": last["close"], "ts": last["ts"], "strategy": "wq-alpha-001"}
    if roc < -0.002 and vol_ok:
        return {"side": "short", "entry": last["close"], "stop": last["close"] + a * 1.2,
                "target": last["close"] - a * 2.0, "rr": 2.0/1.2, "confidence": 0.55,
                "atr": a, "close": last["close"], "ts": last["ts"], "strategy": "wq-alpha-001"}
    return None

# ── Strategy: WQ Alpha 012 (vol-regime compression breakout) ──
def wq_alpha_012(bars):
    if len(bars) < 125:
        return None
    recent_vol = sum(b["high"] - b["low"] for b in bars[-20:]) / 20
    hist_vol = sum(b["high"] - b["low"] for b in bars[-120:-20]) / 100
    if hist_vol <= 0:
        return None
    vr = recent_vol / hist_vol
    a = atr(bars)
    if a is None or a <= 0:
        return None
    last = bars[-1]
    avg_vol = sum(b["volume"] for b in bars[-10:]) / 10 if len(bars) >= 10 else 1
    vol_ok = last["volume"] > avg_vol * 1.5 if avg_vol > 0 else True
    if vr < 0.6 and vol_ok:
        s20 = sma(bars, 20) or last["close"]
        side = "long" if last["close"] > s20 else "short"
        entry = last["close"]
        stop = entry - a * 1.5 if side == "long" else entry + a * 1.5
        target = entry + a * 3.0 if side == "long" else entry - a * 3.0
        return {"side": side, "entry": entry, "stop": stop, "target": target,
                "rr": 3.0/1.5, "confidence": 0.53, "atr": a, "close": last["close"],
                "ts": last["ts"], "strategy": "wq-alpha-012"}
    return None

# ── Signal Selection ──
def pick_best(signals):
    """Pick the highest-confidence signal. Tie-break by RR."""
    valid = [s for s in signals if s is not None]
    if not valid:
        return None
    valid.sort(key=lambda s: (s["confidence"], s["rr"]), reverse=True)
    return valid[0]

# ── Position Sizing (Kelly) ──
def calc_position(signal, account_balance=50000):
    if signal is None:
        return 3
    p = 0.64 if "orb" in signal["strategy"] else 0.55
    b = signal["rr"]
    q = 1 - p
    kelly = max(0, (p * b - q) / b) if b > 0 else 0
    half_kelly = kelly * 0.5
    stop_dist = abs(signal["entry"] - signal["stop"])
    if stop_dist <= 0:
        return 3
    risk_per_contract = stop_dist * 5
    if risk_per_contract <= 0:
        return 3
    dollar_risk = min(half_kelly * account_balance, 500)
    contracts = max(1, int(dollar_risk / risk_per_contract))
    return max(3, min(contracts, 5))

# ── PickMyTrade ──
def send_signal(signal, contracts):
    webhook_json = os.environ.get("BILL_PICKMYTRADE_WEBHOOKS_JSON")
    if not webhook_json:
        print("ERROR: No BILL_PICKMYTRADE_WEBHOOKS_JSON")
        return False
    try:
        webhooks = json.loads(webhook_json)
    except:
        print("ERROR: Invalid webhook JSON")
        return False
    wh = webhooks[0] if webhooks else None
    if not wh:
        return False
    pp = 5
    sl_d = abs(signal["entry"] - signal["stop"]) * pp * contracts
    tp_d = abs(signal["entry"] - signal["target"]) * pp * contracts
    # Trailing stop config: trail 0.5 ATR from best price after profit trigger
    trail_pts = int(signal.get("atr", 30) * 1.0)
    body = {
        "symbol": "MNQ",
        "strategy_name": f"hermes-{signal['strategy']}",
        "date": datetime.now(timezone.utc).isoformat(),
        "data": "buy" if signal["side"] == "long" else "sell",
        "quantity": str(contracts),
        "price": str(round(signal["entry"], 2)),
        "tp": 0, "sl": 0,
        "percentage_tp": 0, "dollar_tp": round(tp_d),
        "percentage_sl": 0, "dollar_sl": round(sl_d),
        "trail": trail_pts,       # <-- TRAILING STOP: trail by this many points
        "trail_stop": trail_pts,
        "trail_trigger": trail_pts, # Activate trailing after price moves this far in our favor
        "trail_freq": 1,            # Update every tick
        "update_tp": True,          # Move TP with trail
        "update_sl": True,          # Move SL with trail
        "breakeven": trail_pts,     # Move to breakeven after this profit
        "breakeven_offset": 1,
        "token": wh.get("token", ""),
        "pyramid": True,
        "same_direction_ignore": False,
    }
    if wh.get("accounts"):
        body["multiple_accounts"] = [
            {"token": a.get("token", wh["token"]), "account_id": a["account_id"],
             "risk_percentage": 0.1, "quantity_multiplier": a.get("quantity_multiplier", 1)}
            for a in wh["accounts"]
        ]
    payload = json.dumps(body).encode()
    req = urllib.request.Request(wh["url"], data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = resp.read().decode()
            print(f"✅ Sent: {resp.status} — {result[:100]}")
            return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# ── Run All ──
def run_strategy(name, csv_name, strategy_fn, min_bars=30):
    path = DATA_DIR / csv_name
    if not path.exists():
        print(f"  SKIP {name}: no data")
        return None
    bars = load_bars(path)
    if len(bars) < min_bars:
        print(f"  SKIP {name}: only {len(bars)} bars (need {min_bars})")
        return None
    sig = strategy_fn(bars)
    print(f"  {'✅' if sig else '⏸️'} {name}: {'signal' if sig else 'no signal'} (last bar: {bars[-1]['ts']})")
    return sig

def main():
    # ⛔ FOMC safety check
    if is_fomc_day():
        print(f"\n{'='*60}")
        print(f"⛔ FOMC DAY — {date.today()} — NO TRADING")
        print(f"Strategies disabled. Market patterns unreliable on FOMC days.")
        print(f"{'='*60}\n")
        state = {"ts": datetime.now(timezone.utc).isoformat(), "signal": None,
                 "reason": "FOMC day — trading blocked"}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "master-signal.latest.json").write_text(json.dumps(state, indent=2))
        return

    print(f"\n{'='*60}")
    print(f"HERMES STRATEGY BRIDGE — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    # Run ALL strategies across ALL instruments
    signals = []

    # ── SESSION DETECTION ──
    now_et = datetime.now(timezone.utc).hour * 60 + datetime.now(timezone.utc).minute - 4 * 60
    now_et = max(0, now_et)  # wrap negative (before 4am UTC)
    if now_et >= 6 * 60 + 30 and now_et < 16 * 60:  # 6:30 AM - 4:00 PM ET
        session = "US"  # Composite: all US sessions
    elif now_et >= 3 * 60 and now_et < 6 * 60 + 30:  # 3 AM - 6:30 AM ET
        session = "LONDON"
    elif now_et >= 16 * 60 or now_et < 3 * 60:  # 4 PM ET - 3 AM ET
        session = "ASIA"
    else:
        session = "OFF"
    print(f"Session: {session}")

    # ── RISK MANAGEMENT ──
    risk_path = STATE_DIR / "risk-state.json"
    risk = {"daily_loss": 0.0, "daily_profit": 0.0, "cumulative_loss": 0.0,
            "cumulative_profit": 0.0, "trade_count": 0, "day": str(date.today()),
            "runway_days": 4, "blocked": False}
    if risk_path.exists():
        try:
            old = json.loads(risk_path.read_text())
            if old.get("day") == str(date.today()):
                risk.update(old)  # carry forward today's stats
            else:
                risk["cumulative_loss"] = old.get("cumulative_loss", 0.0)
                risk["cumulative_profit"] = old.get("cumulative_profit", 0.0)
            # Recalculate runway
            risk["runway_days"] = max(0, int((2000 - risk["cumulative_loss"]) / 500))
            if risk["cumulative_loss"] >= 2000:
                risk["blocked"] = True
        except:
            pass
    print(f"Risk: ${risk['daily_loss']:.0f} loss / ${risk['daily_profit']:.0f} profit today | "
          f"${risk['cumulative_loss']:.0f} / $2000 cumulative loss | "
          f"{risk['runway_days']}d runway | {'⛔ BLOCKED' if risk['blocked'] else '🟢 OK'}")

    if risk["blocked"]:
        print("\n⛔ EMERGENCY STOP — Cumulative loss limit ($2,000) reached. No trades.")
        risk_path.write_text(json.dumps(risk, indent=2))
        return

    # ── PRE-MARKET BRIEF ──
    if session == "ASIA":
        # Check for gaps and key levels (use freshest daily file)
        nq_1d = load_bars(DATA_DIR / "ALL-2MARKETS-NQ-ES-1d-5y-fresh.csv") or load_bars(DATA_DIR / "NQ-1d-1y.csv")
        nq_1h = load_bars(DATA_DIR / "NQ-60m-60d.csv")
        # Filter to NQ only
        if nq_1d:
            nq_1d = [b for b in nq_1d if b.get("symbol", "NQ") == "NQ"]
        prev_day = nq_1d[-2] if nq_1d and len(nq_1d) >= 2 else None
        prev_close_day = nq_1d[-1] if nq_1d else None
        last_bar = nq_1h[-1] if nq_1h else None
        if last_bar and prev_close_day:
            # Get today's session open from the 60m data (today's bar)
            today_open = None
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for b in reversed(nq_1h):
                if b["ts"].startswith(today_str):
                    today_open = b["open"]
                    break
            # Find the most recent daily close (could be same day or yesterday)
            close_price = prev_close_day.get("close", 0)
            if today_open and last_bar:
                gap = last_bar["close"] - close_price if close_price else 0
                day_low = prev_close_day.get("low", 0)
                day_high = prev_close_day.get("high", 0)
            print(f"\n{'─'*50}")
            print(f"🌙 ASIA SESSION PREP")
            print(f"   Prev close: ${prev_day['close']:.0f}")
            print(f"   Current: ${last_bar['close']:.0f}")
            print(f"   Gap: {'+UP' if gap > 0 else '-DOWN'} ${abs(gap):.0f}")
            print(f"   Key levels: H ${prev_day['high']:.0f} | L ${prev_day['low']:.0f}")
            # Check for upcoming news
            events_today = mc.today_events()
            if events_today:
                print(f"   ⚠️ News: {events_today}")
            print(f"{'─'*50}\n")

    # ── NQ STRATEGIES ──
    print("--- NQ 60m Strategies ---")
    signals.append(run_strategy("NQ orb-breakout    (60m)", "NQ-60m-1d.csv", lambda b: orb_breakout(b, 8, 14), min_bars=12))
    signals.append(run_strategy("NQ wq-trend-mom   (60m)", "NQ-60m-60d.csv", wq_trend_momentum))
    signals.append(run_strategy("NQ wq-vol-regime  (60m)", "NQ-60m-60d.csv", wq_vol_regime))

    print("\n--- NQ 30m Strategies ---")
    signals.append(run_strategy("NQ orb-breakout    (30m)", "NQ-30m-5d.csv", lambda b: orb_breakout(b, 12, 13)))

    print("\n--- NQ 15m Strategies ---")
    signals.append(run_strategy("NQ orb-breakout    (15m)", "NQ-15m-5d.csv", lambda b: orb_breakout(b, 12, 14)))
    signals.append(run_strategy("NQ wq-trend-mom   (15m)", "NQ-15m-5d.csv", wq_trend_momentum))
    signals.append(run_strategy("NQ wq-vol-regime  (15m)", "NQ-15m-5d.csv", wq_vol_regime))

    print("\n--- NQ 5m Strategies ---")
    signals.append(run_strategy("NQ orb-breakout    (5m)",  "NQ-5m-60d.csv",  lambda b: orb_breakout(b, 12, 8), min_bars=30))
    signals.append(run_strategy("NQ wq-trend-mom   (5m)",  "NQ-5m-60d.csv",  wq_trend_momentum, min_bars=60))

    # ── ES STRATEGIES (proven at 60m) ──
    print("\n--- ES 60m Strategies ---")
    signals.append(run_strategy("ES orb-breakout    (60m)", "ES-60m-60d.csv", lambda b: orb_breakout(b, 12, 14), min_bars=16))
    signals.append(run_strategy("ES wq-trend-mom   (60m)", "ES-60m-60d.csv", wq_trend_momentum))
    signals.append(run_strategy("ES wq-vol-regime  (60m)", "ES-60m-60d.csv", wq_vol_regime))

    best = pick_best(signals)
    print(f"\n{'='*60}")
    if best is None:
        print("NO TRADE — no strategy has an entry signal right now")
        state = {"ts": datetime.now(timezone.utc).isoformat(), "signal": None,
                 "reason": "no entry conditions met across 9 strategy/timeframe combos"}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "master-signal.latest.json").write_text(json.dumps(state, indent=2))
        return

    # Check for duplicates
    state_path = STATE_DIR / "master-signal.latest.json"
    last_sig = {}
    if state_path.exists():
        try:
            last_sig = json.loads(state_path.read_text())
        except:
            pass
    sig_key = f"{best['side']}@{best['strategy']}"
    if last_sig.get("signal") == sig_key:
        print(f"⏸️ DUPLICATE — {sig_key} already submitted, skipping")
        return
    # 🧠 NEW ARSENAL GATE — reads PEAD, S/R, Donchian, Ichimoku, Insider, COT, DOM, Kalman
    print("\n--- New Arsenal Gate ---")
    ag = new_arsenal_gate(best)
    for r in ag["reasons"]:
        print(f"  • {r}")
    print(f"  Verdict: {ag['verdict']} (size modifier: {ag['confidence_modifier']:.2f}x)")

    if ag["verdict"] == "NO_TRADE":
        print("\n⛔ BLOCKED by arsenal gate")
        state = {"ts": datetime.now(timezone.utc).isoformat(), "signal": None,
                 "reason": f"Arsenal blocked: {ag['reasons']}"}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_DIR.joinpath("master-signal.latest.json").write_text(json.dumps(state, indent=2))
        return

    # 🧠 MACRO CONTEXT GATE — filters trade through every relevant lens
    print("\n--- Macro Context Assessment ---")
    ctx = mc.assess(best)
    for r in ctx["reasons"]:
        print(f"  • {r}")
    print(f"  Verdict: {ctx['verdict']} (size modifier: {ctx['confidence_modifier']:.2f}x)")

    if ctx["verdict"] == "NO_TRADE":
        print("\n⛔ BLOCKED by macro context")
        state = {"ts": datetime.now(timezone.utc).isoformat(), "signal": None,
                 "reason": f"Macro blocked: {ctx['reasons']}"}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_DIR.joinpath("master-signal.latest.json").write_text(json.dumps(state, indent=2))
        return

    contracts = calc_position(best)
    # Apply both modifiers
    contracts = max(3, min(int(contracts * ctx["confidence_modifier"] * ag["confidence_modifier"]), 5))
    print(f"\nBEST SIGNAL: [{best['strategy']}] {best['side'].upper()} @ ${best['entry']:.2f}")
    print(f"  SL: ${best['stop']:.2f}, TP: ${best['target']:.2f}, RR: {best['rr']:.2f}")
    print(f"  ATR: {best['atr']:.2f}, Confidence: {best['confidence']:.0%}")
    print(f"  Position: {contracts} MNQ per account (x2 = {contracts*2} total)")
    print(f"  Trailing: {best.get('atr',30):.0f} pts trail, breakeven at {best.get('atr',30):.0f} pts")

    ok = send_signal(best, contracts)
    state = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "signal": sig_key,
        "strategy": best["strategy"],
        "side": best["side"],
        "entry": round(best["entry"], 2),
        "stop": round(best["stop"], 2),
        "target": round(best["target"], 2),
        "rr": round(best["rr"], 2),
        "contracts": contracts,
        "accounts": 2,
        "submitted": ok,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.joinpath("master-signal.latest.json").write_text(json.dumps(state, indent=2))
    print(f"\n{'✅' if ok else '❌'} {'SUBMITTED' if ok else 'FAILED'}")

if __name__ == "__main__":
    main()
