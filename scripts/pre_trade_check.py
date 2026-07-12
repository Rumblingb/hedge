#!/usr/bin/env python3
"""
PRE-TRADE CHECKER v2.1 — Unified Go/No-Go Decision
Institutional quality. Merges all 7 edges into ONE deterministic decision.
Works during and after hours. Outputs JSON for signalRouter consumption.

Usage:
  python3 scripts/pre_trade_check.py          # Normal run
  python3 scripts/pre_trade_check.py --force  # Force decision despite warnings
"""

__version__ = "2.1.1"

import json, subprocess, sys, os
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ──────────────────────────────────────────
# SECTION 1: DATA LAYER
# ──────────────────────────────────────────

BB_STATE_ROOT = Path(os.path.expanduser("~/.rumbling-hedge"))
STATE_DIR = BB_STATE_ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
DECISION_PATH = STATE_DIR / "pre_trade_decision.json"
LAST_CLOSE_PATH = BB_STATE_ROOT / "state" / "last_known_close.txt"

# Known last NQ close when market is closed (updated each run)
FALLBACK_NQ = 29231.75
FALLBACK_ATR = 11.23
NY_TIMEZONE = ZoneInfo(os.environ.get("BILL_NY_TIMEZONE", "America/New_York"))
POINT_VALUES = {
    "MNQ": 2.0,
    "NQ": 20.0,
    "MES": 5.0,
    "ES": 50.0,
}
DEFAULT_INSTRUMENT = "MNQ"

def point_value_for_instrument(instrument: str) -> float:
    symbol = (instrument or DEFAULT_INSTRUMENT).upper()
    return POINT_VALUES.get(symbol, POINT_VALUES[DEFAULT_INSTRUMENT])

def ny_minutes(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(NY_TIMEZONE)
    return local.hour * 60 + local.minute

def positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
        return value if value > 0 else default
    except Exception:
        return default

def fetch_nq_raw() -> dict:
    """Fetch NQ 5m bars with error handling. Returns {} on failure."""
    cmd = f"""cd /Users/brain/hedge && source ~/Library/Application\\ Support/AgentPay/bill/bill.env && npx tsx -e "
(async () => {{
  try {{
    const q = await (await fetch('https://query1.finance.yahoo.com/v8/finance/chart/MNQ=F?interval=5m&range=5d')).json();
    const r = q.chart?.result?.[0];
    process.stdout.write(JSON.stringify({{
      opens: r?.indicators?.quote?.[0]?.open || [],
      highs: r?.indicators?.quote?.[0]?.high || [],
      lows: r?.indicators?.quote?.[0]?.low || [],
      closes: r?.indicators?.quote?.[0]?.close || [],
      volumes: r?.indicators?.quote?.[0]?.volume || [],
      timestamps: r?.timestamp || []
    }}));
  }} catch(e) {{ process.stdout.write(JSON.stringify({{error: e.message}})); }}
}})();
" 2>/dev/null"""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except:
        return {}

def parse_nq_bars(data: dict) -> tuple:
    """Extract and clean NQ bar data. Returns (closes, highs, lows, opens, volumes, timestamps, is_fresh, freshness_msg)."""
    closes = data.get("closes", [])
    highs = data.get("highs", [])
    lows = data.get("lows", [])
    opens = data.get("opens", [])
    volumes = data.get("volumes", [])
    timestamps = data.get("timestamps", [])
    
    if not closes or len(closes) < 5:
        return [], [], [], [], [], [], False, "No data"
    
    # Check freshness
    last_ts = timestamps[-1] if timestamps else 0
    is_fresh = False
    msg = "No timestamp"
    if isinstance(last_ts, (int, float)) and last_ts > 1000000000:
        age_mins = (datetime.now(timezone.utc).timestamp() - last_ts) / 60
        if age_mins < 30:
            is_fresh = True
            msg = f"{age_mins:.0f} min old — fresh"
        elif age_mins < 60:
            is_fresh = True
            msg = f"{age_mins:.0f} min old — usable with caution"
        else:
            is_fresh = False
            msg = f"{age_mins:.0f} min old — stale, using fallback"
    
    # Convert to numpy and align lengths
    arrs = [np.array(x, dtype=np.float64) for x in [closes, highs, lows]]
    if opens: arrs.append(np.array(opens, dtype=np.float64))
    else: arrs.append(arrs[0])
    vols = np.array(volumes, dtype=np.float64) if volumes else np.ones(len(closes))
    
    min_len = min(len(a) for a in arrs + [vols])
    arrs = [a[:min_len] for a in arrs[:3]] + [arrs[3][:min_len]] + [vols[:min_len]]
    timestamps = timestamps[:min_len]
    
    # Filter NaN
    mask = ~(np.isnan(arrs[0]) | np.isnan(arrs[1]) | np.isnan(arrs[2]))
    arrs = [a[mask].tolist() for a in arrs]
    timestamps = [t for i, t in enumerate(timestamps) if i < len(mask) and mask[i]]
    
    return (*arrs, timestamps, is_fresh, msg)

# ──────────────────────────────────────────
# SECTION 2: EDGE COMPUTATION
# ──────────────────────────────────────────

from scipy import fft

def compute_edges(closes, highs, lows, opens, volumes) -> dict:
    """Compute all 7 edge signals from bar data."""
    current = closes[-1]
    n = len(closes)
    scores = {"bullish": 0, "bearish": 0}
    
    # 1. FFT OSCILLATOR
    log_returns = np.diff(np.log(np.array(closes, dtype=np.float64)))
    if len(log_returns) > 5:
        f = fft.rfft(log_returns - np.mean(log_returns))
        power = np.abs(f)
        if len(power) > 1:
            dom = int(np.argmax(power[1:])) + 1
            osc = float(np.sin(np.angle(f[dom])))
        else:
            osc = 0.0
    else:
        osc = 0.0
    
    scores["fft_osc"] = round(osc, 4)
    if osc < -0.5:
        scores["fft"] = "bearish"
        scores["bearish"] += 1
    elif osc > 0.5:
        scores["fft"] = "bullish"
        scores["bullish"] += 1
    else:
        scores["fft"] = "neutral"
    
    # 2. VWAP
    typical = (np.array(highs) + np.array(lows) + np.array(closes)) / 3
    vols = np.array(volumes, dtype=np.float64)
    vols = np.where(np.isnan(vols) | (vols <= 0), 1, vols)
    cum_pv = np.cumsum(typical * vols)
    cum_v = np.cumsum(vols)
    vwap = cum_pv / cum_v
    cur_vwap = float(vwap[-1])
    
    scores["vwap"] = cur_vwap
    scores["vwap_bias"] = "below" if current < cur_vwap else "above"
    scores["vwap_dev"] = round(current - cur_vwap, 1)
    if current < cur_vwap:
        scores["bearish"] += 1
    else:
        scores["bullish"] += 1
    
    # 3. MOMENTUM (1h = 12 bars 5m)
    if n >= 13:
        mom = (closes[-1] - closes[-13]) / closes[-13] * 100
    else:
        mom = 0.0
    scores["mom_1h"] = round(mom, 4)
    if mom > 0.05:
        scores["bullish"] += 1
    elif mom < -0.05:
        scores["bearish"] += 1
    
    # 4. OFI PROXY (last 5 bars)
    ofi_vals = []
    for i in range(max(0, n - 5), n):
        rng = highs[i] - lows[i]
        if rng > 0 and i < len(opens):
            body = abs(closes[i] - opens[i]) / rng
            upper = (highs[i] - max(closes[i], opens[i])) / rng if highs[i] > max(closes[i], opens[i]) else 0
            lower = (min(closes[i], opens[i]) - lows[i]) / rng if min(closes[i], opens[i]) > lows[i] else 0
            conv = body - max(upper, lower)
            is_bull = closes[i] > opens[i]
            ofi_vals.append(conv if is_bull else -conv)
    
    ofi = float(np.mean(ofi_vals)) if ofi_vals else 0.0
    scores["ofi"] = round(ofi, 4)
    if ofi > 0.1:
        scores["bullish"] += 1
    elif ofi < -0.1:
        scores["bearish"] += 1
    
    # 5. ATR
    tr = []
    for i in range(1, min(15, n)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        tr.append(max(hl, hc, lc))
    atr = float(np.mean(tr)) if tr else FALLBACK_ATR
    
    scores["atr"] = round(atr, 2)
    scores["atr_15m"] = round(atr * np.sqrt(3), 2)
    
    # 6. VOLUME
    avg_vol = float(np.nanmean(vols)) if len(vols) > 0 else 1
    recent_vol = float(np.nanmean(vols[-5:])) if len(vols) >= 5 else avg_vol
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1
    scores["vol_ratio"] = round(vol_ratio, 2)
    if vol_ratio > 1.5:
        if closes[-1] > (closes[-2] if len(closes) > 1 else closes[-1]):
            scores["bullish"] += 1
        else:
            scores["bearish"] += 1
    
    # 7. SESSION PHASE
    et = ny_minutes()
    if 570 <= et < 600:
        scores["session"] = "OPEN — observe only"
        scores["session_ok"] = False
    elif 600 <= et < 720:
        scores["session"] = "MID-MORNING — prime trading"
        scores["session_ok"] = True
    elif 720 <= et < 840:
        scores["session"] = "LUNCH — reduce or skip"
        scores["session_ok"] = False
    elif 840 <= et < 960:
        scores["session"] = "POWER HOUR — active"
        scores["session_ok"] = True
    else:
        scores["session"] = "CLOSED"
        scores["session_ok"] = False
    
    return scores

# ──────────────────────────────────────────
# SECTION 3: DECISION ENGINE
# ──────────────────────────────────────────

def decide(scores: dict, is_fresh: bool, force: bool = False, has_force_flag: bool = False) -> dict:
    """Make deterministic trading decision."""
    d = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": __version__,
        "decision": "NO_TRADE",
        "direction": "FLAT",
        "conviction": "LOW",
        "regime": "UNKNOWN",
        "composite": 0.0,
        "contracts": 0,
        "sl_pts": 0,
        "tp1_pts": 0,
        "tp2_pts": 0,
        "trail_pts": 0,
        "instrument": os.environ.get("BILL_PRE_TRADE_INSTRUMENT", DEFAULT_INSTRUMENT).upper(),
        "point_value": 0,
        "risk_dollars": 0,
        "tp1_dollars": 0,
        "tp2_dollars": 0,
        "research_only": True,
        "writes_orders": False,
        "touches_broker": False,
        "account_split": {},
        "warnings": [],
        "edges": scores,
    }
    
    b = scores.get("bullish", 0)
    s = scores.get("bearish", 0)
    total = b + s
    
    if total == 0:
        d["warnings"].append("No edge signals computed")
        return d
    
    # Freshness
    if not is_fresh and not has_force_flag:
        d["warnings"].append("STALE DATA — use --force to override")
        return d
    
    # Session check
    if not scores.get("session_ok", False) and not has_force_flag:
        if "CLOSED" in scores.get("session", ""):
            d["warnings"].append("Market closed — use --force to override")
            return d
    
    # Net score: -1 (all bearish) to +1 (all bullish)
    net = (b - s) / total
    d["composite"] = round(net, 4)
    
    # Direction
    if net > 0.15:
        d["direction"] = "LONG"
        d["conviction"] = "HIGH" if net > 0.4 else "MEDIUM"
        d["regime"] = "BULLISH" if scores.get("fft") == "bullish" else "BULLISH/mixed"
    elif net < -0.15:
        d["direction"] = "SHORT"
        d["conviction"] = "HIGH" if abs(net) > 0.4 else "MEDIUM"
        d["regime"] = "BEARISH" if scores.get("fft") == "bearish" else "BEARISH/mixed"
    else:
        d["direction"] = "FLAT"
        d["conviction"] = "LOW"
        d["regime"] = "NEUTRAL"
    
    # Position sizing
    atr_15m = scores.get("atr_15m", 20.0)
    
    if d["conviction"] == "HIGH":
        research_contracts = 4
    elif d["conviction"] == "MEDIUM":
        research_contracts = 2
    else:
        research_contracts = 0
    max_contracts = positive_int_env("BILL_PRE_TRADE_MAX_CONTRACTS", positive_int_env("BILL_FUTURES_DEMO_MAX_CONTRACTS", 1))
    contracts = min(research_contracts, max_contracts) if d["direction"] != "FLAT" else 0
    
    d["contracts"] = contracts
    d["research_contracts"] = research_contracts
    d["max_contracts"] = max_contracts
    d["sl_pts"] = round(atr_15m * 1.8, 1)
    d["tp1_pts"] = round(atr_15m * 1.5, 1)
    d["tp2_pts"] = round(atr_15m * 3.0, 1)
    d["trail_pts"] = round(atr_15m * 0.8, 1)
    d["point_value"] = point_value_for_instrument(d["instrument"])
    d["risk_dollars"] = round(d["sl_pts"] * d["point_value"] * contracts, 2)
    d["tp1_dollars"] = round(d["tp1_pts"] * d["point_value"] * contracts, 2)
    d["tp2_dollars"] = round(d["tp2_pts"] * d["point_value"] * contracts, 2)
    
    # Account isolation (max 1 MNQ per account, staggered)
    accts = ["lucidflex_1", "lucidflex_2", "fundednext", "topstep"]
    remaining = contracts
    for acct in accts:
        if remaining > 0:
            d["account_split"][acct] = 1
            remaining -= 1
        else:
            d["account_split"][acct] = 0
    
    if contracts > 0:
        d["stagger_min"] = 5  # 5 min between accounts
        if d["direction"] != "FLAT":
            d["decision"] = "TRADE" if contracts >= 3 else "REDUCED"
    
    return d

# ──────────────────────────────────────────
# SECTION 4: MAIN
# ──────────────────────────────────────────

def main():
    has_force = "--force" in sys.argv
    
    print("=" * 65)
    print(f"  PRE-TRADE CHECKER v{__version__} — {'FORCED' if has_force else 'NORMAL'} MODE")
    print("=" * 65)
    
    # 1. Fetch
    print("\n[1/5] Fetching NQ data...", end=" ", flush=True)
    raw = fetch_nq_raw()
    if "error" in raw:
        print(f"❌ {raw['error']}")
        return
    
    closes, highs, lows, opens, volumes, timestamps, fresh, msg = parse_nq_bars(raw)
    if not closes:
        print("❌ No valid bars")
        return
    print(f"✅ {len(closes)} bars")
    
    # 2. Freshness
    print(f"[2/5] Freshness: {'✅' if fresh else '⚠️'} {msg}")
    
    # 3. Edges
    print("[3/5] Computing edges...", end=" ", flush=True)
    scores = compute_edges(closes, highs, lows, opens, volumes)
    print(f"✅ {scores['bullish']} bullish / {scores['bearish']} bearish / {scores.get('session', '?')}")
    
    # 4. Decide
    print("[4/5] Making decision...", end=" ", flush=True)
    decision = decide(scores, fresh, has_force, has_force)
    print(f"✅ {decision['decision']}")
    
    # 5. Output
    print(f"\n[5/5] Result:")
    print(f"  Decision: {decision['decision']}")
    print(f"  Direction: {decision['direction']} | Conviction: {decision['conviction']}")
    print(f"  Regime: {decision['regime']} | Net: {decision['composite']:+.4f}")
    
    if decision['contracts'] > 0:
        print(f"\n  Position: {decision['contracts']} MNQ total")
        print(f"  Split: {decision['account_split']}")
        print(f"  Stagger: {decision.get('stagger_min', 0)} min")
        print(f"  SL: {decision['sl_pts']} | TP1: {decision['tp1_pts']} | TP2: {decision['tp2_pts']} | Trail: {decision['trail_pts']}")
        print(f"  Risk: ${decision['risk_dollars']:.2f} | TP1: ${decision['tp1_dollars']:.2f} | TP2: ${decision['tp2_dollars']:.2f} ({decision['instrument']} ${decision['point_value']:.2f}/pt)")
    
    if decision['warnings']:
        print(f"\n  ⚠️  {len(decision['warnings'])} warning(s):")
        for w in decision['warnings']:
            print(f"    • {w}")
    
    # Save
    with open(DECISION_PATH, "w") as f:
        json.dump(decision, f, indent=2, default=str)
    print(f"\n  💾 {DECISION_PATH}")
    
    # Save last close for reference
    with open(LAST_CLOSE_PATH, "w") as f:
        f.write(str(closes[-1]) if closes else str(FALLBACK_NQ))
    
    if not has_force:
        print(f"\n  Tip: use --force to override stale-data/closed-market warnings\n")

if __name__ == "__main__":
    main()
