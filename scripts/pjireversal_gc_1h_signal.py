#!/usr/bin/env python3
"""GC PJI Reversal 1h signal generator — HEURISTIC STUB.

AI Scientist verified PF 1.586 for pji_reversal (GC 1h, pji_lookback=8,
pji_threshold=0.002, hold_bars=10). Artifacts:
  Agent-Hermes/ai-scientist-p1-pji-implemented-2026-06-08.md
  Agent-Hermes/ai-scientist-p2-pji-lookback-sweep-2026-06-08.md

Real PJI formula: Jerk[i] = P[i] - 3P[i-1] + 3P[i-2] - P[i-3]
                  PJI = rolling_mean(Jerk, lookback)
Signal: PJI crosses -threshold → LONG, PJI crosses +threshold → SHORT

THIS implementation uses a different (simpler) heuristic. Not a replication.
GC Topstep bars not yet in archive — exits non-zero until available.
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
SIGNAL_PATH = STATE / "gc-pjireversal-signal.latest.json"
GC_CSV = BAR_ARCHIVE / "GC-1m-topstep-readonly.csv"

PJI_LOOKBACK = 8
PJI_THRESHOLD = 0.002


def load_gc_1h():
    if not GC_CSV.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_csv(GC_CSV, parse_dates=["ts"]).sort_values("ts")
        h1 = df.set_index("ts")[["open","high","low","close","volume"]].resample("1h").agg(
            {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
        ).dropna()
        return h1 if len(h1) >= PJI_LOOKBACK + 5 else None
    except Exception:
        return None


def compute_pji(closes, lookback=PJI_LOOKBACK, threshold=PJI_THRESHOLD):
    import numpy as np
    if len(closes) < lookback + 4:
        return "neutral", 0.0
    jerk = [closes[i] - 3*closes[i-1] + 3*closes[i-2] - closes[i-3]
            for i in range(3, len(closes))]
    pji_series = np.convolve(jerk, np.ones(lookback)/lookback, mode="valid")
    if len(pji_series) < 2:
        return "neutral", 0.0
    prev_pji, curr_pji = pji_series[-2], pji_series[-1]
    if prev_pji > threshold and curr_pji <= threshold:
        return "bearish", 0.55
    if prev_pji < -threshold and curr_pji >= -threshold:
        return "bullish", 0.55
    return "neutral", 0.0


def main():
    now = datetime.now(timezone.utc).isoformat()
    h1 = load_gc_1h()

    if h1 is None:
        print("GC pjireversal: no GC Topstep bars — exiting without writing signal", file=sys.stderr)
        sys.exit(1)

    closes = h1["close"].values
    direction, conf = compute_pji(closes)

    result = {
        "ts": now, "direction": direction, "confidence": conf,
        "strategy": "pji_reversal_stub", "timeframe": "1h", "symbol": "GC",
        "pji_lookback": PJI_LOOKBACK, "pji_threshold": PJI_THRESHOLD,
        "implementation_status": "HEURISTIC_STUB",
        "claimed_edge_source": "Agent-Hermes/ai-scientist-p1-pji-implemented-2026-06-08.md",
        "claimed_edge_pf": 1.586, "verified": False,
        "promoted_for_execution": False, "tradable_signal": False,
        "researchOnly": True, "writesOrders": False,
        "note": "STUB: PJI formula implemented but not backtested against AI Scientist OOS. 1.586 PF is AI Scientist claim.",
    }
    SIGNAL_PATH.write_text(json.dumps(result, indent=2))
    print(f"GC pjireversal stub: {direction} conf={conf:.2f} [HEURISTIC_STUB]")


if __name__ == "__main__":
    main()
