#!/usr/bin/env python3
"""NQ VWAP Trend 15m signal generator — UNVERIFIED HEURISTIC.

NO AI Scientist artifact backing this as a standalone strategy.
The only VWAP research (ai-scientist-s2-orb-vwap-hybrid-2026-06-08.md) tested it
as a filter for ORB — marginal improvement, not a standalone edge.

This generator reads from Topstep readonly bar archive (NQ 1m), resamples to 15m,
computes session-anchored VWAP (resets at RTH open 14:30 UTC), and emits a
directional signal. It is informational only — never promoted for execution.
promoted_for_execution=False always. No profit_factor_backtest claim.
"""
import json, os, sys
from datetime import datetime, timezone, time as dtime
from pathlib import Path

VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge/state"
BAR_ARCHIVE = ROOT / ".rumbling-hedge/research/topstep-readonly-bars"
SIGNAL_PATH = STATE / "nq-vwaptrend-signal.latest.json"
NQ_CSV = BAR_ARCHIVE / "NQ-1m-topstep-readonly.csv"

RTH_OPEN_UTC = dtime(14, 30)   # 09:30 ET


def load_nq_15m():
    if not NQ_CSV.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_csv(NQ_CSV, parse_dates=["ts"]).sort_values("ts")
        df = df.set_index("ts")
        m15 = df[["open","high","low","close","volume"]].resample("15min").agg(
            {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
        ).dropna()
        return m15 if len(m15) >= 10 else None
    except Exception:
        return None


def session_anchored_vwap(m15):
    """Compute VWAP anchored to the most recent RTH session open."""
    import pandas as pd, numpy as np
    idx = m15.index
    # Find latest RTH open boundary
    session_start = None
    for ts in reversed(idx):
        t = ts.time() if hasattr(ts, 'time') else ts.to_pydatetime().time()
        if t <= RTH_OPEN_UTC and t >= dtime(14, 0):
            session_start = ts
            break
    if session_start is None:
        # Fallback: use last day's data
        last_date = idx[-1].date()
        session_df = m15[m15.index.date == last_date]
    else:
        session_df = m15[m15.index >= session_start]

    if len(session_df) < 2:
        return None, None

    typical = (session_df["high"] + session_df["low"] + session_df["close"]) / 3
    cum_tpv = (typical * session_df["volume"]).cumsum()
    cum_vol = session_df["volume"].cumsum()
    vwap_series = cum_tpv / cum_vol.replace(0, float("nan"))
    vwap = float(vwap_series.dropna().iloc[-1]) if not vwap_series.dropna().empty else None
    price = float(session_df["close"].iloc[-1])
    return vwap, price


def main():
    now = datetime.now(timezone.utc).isoformat()
    m15 = load_nq_15m()

    if m15 is None:
        print("NQ vwaptrend: no NQ Topstep bars — exiting without writing signal", file=sys.stderr)
        sys.exit(1)

    vwap, price = session_anchored_vwap(m15)
    if vwap is None or price is None:
        print("NQ vwaptrend: insufficient session bars", file=sys.stderr)
        sys.exit(1)

    dev = (price - vwap) / vwap if vwap > 0 else 0.0
    if dev > 0.001:
        direction, conf = "bullish", round(min(abs(dev) * 50, 0.6), 3)
    elif dev < -0.001:
        direction, conf = "bearish", round(min(abs(dev) * 50, 0.6), 3)
    else:
        direction, conf = "neutral", 0.0

    result = {
        "ts": now, "direction": direction, "confidence": conf,
        "strategy": "vwap_trend_heuristic", "timeframe": "15m", "symbol": "NQ",
        "vwap": round(vwap, 2), "price": round(price, 2), "dev_pct": round(dev * 100, 4),
        "implementation_status": "HEURISTIC_UNVERIFIED",
        "claimed_edge_pf": None, "verified": False,
        "promoted_for_execution": False, "tradable_signal": False,
        "researchOnly": True, "writesOrders": False,
        "data_source": "topstep-readonly-bars/NQ-1m",
        "note": "No standalone AI Scientist PF backing. Informational VWAP divergence only.",
    }
    SIGNAL_PATH.write_text(json.dumps(result, indent=2))
    print(f"NQ vwaptrend: {direction} conf={conf:.3f} vwap={vwap:.1f} price={price:.1f} [UNVERIFIED]")


if __name__ == "__main__":
    main()
