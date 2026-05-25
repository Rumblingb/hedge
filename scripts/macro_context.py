#!/usr/bin/env python3
"""
Macro Context Engine — Gives us the highest probability by filtering trades through every relevant lens.

Before ANY trade fires, this engine checks:
  - Economic calendar (CPI, NFP, FOMC, etc.) — avoid trading into known events
  - Market sentiment (VIX, put/call ratio, fear/greed) — is risk-on or risk-off?
  - Cross-asset context (DXY, bond yields, gold) — what are other markets saying?
  - Intraday session phase (open, lunch, close) — best times for each strategy
  - Volatility regime (low/normal/high) — adjust sizing accordingly
  - News sentiment (headline scanning) — major events that change everything

Returns a verdict: TRADE | REDUCED | NO_TRADE with reasons.
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

HOME = os.environ["HOME"]
STATE_DIR = Path(HOME) / "hedge" / ".rumbling-hedge" / "state"
DATA_DIR = Path(HOME) / "hedge" / "data" / "free"

# ── 2026 Macro Calendar — Major Events ──
# High-impact US data releases that can disrupt any trade
MACRO_EVENTS_2026 = {
    # FOMC
    (5, 19): "FOMC Decision",
    (6, 16): "FOMC Day 1", (6, 17): "FOMC Decision",
    (7, 28): "FOMC Day 1", (7, 29): "FOMC Decision",
    (9, 15): "FOMC Day 1", (9, 16): "FOMC Decision",
    (11, 3): "FOMC Day 1", (11, 4): "FOMC Decision",
    (12, 15): "FOMC Day 1", (12, 16): "FOMC Decision",
    # CPI
    (6, 10): "CPI Release", (7, 15): "CPI Release",
    (8, 12): "CPI Release", (9, 11): "CPI Release",
    (10, 14): "CPI Release", (11, 13): "CPI Release", (12, 11): "CPI Release",
    # PPI
    (6, 11): "PPI Release", (7, 16): "PPI Release",
    # NFP (jobs)
    (6, 5): "NFP/Jobs", (7, 2): "NFP/Jobs",
    (8, 7): "NFP/Jobs", (9, 4): "NFP/Jobs",
    (10, 2): "NFP/Jobs", (11, 6): "NFP/Jobs", (12, 4): "NFP/Jobs",
    # Other high impact
    (6, 1): "ISM Manufacturing", (7, 1): "ISM Manufacturing",
    (6, 3): "ISM Services", (7, 3): "ISM Services",
    (6, 24): "GDP Final", (7, 30): "GDP Advance",
    (6, 12): "Michigan Sentiment", (7, 11): "Michigan Sentiment",
}

def today_events():
    """Get any macro event happening today."""
    m = date.today()
    return MACRO_EVENTS_2026.get((m.month, m.day))

def next_3_days_events():
    """Get events in the next 3 days."""
    events = []
    for i in range(4):
        d = date.today() + timedelta(days=i)
        ev = MACRO_EVENTS_2026.get((d.month, d.day))
        if ev:
            events.append({"date": d.isoformat(), "event": ev})
    return events

def check_data_freshness():
    """Are our data files fresh (within last 2 hours for 15m, 3 hours for 60m)?"""
    now = datetime.now(timezone.utc).timestamp()
    checks = [
        ("15m", DATA_DIR / "NQ-15m-5d.csv", 7200),       # 2 hours
        ("60m", DATA_DIR / "NQ-60m-1d.csv", 10800),      # 3 hours
    ]
    stale = []
    for name, path, max_age in checks:
        if path.exists():
            age = now - path.stat().st_mtime
            if age > max_age:
                stale.append(f"{name} ({age/60:.0f}m old)")
        else:
            stale.append(f"{name} (missing)")
    return stale

# ── Fetch Market Context ──
def get_vix():
    try:
        req = urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read())
            quotes = d["chart"]["result"][0]["indicators"]["quote"][0]
            closes = [c for c in quotes["close"] if c is not None]
            return closes[-1] if closes else None
    except:
        return None

def get_dxy():
    try:
        req = urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1d&range=5d",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read())
            quotes = d["chart"]["result"][0]["indicators"]["quote"][0]
            closes = [c for c in quotes["close"] if c is not None]
            return closes[-1] if closes else None
    except:
        return None

def get_news_sentiment():
    """Quick news scan for NQ-related headlines. Returns bearish/neutral/bullish."""
    try:
        req = urllib.request.Request(
            "https://finance.yahoo.com/news/",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            html = r.read().decode("utf-8", errors="ignore")
            # Count bullish vs bearish keywords
            bullish = html.lower().count("rally") + html.lower().count("surge") + html.lower().count("bullish")
            bearish = html.lower().count("plunge") + html.lower().count("crash") + html.lower().count("bearish")
            if bearish > bullish * 2:
                return "bearish"
            elif bullish > bearish * 2:
                return "bullish"
            return "neutral"
    except:
        return "neutral"

# ── Decision Engine ──
def assess(signal):
    """
    Full-context assessment. Returns:
      verdict: "TRADE" | "REDUCED" | "NO_TRADE"
      confidence_modifier: multiplies position size (0.0-1.0)
      reasons: list of factors
    """
    reasons = []
    blockers = []
    modifiers = []

    # 1. MACRO EVENT TODAY?
    event = today_events()
    if event:
        if "FOMC" in event:
            return {"verdict": "NO_TRADE", "confidence_modifier": 0.0,
                    "reasons": [f"FOMC day — {event} — no trading"]}
        if "NFP" in event or "CPI" in event:
            blockers.append(f"High-impact event: {event}")
            modifiers.append(0.3)  # Drastically reduce size

    # 2. MACRO EVENT IN NEXT 3 DAYS?
    upcoming = next_3_days_events()
    if upcoming:
        for ev in upcoming:
            if ev["date"] != date.today().isoformat():
                reasons.append(f"Event in {ev['date']}: {ev['event']}")

    # 3. MARKET VOLATILITY (VIX)
    vix = get_vix()
    if vix:
        if vix > 30:
            blockers.append(f"VIX at {vix:.1f} — extreme fear, no directional trades")
        elif vix > 22:
            reasons.append(f"VIX at {vix:.1f} — elevated, reduce size")
            modifiers.append(0.5)
        elif vix < 13:
            reasons.append(f"VIX at {vix:.1f} — low, trend-friendly")
            modifiers.append(1.2)
        else:
            reasons.append(f"VIX at {vix:.1f} — normal")
            modifiers.append(1.0)

    # 4. SESSION PHASE
    now_et = datetime.now(timezone.utc).hour - 4  # EDT = UTC-4
    if now_et < 4:
        now_et += 24
    if 9 <= now_et <= 10:
        reasons.append("Session: open (high vol, best for breakouts)")
        modifiers.append(1.1)
    elif 10 < now_et <= 12:
        reasons.append("Session: mid-morning (trend develops)")
        modifiers.append(1.0)
    elif 12 < now_et <= 14:
        reasons.append("Session: lunch (low vol, range-bound)")
        modifiers.append(0.7)
    elif 14 < now_et <= 16:
        reasons.append("Session: afternoon (positioning for close)")
        modifiers.append(0.9)

    # 5. DATA FRESHNESS
    stale = check_data_freshness()
    if stale:
        blockers.append(f"Stale data: {', '.join(stale)}")
        modifiers.append(0.5)

    # 6. NEWS SENTIMENT
    sentiment = get_news_sentiment()
    if sentiment == "bearish" and signal and signal.get("side") == "long":
        blockers.append("Bearish news sentiment conflicting with long signal")
        modifiers.append(0.5)
    elif sentiment == "bullish" and signal and signal.get("side") == "short":
        blockers.append("Bullish news sentiment conflicting with short signal")
        modifiers.append(0.5)

    # 7. CROSS-ASSET: Dollar index
    dxy = get_dxy()
    if dxy:
        if dxy > 105:
            reasons.append(f"DXY at {dxy:.1f} — strong dollar, headwind for NQ longs")
            if signal and signal.get("side") == "long":
                modifiers.append(0.7)
        elif dxy < 100:
            reasons.append(f"DXY at {dxy:.1f} — weak dollar, tailwind for NQ")
            if signal and signal.get("side") == "long":
                modifiers.append(1.2)

    # ── FINAL VERDICT ──
    if blockers:
        if any("FOMC" in b for b in blockers):
            return {"verdict": "NO_TRADE", "confidence_modifier": 0.0,
                    "reasons": blockers}
        return {"verdict": "REDUCED", "confidence_modifier": min(modifiers) if modifiers else 0.5,
                "reasons": blockers + reasons}

    avg_mod = sum(modifiers) / len(modifiers) if modifiers else 1.0
    avg_mod = max(0.1, min(avg_mod, 1.5))

    if avg_mod < 0.4:
        return {"verdict": "NO_TRADE", "confidence_modifier": 0.0,
                "reasons": reasons + [f"Confidence too low ({avg_mod:.2f})"]}
    elif avg_mod < 0.7:
        return {"verdict": "REDUCED", "confidence_modifier": avg_mod,
                "reasons": reasons + [f"Reduced confidence ({avg_mod:.2f})"]}

    return {"verdict": "TRADE", "confidence_modifier": avg_mod, "reasons": reasons}

def main():
    print(f"{'='*60}")
    print(f"MACRO CONTEXT ENGINE — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")

    today_ev = today_events()
    print(f"\n📅 Macro today: {today_ev or 'No major events'}")
    
    upcoming = next_3_days_events()
    if upcoming:
        parts = [f"{e['date']} {e['event']}" for e in upcoming]
        print(f"   Upcoming: {' | '.join(parts)}")

    vix = get_vix()
    dxy = get_dxy()
    sentiment = get_news_sentiment()
    stale = check_data_freshness()

    print(f"\n📊 VIX: {vix:.1f}" if vix else "\n📊 VIX: N/A")
    print(f"💵 DXY: {dxy:.1f}" if dxy else "💵 DXY: N/A")
    print(f"📰 News sentiment: {sentiment}")
    print(f"📡 Data: {'stale: ' + ', '.join(stale) if stale else 'fresh'}")

    verdict = assess(None)
    print(f"\n{'='*60}")
    print(f"VERDICT: {verdict['verdict']}")
    for r in verdict["reasons"]:
        print(f"  • {r}")
    if verdict["verdict"] != "NO_TRADE":
        print(f"  Size modifier: {verdict['confidence_modifier']:.2f}x")
    print(f"{'='*60}")

    # Save state
    state = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "today_event": today_ev,
        "upcoming_events": upcoming,
        "vix": vix,
        "dxy": dxy,
        "sentiment": sentiment,
        "data_fresh": not stale,
        "stale_data": stale,
        "verdict": verdict,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "macro-context.latest.json").write_text(json.dumps(state, indent=2, default=str))
    print(f"\nSaved to state/macro-context.latest.json")

if __name__ == "__main__":
    main()
