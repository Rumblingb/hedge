#!/usr/bin/env python3
"""GC wq_vol_regime 1h signal generator — HEURISTIC STUB.

AI Scientist verified PF 3.411 for wq_vol_regime (GC 1h, short_lk=10, long_lk=20,
sh_th=1.2, lo_th=0.8, hold_bars=8). Artifact: Agent-Hermes/ai-scientist-gold-volregime-
final-optimal-2026-06-08.md

THIS implementation is NOT a replication of that strategy. It is an unverified heuristic.
GC bars not yet in topstep-readonly-bars archive — exits non-zero until available.
promoted_for_execution=False always.
"""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

VENV_PYTHON = Path("/Users/brain/hedge/.venv/bin/python")
if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

ROOT = Path("/Users/brain/hedge")
STATE = ROOT / ".rumbling-hedge/state"
BAR_ARCHIVE = ROOT / ".rumbling-hedge/research/topstep-readonly-bars"
SIGNAL_PATH = STATE / "gc-volregime-signal.latest.json"
GC_CSV = BAR_ARCHIVE / "GC-1m-topstep-readonly.csv"


def load_gc_1h():
    if not GC_CSV.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_csv(GC_CSV, parse_dates=["ts"]).sort_values("ts")
        h1 = df.set_index("ts")[["open","high","low","close","volume"]].resample("1h").agg(
            {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
        ).dropna()
        return h1 if len(h1) >= 22 else None
    except Exception:
        return None


def main():
    now = datetime.now(timezone.utc).isoformat()
    h1 = load_gc_1h()

    if h1 is None:
        print("GC volregime: no GC Topstep bars — exiting without writing signal", file=sys.stderr)
        sys.exit(1)

    import numpy as np
    closes = h1["close"].values
    highs = h1["high"].values
    lows = h1["low"].values
    atr_baseline = float(np.mean(highs[-20:] - lows[-20:]))
    momentum = float(closes[-1] - closes[-5])
    direction = "bullish" if momentum > 0 else ("bearish" if momentum < 0 else "neutral")
    conf = round(min(abs(momentum) / (atr_baseline * 2), 0.5), 3) if atr_baseline > 0 else 0.0

    result = {
        "ts": now, "direction": direction, "confidence": conf,
        "strategy": "wq_vol_regime_stub", "timeframe": "1h", "symbol": "GC",
        "implementation_status": "HEURISTIC_STUB",
        "claimed_edge_source": "Agent-Hermes/ai-scientist-gold-volregime-final-optimal-2026-06-08.md",
        "claimed_edge_pf": 3.411, "verified": False,
        "promoted_for_execution": False, "tradable_signal": False,
        "researchOnly": True, "writesOrders": False,
        "note": "STUB: not a replication of AI Scientist wq_vol_regime. 3.411 PF is AI Scientist claim, not this implementation.",
    }
    SIGNAL_PATH.write_text(json.dumps(result, indent=2))
    print(f"GC volregime stub: {direction} conf={conf:.3f} [HEURISTIC_STUB]")


if __name__ == "__main__":
    main()
