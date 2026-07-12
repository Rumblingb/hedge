#!/usr/bin/env python3
"""NQ Quant V4 Signal Adapter — bridges external/nq-quant engine into arbitration.

The NQ Quant V4 engine (ICT/FVG methodology) produces a completely different
edge from our ORB breakout. PF 3.53, +891.8R over 10.3 years, 0/11 negative years.

This adapter:
1. Runs the V4 engine on the latest NQ data
2. Extracts the current signal (direction + confidence)
3. Writes to nq-quant-signal.latest.json for arbitration to consume

Usage:
  BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true python3 scripts/nq_quant_signal.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "hedge"
STATE = ROOT / ".rumbling-hedge" / "state"
NQ_QUANT = ROOT / "external" / "nq-quant"
NQ_DATA = ROOT / "data" / "free"

OUTPUT = STATE / "nq-quant-signal.latest.json"


def get_latest_nq_bars() -> pd.DataFrame | None:
    """Load the latest NQ bars from our data directory."""
    import pandas as pd
    csv_path = NQ_DATA / "NQ-1m-5d.csv"
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    df = df.set_index("ts").sort_index()
    # Filter to most recent 5 days of RTH bars
    cutoff = df.index.max() - pd.Timedelta(days=5)
    return df[df.index >= cutoff]


def generate_signal() -> dict:
    """Generate a signal from the NQ Quant V4 logic.
    
    Currently a stub — full integration requires the V4 engine's dependencies
    (numpy, pandas, chain_engine). Run the engine backtest, extract direction
    from the most recent entry signal, return as arbitration-compatible dict.
    """
    try:
        df = get_latest_nq_bars()
        if df is None or len(df) < 200:
            return _neutral("insufficient data")
        
        # Stub: In production, this would call the V4 engine's live prediction
        # path. For now, returns neutral with metadata.
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signal": "nq-quant-v4",
            "strategy": "nq-quant-v4",
            "direction": "neutral",
            "confidence": 0.0,
            "promoted_for_execution": False,
            "active_window": True,
            "entry_price": None,
            "metadata": {
                "engine": "nq-quant-v4",
                "status": "stub",
                "data_bars": len(df),
                "data_range": f"{df.index[0]} to {df.index[-1]}",
                "note": "Full integration: run V4 engine backtest, extract live signal direction",
            },
        }
    except ImportError as e:
        return _neutral(f"dependency missing: {e}")
    except Exception as e:
        return _neutral(f"error: {e}")


def _neutral(reason: str) -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "signal": "nq-quant-v4",
        "strategy": "nq-quant-v4",
        "direction": "neutral",
        "confidence": 0.0,
        "promoted_for_execution": False,
        "active_window": True,
        "entry_price": None,
        "metadata": {"engine": "nq-quant-v4", "status": "stub", "note": reason},
    }


def main():
    signal = generate_signal()
    # Atomic write
    tmp = OUTPUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(signal, indent=2, default=str))
    tmp.rename(OUTPUT)
    print(f"✅ nq-quant-v4 signal written ({signal['metadata']['status']})")


if __name__ == "__main__":
    import pandas as pd
    main()
