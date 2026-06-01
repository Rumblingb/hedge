#!/usr/bin/env python3
"""
Master Strategy Execution Bridge — 60m + 15m Edges
Runs all proven edge strategies on NQ, selects best signal,
applies guarded risk checks, and routes only through the Topstep demo bridge.
Topstep demo route capped: deterministic code caps routed size and ignores
unpromoted research overlays.

Legacy PickMyTrade/LucidFlex execution is disabled in this path.

Strategies (6 proven edges):
  60m: orb-breakout (68%), wq-trend-mom (61.5%), wq-vol-regime (57.1%), wq-alpha-001 (58.2%)
  15m: orb-breakout (55.1%), wq-alpha-012 (53.1%)
"""

import json, os, sys, csv
import urllib.request
from datetime import datetime, timezone, date
from pathlib import Path
from math import floor
from zoneinfo import ZoneInfo

HOME = os.environ["HOME"]
CANONICAL_STATE_DIR = Path(HOME) / "hedge" / ".rumbling-hedge" / "state"
LEGACY_STATE_DIR = Path(HOME) / ".rumbling-hedge" / "state"
VAULT_DIR = Path(HOME) / "Documents" / "memorybrain"
TRADING_TIMEZONE = ZoneInfo(os.environ.get("BILL_TRADING_TIMEZONE", "Europe/London"))
NY_TIMEZONE = ZoneInfo(os.environ.get("BILL_NY_TIMEZONE", "America/New_York"))

def read_state_json(name, allow_legacy=False):
    """Read canonical Bill state first; legacy home-level state is shadow-only."""
    paths = [CANONICAL_STATE_DIR / name]
    if allow_legacy:
        paths.append(LEGACY_STATE_DIR / name)
    for path in paths:
        try:
            if path.exists():
                return json.loads(path.read_text()), path
        except Exception:
            pass
    return {}, None

def promoted_execution_overlay(data):
    return data.get("promoted_for_execution") is True and data.get("tradable_signal") is True

def current_trading_date(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(TRADING_TIMEZONE).date()

def ny_minutes(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(NY_TIMEZONE)
    return local.hour * 60 + local.minute

def today_daily_plan_path():
    return VAULT_DIR / "Agent-Hermes" / "daily" / f"{current_trading_date().isoformat()}-bill-trading-plan.md"

def read_text_safe(path):
    try:
        return path.read_text()
    except Exception:
        return ""

def env_true(name):
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}

def positive_int_env(name, default):
    try:
        value = int(os.environ.get(name, str(default)))
        return value if value > 0 else default
    except Exception:
        return default

def machine_control_lines(text):
    """Return standalone control lines only, excluding markdown bullets/prose."""
    return {line.strip() for line in text.splitlines() if line.strip()}

def execution_firewall_decision():
    """Fail-closed approval gate before any Topstep demo route.

    The daily note is human-facing memory, so approval must be deliberately
    machine-readable. Free-form bullish language is never enough.
    """
    blockers = []
    daily_path = today_daily_plan_path()
    daily_text = read_text_safe(daily_path)
    monitor, monitor_path = read_state_json("topstep-100k-monitor.latest.json")
    live_gate, live_gate_path = read_state_json("live-readiness-gate.latest.json")

    if not daily_text:
        blockers.append(f"daily plan missing or unreadable: {daily_path}")
    else:
        control_lines = machine_control_lines(daily_text)
        if "No new Bill/Hermes orders approved" in daily_text:
            blockers.append("daily plan explicitly says no new Bill/Hermes orders approved")
        if "BILL_ROUTE_APPROVAL: APPROVED" not in control_lines:
            blockers.append("daily plan lacks BILL_ROUTE_APPROVAL: APPROVED")
        if "BROKER_RECONCILIATION: GREEN" not in control_lines:
            blockers.append("daily plan lacks BROKER_RECONCILIATION: GREEN")

    if os.environ.get("BILL_ENABLE_FUTURES_DEMO_EXECUTION") != "true":
        blockers.append("BILL_ENABLE_FUTURES_DEMO_EXECUTION is not true")
    if os.environ.get("RH_TOPSTEP_READ_ONLY") == "true":
        blockers.append("RH_TOPSTEP_READ_ONLY is true")
    if os.environ.get("RH_LIVE_EXECUTION_ENABLED") == "true":
        blockers.append("RH_LIVE_EXECUTION_ENABLED is true; master bridge is demo-only")
    if os.environ.get("RH_TOPSTEP_DEMO_ONLY") == "false":
        blockers.append("RH_TOPSTEP_DEMO_ONLY must not be false")

    if monitor.get("status") != "OK":
        blockers.append(f"Topstep monitor is not OK: {monitor.get('status', 'missing')}")
    hard_blockers = monitor.get("hard_blockers") or []
    warnings = monitor.get("warnings") or []
    if hard_blockers:
        blockers.append(f"Topstep monitor hard blockers: {hard_blockers}")
    if warnings:
        blockers.append(f"Topstep monitor warnings require reconciliation: {warnings}")

    if live_gate.get("readyForDemoExpansion") is not True:
        blockers.append("live-readiness gate does not allow demo expansion")

    return {
        "allowed": not blockers,
        "blockers": blockers,
        "daily_plan": str(daily_path),
        "monitor": str(monitor_path) if monitor_path else None,
        "live_readiness_gate": str(live_gate_path) if live_gate_path else None,
    }

# ── Import macro context engine ──
sys.path.insert(0, str(Path(__file__).parent))
import macro_context as mc
from new_arsenal_gate import new_arsenal_gate
from data_freshness_gate import check_freshness
from session_gate import gate_decision, detect_session, read_trade_count, increment_trade_count

    # ── Confluence signal readers ──
def read_rolling_window_params():
    """Read promoted rolling window optimizer output only."""
    d, _ = read_state_json("rolling-window-params.latest.json")
    if d.get("promoted_for_execution") is True:
        return d.get("parameters", {}), d.get("regime", "unknown")
    return {}, "shadow_only"

def read_dom_proxy_signal():
    """Read DOM proxy only if it has been explicitly promoted."""
    d, _ = read_state_json("dom-proxy-signal.latest.json")
    if promoted_execution_overlay(d):
        return d.get("direction", "neutral"), d.get("confidence", 0.0)
    return "neutral", 0.0

def read_kalman_pairs_signal():
    """Read Kalman pairs only if it has been explicitly promoted."""
    d, _ = read_state_json("kalman-pairs-signal.latest.json")
    if promoted_execution_overlay(d):
        return d.get("action", "HOLD"), d.get("direction", "neutral"), d.get("stats", {})
    return "HOLD", "neutral", {}

def read_whale_flow_signal():
    """Read whale flow only if it has been explicitly promoted."""
    d, _ = read_state_json("whale-flow-signal.latest.json")
    if promoted_execution_overlay(d):
        return d.get("direction", "neutral"), d.get("confidence", 0.0)
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

def is_fomc_day(now=None):
    return current_trading_date(now) in FOMC_DATES
BILL_ENV = Path(HOME) / "Library/Application Support/AgentPay/bill/bill.env"
DATA_DIR = Path(HOME) / "hedge" / "data" / "free"
STATE_DIR = CANONICAL_STATE_DIR

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

def bar_age_hours(bar):
    """Return age of a bar timestamp in hours; inf if timestamp is invalid."""
    try:
        ts = str(bar.get("ts", "")).replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600
    except Exception:
        return float("inf")

def iso_age_minutes(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60
    except Exception:
        return float("inf")

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

def write_master_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.joinpath("master-signal.latest.json").write_text(json.dumps(state, indent=2) + "\n")

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
def run_strategy(name, csv_name, strategy_fn, min_bars=30, symbol="NQ", max_age_hours=8):
    path = DATA_DIR / csv_name
    if not path.exists():
        print(f"  SKIP {name}: no data")
        return None
    bars = load_bars(path, symbol=symbol)
    if len(bars) < min_bars:
        print(f"  SKIP {name}: only {len(bars)} bars (need {min_bars})")
        return None
    age_h = bar_age_hours(bars[-1])
    if age_h > max_age_hours:
        print(f"  SKIP {name}: stale data (last bar: {bars[-1]['ts']}, age={age_h:.1f}h, max={max_age_hours}h)")
        return None
    sig = strategy_fn(bars)
    print(f"  {'✅' if sig else '⏸️'} {name}: {'signal' if sig else 'no signal'} (last bar: {bars[-1]['ts']})")
    return sig

def main():
    # ⛔ FOMC safety check
    if is_fomc_day():
        print(f"\n{'='*60}")
        print(f"⛔ FOMC DAY — {current_trading_date()} — NO TRADING")
        print(f"Strategies disabled. Market patterns unreliable on FOMC days.")
        print(f"{'='*60}\n")
        state = {"ts": datetime.now(timezone.utc).isoformat(), "signal": None,
            "reason": "FOMC day — trading blocked"}
        write_master_state(state)
        return

    # ⛔ DATA FRESHNESS GATE — block if Yahoo data is stale
    nq_check = check_freshness("NQ=F")
    es_check = check_freshness("ES=F")
    if nq_check["status"] in ("STALE", "BLOCK") or es_check["status"] in ("STALE", "BLOCK"):
        print(f"\n{'='*60}")
        print(f"⛔ DATA FRESHNESS GATE — BLOCKING ALL TRADES")
        print(f"NQ: {nq_check.get('age_seconds','?')}s old ({nq_check.get('reason','?')})")
        print(f"ES: {es_check.get('age_seconds','?')}s old ({es_check.get('reason','?')})")
        print(f"{'='*60}\n")
        state = {"ts": datetime.now(timezone.utc).isoformat(), "signal": None,
            "reason": f"Data stale — NQ:{nq_check.get('age_seconds','?')}s ES:{es_check.get('age_seconds','?')}s"}
        write_master_state(state)
        return

    print(f"\n{'='*60}")
    print(f"HERMES STRATEGY BRIDGE — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    # Run ALL strategies across ALL instruments
    signals = []

    # ── SESSION DETECTION ──
    now_et = ny_minutes()
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
    trading_day = current_trading_date().isoformat()
    risk = {"daily_loss": 0.0, "daily_profit": 0.0, "cumulative_loss": 0.0,
            "cumulative_profit": 0.0, "trade_count": 0, "day": trading_day,
            "runway_days": 4, "blocked": False}
    if risk_path.exists():
        try:
            old = json.loads(risk_path.read_text())
            if old.get("day") == trading_day:
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
            today_str = trading_day
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
    signals.append(run_strategy("NQ orb-breakout    (60m)", "NQ-60m-60d.csv", lambda b: orb_breakout(b, 8, 14), min_bars=12))
    signals.append(run_strategy("NQ wq-trend-mom   (60m)", "NQ-60m-60d.csv", wq_trend_momentum))
    signals.append(run_strategy("NQ wq-vol-regime  (60m)", "NQ-60m-60d.csv", wq_vol_regime))

    print("\n--- NQ 30m Strategies ---")
    signals.append(run_strategy("NQ orb-breakout    (30m)", "NQ-30m-60d.csv", lambda b: orb_breakout(b, 12, 13)))

    print("\n--- NQ 15m Strategies ---")
    signals.append(run_strategy("NQ orb-breakout    (15m)", "NQ-15m-60d.csv", lambda b: orb_breakout(b, 12, 14)))
    signals.append(run_strategy("NQ wq-trend-mom   (15m)", "NQ-15m-60d.csv", wq_trend_momentum))
    signals.append(run_strategy("NQ wq-vol-regime  (15m)", "NQ-15m-60d.csv", wq_vol_regime))

    print("\n--- NQ 5m Strategies ---")
    signals.append(run_strategy("NQ orb-breakout    (5m)",  "NQ-5m-5d.csv",  lambda b: orb_breakout(b, 12, 8), min_bars=30))
    signals.append(run_strategy("NQ wq-trend-mom   (5m)",  "NQ-5m-5d.csv",  wq_trend_momentum, min_bars=60))

    # ── ES STRATEGIES (proven at 60m) ──
    print("\n--- ES 60m Strategies ---")
    signals.append(run_strategy("ES orb-breakout    (60m)", "ES-60m-60d.csv", lambda b: orb_breakout(b, 12, 14), min_bars=16, symbol="ES"))
    signals.append(run_strategy("ES wq-trend-mom   (60m)", "ES-60m-60d.csv", wq_trend_momentum, symbol="ES"))
    signals.append(run_strategy("ES wq-vol-regime  (60m)", "ES-60m-60d.csv", wq_vol_regime, symbol="ES"))

    best = pick_best(signals)
    print(f"\n{'='*60}")
    if best is None:
        print("NO TRADE — no strategy has an entry signal right now")
        state = {"ts": datetime.now(timezone.utc).isoformat(), "signal": None,
                 "reason": "no entry conditions met across 9 strategy/timeframe combos"}
        write_master_state(state)
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
    pending_is_fresh = (
        last_sig.get("status") == "pending_topstep_demo_submission"
        and iso_age_minutes(last_sig.get("ts")) <= 10
    )
    already_routed = last_sig.get("submitted") is True or pending_is_fresh
    if last_sig.get("signal") == sig_key and already_routed:
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
        write_master_state(state)
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
        write_master_state(state)
        return

    firewall = execution_firewall_decision()
    if not firewall["allowed"]:
        print("\n⛔ EXECUTION FIREWALL — Topstep demo route blocked")
        for blocker in firewall["blockers"]:
            print(f"  • {blocker}")
        state = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signal": sig_key,
            "strategy": best["strategy"],
            "side": best["side"],
            "entry": round(best["entry"], 2),
            "stop": round(best["stop"], 2),
            "target": round(best["target"], 2),
            "rr": round(best["rr"], 2),
            "contracts": 0,
            "research_contracts": calc_position(best),
            "accounts": 0,
            "route": "shadow_only",
            "submitted": False,
            "status": "demo_route_blocked",
            "execution_firewall": firewall,
        }
        write_master_state(state)
        return

    # ── Session Gate — skip London/Premarket, cap 3 trades/session, Tue=full, Wed/Fri=half ──
    session = detect_session()
    trade_count = read_trade_count()
    sgate_ok, sgate_reason, sgate_mult, sgate_rem = gate_decision(session=session, trade_count=trade_count)
    if not sgate_ok:
        print(f"\n⛔ SESSION GATE — {sgate_reason}")
        state = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signal": sig_key,
            "strategy": best["strategy"],
            "side": best["side"],
            "session": session,
            "trade_count": trade_count,
            "session_gate_reason": sgate_reason,
            "route": "shadow_only",
            "submitted": False,
            "status": "session_gate_blocked",
        }
        write_master_state(state)
        return
    print(f"\n✓ SESSION GATE — {sgate_reason} | multiplier={sgate_mult:.1f}x | {sgate_rem} trades remaining")

    contracts = calc_position(best)
    # Apply session size multiplier + macro + arsenal modifiers
    contracts = max(3, min(int(contracts * ctx["confidence_modifier"] * ag["confidence_modifier"] * sgate_mult), 5))
    max_demo_contracts = positive_int_env("BILL_FUTURES_DEMO_MAX_CONTRACTS", 1)
    topstep_contracts = max(1, min(contracts, max_demo_contracts))
    print(f"\nBEST SIGNAL: [{best['strategy']}] {best['side'].upper()} @ ${best['entry']:.2f}")
    print(f"  SL: ${best['stop']:.2f}, TP: ${best['target']:.2f}, RR: {best['rr']:.2f}")
    print(f"  ATR: {best['atr']:.2f}, Confidence: {best['confidence']:.0%}")
    print(f"  Research size: {contracts} MNQ | Topstep demo route: {topstep_contracts} MNQ")
    print(f"  Trailing: {best.get('atr',30):.0f} pts trail, breakeven at {best.get('atr',30):.0f} pts")

    state = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "signal": sig_key,
        "strategy": best["strategy"],
        "side": best["side"],
        "entry": round(best["entry"], 2),
        "stop": round(best["stop"], 2),
        "target": round(best["target"], 2),
        "rr": round(best["rr"], 2),
        "contracts": topstep_contracts,
        "research_contracts": contracts,
        "accounts": 1,
        "route": "topstep_demo",
        "submitted": None,
        "status": "pending_topstep_demo_submission",
        "execution_firewall": firewall,
    }
    write_master_state(state)

    # 🆕 Route ALL signals to Topstep demo (LucidFlex/PickMyTrade disabled per founder)
    topstep_ok = False
    topstep_detail = None
    try:
        import subprocess
        bridge_path = Path(os.environ.get("HOME", "")) / ".hermes/scripts/topstep_demo_bridge.py"
        if bridge_path.exists():
            result = subprocess.run(
                [sys.executable or "python3", str(bridge_path)],
                capture_output=True, text=True, timeout=30
            )
            for line in result.stdout.splitlines():
                print(f"  [TopstepDemo] {line}")
            recent_path = STATE_DIR / "topstep-demo-submission.latest.json"
            if recent_path.exists():
                try:
                    recent = json.loads(recent_path.read_text())
                    topstep_ok = recent.get("submitted") is True and recent.get("last_signal") == sig_key
                    topstep_detail = recent.get("detail")
                except Exception as e:
                    topstep_detail = f"could_not_read_recent_submission: {e}"
            if result.stderr.strip():
                print(f"  [TopstepDemo] stderr: {result.stderr.strip()[:200]}")
    except Exception as e:
        print(f"  [TopstepDemo] Error: {e}")

    state.update({
        "ts": datetime.now(timezone.utc).isoformat(),
        "submitted": topstep_ok,
        "status": "topstep_demo_submitted" if topstep_ok else "topstep_demo_failed",
        "topstep_detail": topstep_detail,
    })
    write_master_state(state)
    print(f"\n{'✅' if topstep_ok else '❌'} {'TOPSTEP DEMO SUBMITTED' if topstep_ok else 'TOPSTEP DEMO FAILED'}")

if __name__ == "__main__":
    main()
