import numpy as np
from scipy import fft
from typing import List, Tuple, Optional

def detect_regime_fft(closes: List[float]) -> Tuple[str, float, float, float, float]:
    """
    Detect NQ regime using FFT on detrended (log-return) data.
    
    Returns: (regime: str, trend_ratio: float, trend_energy: float, mid_energy: float, noise_energy: float)
    
    Regimes:
    - RANGE:    ratio < 0.3 — ORB unreliable, use mean-reversion
    - TRENDING: ratio > 0.6 — ORB breakout, let winners run
    - MIXED:    0.3-0.6 — session-aware ORB with confirmation
    """
    arr = np.array(closes, dtype=np.float64)
    log_returns = np.diff(np.log(arr))
    n = len(log_returns)
    
    freq = fft.rfft(log_returns - np.mean(log_returns))
    power = np.abs(freq) ** 2
    
    # Frequency bands (in normalized frequency space)
    # 0-0.05 = trend cycles (20+ bars), 0.05-0.15 = medium (7-20 bars), 0.15+ = noise
    trend_band = int(n * 0.05)
    medium_band = int(n * 0.15)
    
    trend_energy = float(np.sum(power[:trend_band]))
    mid_energy = float(np.sum(power[trend_band:medium_band]))
    noise_energy = float(np.sum(power[medium_band:]))
    
    total = trend_energy + mid_energy + noise_energy
    ratio = trend_energy / total if total > 0 else 0.5
    
    if ratio < 0.3:
        regime = "RANGE"
    elif ratio > 0.6:
        regime = "TRENDING"
    else:
        regime = "MIXED"
    
    return regime, ratio, trend_energy, mid_energy, noise_energy


def fft_oscillator(closes: List[float]) -> float:
    """
    FFT oscillator: [-1, 1] where positive = dominant up-cycle, negative = dominant down-cycle.
    Extracts the phase of the dominant frequency component.
    """
    arr = np.array(closes, dtype=np.float64)
    log_returns = np.diff(np.log(arr))
    n = len(log_returns)
    
    freq = fft.rfft(log_returns - np.mean(log_returns))
    power = np.abs(freq)
    
    if len(power) < 2:
        return 0.0
    
    # Find dominant frequency (excluding DC)
    dom_idx = int(np.argmax(power[1:])) + 1
    dom_phase = np.angle(freq[dom_idx])
    dom_mag = power[dom_idx]
    
    # Normalize: phase → [-1, 1]
    osc = float(np.sin(dom_phase))
    return osc * min(1.0, dom_mag / np.mean(power[1:]))


def fft_volatility(closes: List[float], window: int = 10) -> float:
    """
    FFT-based volatility: ratio of noise energy to total energy.
    Higher = more random noise = less predictable.
    """
    arr = np.array(closes[-window*20:], dtype=np.float64)
    log_returns = np.diff(np.log(arr))
    n = len(log_returns)
    
    freq = fft.rfft(log_returns - np.mean(log_returns))
    power = np.abs(freq) ** 2
    
    noise_band = int(n * 0.15)
    noise_energy = float(np.sum(power[noise_band:]))
    total = float(np.sum(power))
    
    return noise_energy / total if total > 0 else 0.5


if __name__ == "__main__":
    # Quick test
    import json, subprocess
    cmd = "cd /Users/brain/hedge && source ~/Library/Application\ Support/AgentPay/bill/bill.env && npx tsx -e \"(async () => { const q = await (await fetch('https://query1.finance.yahoo.com/v8/finance/chart/NQ=F?range=5d&interval=5m')).json(); const c = q.chart?.result?.[0]?.indicators?.quote?.[0]?.close || []; process.stdout.write(JSON.stringify(c.filter(v => v != null))); })();\" 2>/dev/null"
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    closes = json.loads(r.stdout)
    
    regime, ratio, te, me, ne = detect_regime_fft(closes)
    osc = fft_oscillator(closes)
    vol = fft_volatility(closes)
    
    print(f"Bars: {len(closes)}")
    print(f"Regime: {regime}")
    print(f"Trend ratio: {ratio:.4f}")
    print(f"Trend/Mid/Noise: {te:.2f}/{me:.2f}/{ne:.2f}")
    print(f"FFT Oscillator: {osc:.4f}")
    print(f"FFT Noise ratio: {vol:.4f}")
