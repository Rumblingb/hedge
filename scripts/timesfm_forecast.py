#!/usr/bin/env python3
"""TimesFM forecast for NQ — integrated with bill pipeline"""

import sys, json, subprocess, os
sys.path.insert(0, os.path.expanduser("~/.hermes/venvs/timesfm/lib/python3.11/site-packages"))

from timesfm import TimesFm, TimesFmHparams, TimesFmCheckpoint
import numpy as np
import torch

def fetch_nq_5m(bars: int = 512) -> tuple[np.ndarray, list[float]]:
    """Fetch NQ 5m data, return (padded_input, original_closes)"""
    cmd = """cd /Users/brain/hedge && source ~/Library/Application\ Support/AgentPay/bill/bill.env && npx tsx -e "
(async () => {
  const q = await (await fetch('https://query1.finance.yahoo.com/v8/finance/chart/NQ=F?range=5d&interval=5m')).json();
  const c = q.chart?.result?.[0]?.indicators?.quote?.[0]?.close || [];
  process.stdout.write(JSON.stringify(c.filter(v => v != null)));
})();
" 2>/dev/null"""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    closes = json.loads(r.stdout)
    
    arr = np.array(closes, dtype=np.float64)
    # Log returns for TimesFM
    log_ret = np.diff(np.log(arr))
    
    # Pad if needed
    if len(log_ret) < bars:
        pad = np.zeros(bars - len(log_ret))
        padded = np.concatenate([pad, log_ret])
    else:
        padded = log_ret[-bars:]
    
    return padded.astype(np.float32).reshape(1, -1), closes

def run_timesfm_forecast(inputs: np.ndarray, horizon: int = 24) -> dict:
    """Run TimesFM forecast, return direction + confidence"""
    backend = 'mps' if torch.backends.mps.is_available() else 'cpu'
    hparams = TimesFmHparams(context_len=inputs.shape[1], horizon_len=horizon, backend=backend)
    ckpt_path = os.path.expanduser("~/.hermes/downloads/timesfm/models/torch_model.ckpt")
    ckpt = TimesFmCheckpoint(version='torch', path=ckpt_path, type='pt')
    model = TimesFm(hparams=hparams, checkpoint=ckpt)
    
    freq = np.array([0], dtype=np.int32)
    point, quantiles = model.forecast(inputs, freq)
    
    mean_return = float(point[0].mean())
    # Sum of last 12 bars (1 hour) = cumulative return
    cum_return_1h = float(point[0, :12].sum())
    cum_return_2h = float(point[0, :24].sum())
    
    direction = "UP" if cum_return_1h > 0 else "DOWN"
    # Confidence from quantile spread
    spread = float(np.mean(quantiles[0, :12, -1] - quantiles[0, :12, 0]))
    confidence = max(0.0, min(1.0, 1.0 - spread / 0.02))
    
    return {
        "mean_return": round(mean_return, 6),
        "cum_return_1h": round(cum_return_1h, 6),
        "cum_return_2h": round(cum_return_2h, 6),
        "direction": direction,
        "confidence": round(confidence, 4),
        "spread": round(spread, 6),
    }

if __name__ == "__main__":
    inputs, closes = fetch_nq_5m(512)
    forecast = run_timesfm_forecast(inputs, 24)
    
    current = closes[-1]
    forecast_1h = current * (1 + forecast["cum_return_1h"])
    forecast_2h = current * (1 + forecast["cum_return_2h"])
    
    print(f"NQ: {current:.2f}")
    print(f"TimesFM 1h forecast: {forecast_1h:.2f} ({forecast['direction']})")
    print(f"TimesFM 2h forecast: {forecast_2h:.2f}")
    print(f"Confidence: {forecast['confidence']:.1%}")
    print(f"Spread: {forecast['spread']:.6f}")
