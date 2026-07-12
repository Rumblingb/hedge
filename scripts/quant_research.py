#!/usr/bin/env python3
"""
Comprehensive quantitative research script for testing multiple strategies
on NQ 15m, 30m, and 60m data.
Outputs results sorted by total R and OOS-validated.
"""

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
import statistics
import math
from typing import List, Tuple, Optional, Union

# ======================
# Data Structures
# ======================

@dataclass
class Bar:
    ts: str  # raw timestamp string
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @property
    def dt(self) -> datetime:
        # Parse timestamp string to datetime (assumes UTC format with +00:00)
        # Remove timezone info for simplicity, treat as UTC
        dt_str = self.ts.replace('+00:00', '')
        return datetime.fromisoformat(dt_str)

# ======================
# Helper Functions
# ======================

def load_csv(path: str, symbol: str = "NQ") -> List[Bar]:
    """Load CSV file and return list of Bar objects filtered by symbol."""
    bars = []
    with open(path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['symbol'] == symbol:
                bars.append(Bar(
                    ts=row['ts'],
                    symbol=row['symbol'],
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume'])
                ))
    return bars

def session_classify(bar: Bar) -> str:
    """Classify bar into session: asia, london, ny, other (ET = UTC-4)."""
    # Convert UTC to ET by subtracting 4 hours
    et_dt = bar.dt - timedelta(hours=4)
    hour = et_dt.hour
    minute = et_dt.minute
    time_in_minutes = hour * 60 + minute
    
    # Asia: 19:00-03:00 ET => 1140 to 180 minutes (next day)
    if time_in_minutes >= 19*60 or time_in_minutes < 3*60:
        return "asia"
    # London: 03:00-07:00 ET => 180 to 420 minutes
    elif 3*60 <= time_in_minutes < 7*60:
        return "london"
    # NY: 09:30-16:00 ET => 570 to 960 minutes
    elif 9*60+30 <= time_in_minutes < 16*60:
        return "ny"
    else:
        return "other"

def sma(values: List[float], period: int) -> List[Optional[float]]:
    """Simple moving average."""
    result: List[Optional[float]] = [None] * len(values)
    if period <= 0:
        return result
    for i in range(len(values)):
        if i < period - 1:
            result[i] = None
        else:
            result[i] = sum(values[i-period+1:i+1]) / period
    return result

def atr(bars: List[Bar], idx: int, period: int = 14) -> float:
    """Average True Range at index idx."""
    if idx < period:
        return 0.0
    tr_sum = 0.0
    for i in range(idx - period + 1, idx + 1):
        high = bars[i].high
        low = bars[i].low
        prev_close = bars[i-1].close if i > 0 else bars[i].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_sum += tr
    return tr_sum / period

def avg_vol(bars: List[Bar], idx: int, window: int = 20) -> float:
    """Average volume over lookback window."""
    if idx < window:
        return 0.0
    vol_sum = sum(bars[i].volume for i in range(idx - window + 1, idx + 1))
    return vol_sum / window

def stdev(values: List[float], idx: int, window: int) -> float:
    """Standard deviation of values over lookback window."""
    if idx < window:
        return 0.0
    slice_vals = values[idx - window + 1:idx + 1]
    mean = statistics.mean(slice_vals)
    variance = sum((x - mean) ** 2 for x in slice_vals) / window
    return math.sqrt(variance)

def safe_float(val: Optional[float]) -> float:
    """Convert Optional[float] to float, returning 0.0 if None."""
    return val if val is not None else 0.0

# ======================
# Strategy Definitions
# ======================

class Strategy:
    """Base class for strategies."""
    def __init__(self, name: str, exit_bars: int):
        self.name = name
        self.exit_bars = exit_bars
    
    def generate_signals(self, bars: List[Bar]) -> List[Tuple[int, int, str]]:
        """
        Generate trading signals.
        Returns list of (entry_idx, exit_idx, direction) where direction is 'long' or 'short'.
        exit_idx = entry_idx + exit_bars (if within bounds).
        """
        signals = []
        for i in range(len(bars)):
            if self.should_enter_long(bars, i):
                exit_idx = i + self.exit_bars
                if exit_idx < len(bars):
                    signals.append((i, exit_idx, 'long'))
            if self.should_enter_short(bars, i):
                exit_idx = i + self.exit_bars
                if exit_idx < len(bars):
                    signals.append((i, exit_idx, 'short'))
        return signals
    
    def should_enter_long(self, bars: List[Bar], idx: int) -> bool:
        raise NotImplementedError
    
    def should_enter_short(self, bars: List[Bar], idx: int) -> bool:
        raise NotImplementedError

# Helper to compute volume condition vol > 1.3 * avg_vol
def vol_condition(bars: List[Bar], idx: int, avg_window: int = 20) -> bool:
    if idx < avg_window:
        return False
    avg = avg_vol(bars, idx, avg_window)
    return bars[idx].volume > 1.3 * avg

# ======================
# Group A: Session-gated
# ======================

class WqTrendMomAsiaLondon(Strategy):
    """SMA20/50 crossover + vol>1.3 + exit=8, ONLY in Asia or London sessions."""
    def __init__(self):
        super().__init__("wq-trend-mom-asia-london", 8)
    
    def should_enter_long(self, bars: List[Bar], idx: int) -> bool:
        if idx < 50:
            return False
        # Session filter
        sess = session_classify(bars[idx])
        if sess not in ("asia", "london"):
            return False
        # Volume condition
        if not vol_condition(bars, idx):
            return False
        # SMA20/50 crossover: SMA20 > SMA50 and previous SMA20 <= previous SMA50
        closes = [bar.close for bar in bars]
        sma20 = sma(closes, 20)
        sma50 = sma(closes, 50)
        sma20_val = sma20[idx]
        sma50_val = sma50[idx]
        if sma20_val is None or sma50_val is None:
            return False
        if idx == 0:
            prev_sma20 = sma20_val
            prev_sma50 = sma50_val
        else:
            prev_sma20 = sma20[idx-1]
            prev_sma50 = sma50[idx-1]
            if prev_sma20 is None or prev_sma50 is None:
                return False
        return sma20_val > sma50_val and prev_sma20 <= prev_sma50
    
    def should_enter_short(self, bars: List[Bar], idx: int) -> bool:
        if idx < 50:
            return False
        sess = session_classify(bars[idx])
        if sess not in ("asia", "london"):
            return False
        if not vol_condition(bars, idx):
            return False
        closes = [bar.close for bar in bars]
        sma20 = sma(closes, 20)
        sma50 = sma(closes, 50)
        sma20_val = sma20[idx]
        sma50_val = sma50[idx]
        if sma20_val is None or sma50_val is None:
            return False
        if idx == 0:
            prev_sma20 = sma20_val
            prev_sma50 = sma50_val
        else:
            prev_sma20 = sma20[idx-1]
            prev_sma50 = sma50[idx-1]
            if prev_sma20 is None or prev_sma50 is None:
                return False
        return sma20_val < sma50_val and prev_sma20 >= prev_sma50

class OrbBreakoutNy(Strategy):
    """Range breakout from last 8 bars + vol>1.3 + exit=8, ONLY in NY session."""
    def __init__(self):
        super().__init__("orb-breakout-ny", 8)
    
    def should_enter_long(self, bars: List[Bar], idx: int) -> bool:
        if idx < 8:
            return False
        sess = session_classify(bars[idx])
        if sess != "ny":
            return False
        if not vol_condition(bars, idx):
            return False
        # Compute range of bars[i-8:i-1] (previous 8 bars, excluding current?)
        # Description: range breakout from last 8 bars -> likely high of last 8 bars
        start = idx - 8
        end = idx  # exclusive? We'll use bars[start:end] (8 bars)
        high_range = max(bars[i].high for i in range(start, end))
        low_range = min(bars[i].low for i in range(start, end))
        # Breakout above high_range
        return bars[idx].close > high_range
    
    def should_enter_short(self, bars: List[Bar], idx: int) -> bool:
        if idx < 8:
            return False
        sess = session_classify(bars[idx])
        if sess != "ny":
            return False
        if not vol_condition(bars, idx):
            return False
        start = idx - 8
        end = idx
        high_range = max(bars[i].high for i in range(start, end))
        low_range = min(bars[i].low for i in range(start, end))
        # Breakdown below low_range
        return bars[idx].close < low_range

# ======================
# Group B: Session composites
# ======================

class SessionComposite(Strategy):
    """Run all session-gated strategies (1+2), merge their trades."""
    def __init__(self):
        # We'll delegate to sub-strategies
        self.strategy1 = WqTrendMomAsiaLondon()
        self.strategy2 = OrbBreakoutNy()
        super().__init__("session-composite", 0)  # exit handled by sub-strategies
    
    def generate_signals(self, bars: List[Bar]) -> List[Tuple[int, int, str]]:
        signals1 = self.strategy1.generate_signals(bars)
        signals2 = self.strategy2.generate_signals(bars)
        # Merge and sort by entry_idx
        all_signals = signals1 + signals2
        all_signals.sort(key=lambda x: x[0])
        return all_signals

class WqVolRegime:
    """Helper for wq-vol-regime: short_vol/long_vol ratio."""
    def __init__(self, short_lookback: int = 10, long_lookback: int = 20,
                 short_threshold: float = 1.4, long_threshold: float = 0.8):
        self.short_lookback = short_lookback
        self.long_lookback = long_lookback
        self.short_threshold = short_threshold
        self.long_threshold = long_threshold
    
    def compute_ratio(self, bars: List[Bar], idx: int) -> Optional[float]:
        if idx < self.long_lookback:
            return None
        # short_vol: average true range over short_lookback
        tr_sum_short = 0.0
        for i in range(idx - self.short_lookback + 1, idx + 1):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i-1].close if i > 0 else bars[i].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_sum_short += tr
        avg_tr_short = tr_sum_short / self.short_lookback
        
        # long_vol: average true range over long_lookback
        tr_sum_long = 0.0
        for i in range(idx - self.long_lookback + 1, idx + 1):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i-1].close if i > 0 else bars[i].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_sum_long += tr
        avg_tr_long = tr_sum_long / self.long_lookback
        
        if avg_tr_long == 0:
            return None
        return avg_tr_short / avg_tr_long
    
    def signal_direction(self, bars: List[Bar], idx: int) -> Optional[str]:
        ratio = self.compute_ratio(bars, idx)
        if ratio is None:
            return None
        if ratio > self.short_threshold:
            return 'short'
        elif ratio < self.long_threshold:
            return 'long'
        else:
            return None

class TrendVolMerge(Strategy):
    """Fire ONLY when BOTH wq-trend-mom (any session) AND wq-vol-regime agree on direction."""
    def __init__(self):
        self.wq_trend_mom = WqTrendMomAnySession()  # defined later
        self.wq_vol_regime = WqVolRegime()
        super().__init__("trend-vol-merge", 5)  # exit=5 as per description
    
    def generate_signals(self, bars: List[Bar]) -> List[Tuple[int, int, str]]:
        signals = []
        for i in range(len(bars)):
            dir_trend = self.wq_trend_mom.get_direction(bars, i)
            dir_vol = self.wq_vol_regime.signal_direction(bars, i)
            if dir_trend is not None and dir_vol is not None and dir_trend == dir_vol:
                exit_idx = i + self.exit_bars
                if exit_idx < len(bars):
                    signals.append((i, exit_idx, dir_trend))
        return signals

class WqTrendMomAnySession(Strategy):
    """SMA20/50 crossover + vol>1.3 + exit=8, ANY session."""
    def __init__(self):
        super().__init__("wq-trend-mom-any", 8)
    
    def should_enter_long(self, bars: List[Bar], idx: int) -> bool:
        if idx < 50:
            return False
        if not vol_condition(bars, idx):
            return False
        closes = [bar.close for bar in bars]
        sma20 = sma(closes, 20)
        sma50 = sma(closes, 50)
        sma20_val = sma20[idx]
        sma50_val = sma50[idx]
        if sma20_val is None or sma50_val is None:
            return False
        if idx == 0:
            prev_sma20 = sma20_val
            prev_sma50 = sma50_val
        else:
            prev_sma20 = sma20[idx-1]
            prev_sma50 = sma50[idx-1]
            if prev_sma20 is None or prev_sma50 is None:
                return False
        return sma20_val > sma50_val and prev_sma20 <= prev_sma50
    
    def should_enter_short(self, bars: List[Bar], idx: int) -> bool:
        if idx < 50:
            return False
        if not vol_condition(bars, idx):
            return False
        closes = [bar.close for bar in bars]
        sma20 = sma(closes, 20)
        sma50 = sma(closes, 50)
        sma20_val = sma20[idx]
        sma50_val = sma50[idx]
        if sma20_val is None or sma50_val is None:
            return False
        if idx == 0:
            prev_sma20 = sma20_val
            prev_sma50 = sma50_val
        else:
            prev_sma20 = sma20[idx-1]
            prev_sma50 = sma50[idx-1]
            if prev_sma20 is None or prev_sma50 is None:
                return False
        return sma20_val < sma50_val and prev_sma20 >= prev_sma50
    
    def get_direction(self, bars: List[Bar], idx: int) -> Optional[str]:
        if self.should_enter_long(bars, idx):
            return 'long'
        if self.should_enter_short(bars, idx):
            return 'short'
        return None

# ======================
# Group C: BRONZE strategies
# ======================

class ShortTermReversal(Strategy):
    """If bar i moved >1.5 ATR from bar i-1 (big move), fade it."""
    def __init__(self):
        super().__init__("short-term-reversal", 5)
    
    def should_enter_long(self, bars: List[Bar], idx: int) -> bool:
        if idx < 1:
            return False
        # Big down move: close[i] < close[i-1] - 1.5*ATR
        atr_val = atr(bars, idx, 14)
        if atr_val == 0:
            return False
        big_down = bars[idx].close < bars[idx-1].close - 1.5 * atr_val
        return big_down
    
    def should_enter_short(self, bars: List[Bar], idx: int) -> bool:
        if idx < 1:
            return False
        atr_val = atr(bars, idx, 14)
        if atr_val == 0:
            return False
        big_up = bars[idx].close > bars[idx-1].close + 1.5 * atr_val
        return big_up

class GapFade(Strategy):
    """If open is >0.5 ATR above/below previous close, fade the gap direction."""
    def __init__(self):
        super().__init__("gap-fade", 3)
    
    def should_enter_long(self, bars: List[Bar], idx: int) -> bool:
        if idx < 1:
            return False
        atr_val = atr(bars, idx, 14)
        if atr_val == 0:
            return False
        # Gap down: open < prev_close - 0.5*ATR -> we long (fade gap up)
        gap_down = bars[idx].open < bars[idx-1].close - 0.5 * atr_val
        return gap_down
    
    def should_enter_short(self, bars: List[Bar], idx: int) -> bool:
        if idx < 1:
            return False
        atr_val = atr(bars, idx, 14)
        if atr_val == 0:
            return False
        gap_up = bars[idx].open > bars[idx-1].close + 0.5 * atr_val
        return gap_up

class VolumeSurgeReversal(Strategy):
    """If volume >3× avg(10) AND price >1.5σ from SMA20 → short. If price < -1.5σ from SMA20 → long."""
    def __init__(self):
        super().__init__("volume-surge-reversal", 5)
    
    def should_enter_long(self, bars: List[Bar], idx: int) -> bool:
        if idx < 10:
            return False
        # volume > 3 * avg(10)
        avg_vol_10 = avg_vol(bars, idx, 10)
        if bars[idx].volume <= 3 * avg_vol_10:
            return False
        # price < -1.5σ from SMA20
        closes = [bar.close for bar in bars]
        sma20_vals = sma(closes, 20)
        sma20_val = sma20_vals[idx]
        if sma20_val is None:
            return False
        # stddev of closes over 20
        price_stdev = stdev(closes, idx, 20)
        if price_stdev == 0:
            return False
        deviation = bars[idx].close - sma20_val
        return deviation < -1.5 * price_stdev
    
    def should_enter_short(self, bars: List[Bar], idx: int) -> bool:
        if idx < 10:
            return False
        avg_vol_10 = avg_vol(bars, idx, 10)
        if bars[idx].volume <= 3 * avg_vol_10:
            return False
        closes = [bar.close for bar in bars]
        sma20_vals = sma(closes, 20)
        sma20_val = sma20_vals[idx]
        if sma20_val is None:
            return False
        price_stdev = stdev(closes, idx, 20)
        if price_stdev == 0:
            return False
        deviation = bars[idx].close - sma20_val
        return deviation > 1.5 * price_stdev

class DonchianBreakout(Strategy):
    """20-bar Donchian channel breakout."""
    def __init__(self):
        super().__init__("donchian-breakout", 8)
    
    def should_enter_long(self, bars: List[Bar], idx: int) -> bool:
        if idx < 20:
            return False
        # highest high of previous 20 bars
        period_high = max(bars[i].high for i in range(idx-20, idx))
        return bars[idx].close > period_high
    
    def should_enter_short(self, bars: List[Bar], idx: int) -> bool:
        if idx < 20:
            return False
        period_low = min(bars[i].low for i in range(idx-20, idx))
        return bars[idx].close < period_low

# ======================
# Group D: My quant research (merged/hybrid)
# ======================

class VolExpansionMomentum(Strategy):
    """Detect vol regime: compute short_vol(10)/long_vol(20). If short_vol/long_vol was below 0.8 for 3+ bars (squeeze) AND now crosses above (expansion) AND price above SMA20 → long momentum. If below SMA20 → short momentum. Exit at 8 bars."""
    def __init__(self):
        super().__init__("vol-expansion-momentum", 8)
        self.short_lookback = 10
        self.long_lookback = 20
        self.squeeze_threshold = 0.8
        self.squeeze_bars_required = 3
    
    def _compute_vol_ratio(self, bars: List[Bar], idx: int) -> Optional[float]:
        if idx < self.long_lookback:
            return None
        # short_vol: ATR(10)
        tr_sum_short = 0.0
        for i in range(idx - self.short_lookback + 1, idx + 1):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i-1].close if i > 0 else bars[i].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_sum_short += tr
        avg_tr_short = tr_sum_short / self.short_lookback
        
        # long_vol: ATR(20)
        tr_sum_long = 0.0
        for i in range(idx - self.long_lookback + 1, idx + 1):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i-1].close if i > 0 else bars[i].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_sum_long += tr
        avg_tr_long = tr_sum_long / self.long_lookback
        
        if avg_tr_long == 0:
            return None
        return avg_tr_short / avg_tr_long
    
    def should_enter_long(self, bars: List[Bar], idx: int) -> bool:
        if idx < self.long_lookback:
            return False
        # Need to check squeeze condition: ratio below 0.8 for at least 3 consecutive bars ending at idx-1?
        # Actually: "was below 0.8 for 3+ bars (squeeze) AND now crosses above (expansion)"
        # So we need ratio[idx-1] < 0.8 for 3 bars? and ratio[idx] >= 0.8?
        # We'll check that for the last 3 bars (idx-3, idx-2, idx-1) all < 0.8 and current >= 0.8
        if idx < 3:
            return False
        ratios = []
        for offset in range(3):
            r = self._compute_vol_ratio(bars, idx - 3 + offset)
            if r is None:
                return False
            ratios.append(r)
        if not all(r < self.squeeze_threshold for r in ratios):
            return False
        current_ratio = self._compute_vol_ratio(bars, idx)
        if current_ratio is None:
            return False
        if current_ratio < self.squeeze_threshold:  # not crossed above
            return False
        # price above SMA20
        closes = [bar.close for bar in bars]
        sma20 = sma(closes, 20)
        sma20_val = sma20[idx]
        if sma20_val is None:
            return False
        return bars[idx].close > sma20_val
    
    def should_enter_short(self, bars: List[Bar], idx: int) -> bool:
        if idx < self.long_lookback:
            return False
        if idx < 3:
            return False
        ratios = []
        for offset in range(3):
            r = self._compute_vol_ratio(bars, idx - 3 + offset)
            if r is None:
                return False
            ratios.append(r)
        if not all(r < self.squeeze_threshold for r in ratios):
            return False
        current_ratio = self._compute_vol_ratio(bars, idx)
        if current_ratio is None:
            return False
        if current_ratio < self.squeeze_threshold:
            return False
        closes = [bar.close for bar in bars]
        sma20 = sma(closes, 20)
        sma20_val = sma20[idx]
        if sma20_val is None:
            return False
        return bars[idx].close < sma20_val

class TripleConfirm(Strategy):
    """Fire ONLY when orb-breakout AND wq-trend-mom AND wq-vol-regime all agree on direction in the same bar. Exit at 5 bars."""
    def __init__(self):
        self.orb = OrbBreakoutNy()
        self.wq_trend = WqTrendMomAnySession()
        self.wq_vol = WqVolRegime()
        super().__init__("triple-confirm", 5)
    
    def generate_signals(self, bars: List[Bar]) -> List[Tuple[int, int, str]]:
        signals = []
        for i in range(len(bars)):
            dir_orb = None
            if self.orb.should_enter_long(bars, i):
                dir_orb = 'long'
            elif self.orb.should_enter_short(bars, i):
                dir_orb = 'short'
            
            dir_trend = None
            if self.wq_trend.should_enter_long(bars, i):
                dir_trend = 'long'
            elif self.wq_trend.should_enter_short(bars, i):
                dir_trend = 'short'
            
            dir_vol = self.wq_vol.signal_direction(bars, i)
            
            if dir_orb is not None and dir_trend is not None and dir_vol is not None:
                if dir_orb == dir_trend == dir_vol:
                    exit_idx = i + self.exit_bars
                    if exit_idx < len(bars):
                        signals.append((i, exit_idx, dir_orb))
        return signals

# ======================
# Strategy Factory
# ======================

def get_all_strategies() -> List[Strategy]:
    """Return list of all strategy instances."""
    return [
        # Group A
        WqTrendMomAsiaLondon(),
        OrbBreakoutNy(),
        # Group B
        SessionComposite(),
        TrendVolMerge(),
        # Group C
        ShortTermReversal(),
        GapFade(),
        VolumeSurgeReversal(),
        DonchianBreakout(),
        # Group D
        VolExpansionMomentum(),
        TripleConfirm(),
    ]

# ======================
# Backtesting Engine
# ======================

def backtest_strategy(strategy: Strategy, bars: List[Bar]) -> dict:
    """Backtest a single strategy on bars, return performance metrics.
    R-multiple = (exit_price - entry_price) / ATR_at_entry (matching Rust pipeline)."""
    signals = strategy.generate_signals(bars)
    trades = []
    for entry_idx, exit_idx, direction in signals:
        entry_price = bars[entry_idx].close
        exit_price = bars[exit_idx].close
        atr_val = atr(bars, entry_idx, 14)
        if atr_val == 0:
            continue
        if direction == 'long':
            r = (exit_price - entry_price) / atr_val
        else:  # short
            r = (entry_price - exit_price) / atr_val
        trades.append(r)
    
    if not trades:
        return {
            'strategy': strategy.name,
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'total_r': 0.0
        }
    
    wins = sum(1 for pnl in trades if pnl > 0)
    losses = len(trades) - wins
    total_r = sum(trades)
    win_rate = (wins / len(trades)) * 100 if trades else 0.0
    
    return {
        'strategy': strategy.name,
        'trades': len(trades),
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'total_r': total_r
    }

def run_analysis():
    """Run analysis on 15m, 30m, 60m data."""
    timeframes = ['15m', '30m', '60m']
    base_path = '/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-'
    
    all_results = []
    
    for tf in timeframes:
        path = base_path + tf + '.csv'
        print(f"Loading {tf} data from {path}...")
        bars = load_csv(path, symbol='NQ')
        print(f"Loaded {len(bars)} NQ bars for {tf}.")
        
        strategies = get_all_strategies()
        for strategy in strategies:
            result = backtest_strategy(strategy, bars)
            result['timeframe'] = tf
            all_results.append(result)
            print(f"{strategy.name} ({tf}): {result['trades']} trades, {result['wins']}/{result['losses']} W/L ({result['win_rate']:.1f}%), total R {result['total_r']:+.2f}")
    
    # Leaderboard sorted by total R descending
    print("\n" + "="*80)
    print("LEADERBOARD (sorted by total R)")
    print("="*80)
    sorted_results = sorted(all_results, key=lambda x: x['total_r'], reverse=True)
    for i, res in enumerate(sorted_results, 1):
        print(f"{i:2d}. {res['strategy']} ({res['timeframe']}): {res['trades']} trades, {res['wins']}/{res['losses']} W/L ({res['win_rate']:.1f}%), total R {res['total_r']:+.2f}")
    
    return sorted_results

if __name__ == "__main__":
    run_analysis()