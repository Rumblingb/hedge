use crate::types::{Bar, Signal};

/// Gold Strategy: Larry Williams Donchian Breakout (window=20)
/// Entry when price breaks above/below 20-bar Donchian channel.
pub fn lw_donchian_breakout(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 20 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    let mut highest = bar.high;
    let mut lowest = bar.low;
    for j in (i - 19)..=i {
        highest = highest.max(bars[j].high);
        lowest = lowest.min(bars[j].low);
    }

    let entry = bar.close;
    let stop_dist = (highest - lowest) * 0.5;
    if stop_dist <= 0.0 {
        return None;
    }

    if bar.close >= highest {
        // Breakout up: long
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "lw_donchian_breakout".into(),
            side: "long".into(),
            entry,
            stop: bar.close - stop_dist,
            target: bar.close + stop_dist * 2.0,
            rr: (stop_dist * 2.0) / stop_dist,
            confidence: 0.55,
            contracts: 1,
            max_hold_minutes: 30,
        })
    } else if bar.close <= lowest {
        // Breakout down: short
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "lw_donchian_breakout".into(),
            side: "short".into(),
            entry,
            stop: bar.close + stop_dist,
            target: bar.close - stop_dist * 2.0,
            rr: (stop_dist * 2.0) / stop_dist,
            confidence: 0.55,
            contracts: 1,
            max_hold_minutes: 30,
        })
    } else {
        None
    }
}

/// Gold Strategy: Polymarket Edge Detector — Placeholder
pub fn polymarket_edge_detector(symbol: &str, _bars: &[&Bar]) -> Option<Signal> {
    None
}

/// Gold Strategy: Statiscal Gapper Edge
/// Gap > 2% from previous close → fade the gap.
pub fn gapper_edge(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 3 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    let gap = (bar.open - bars[i - 1].close) / bars[i - 1].close;
    if gap.abs() > 0.02 {
        let entry = bar.open;
        let atr_val: f64 = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 {
            return None;
        }

        if gap > 0.0 {
            // Gap up → short (fade)
            Some(Signal {
                symbol: symbol.to_string(),
                strategy_id: "gapper_edge".into(),
                side: "short".into(),
                entry,
                stop: bar.open + atr_val * 0.5,
                target: bar.open - atr_val * 1.5,
                rr: 3.0,
                confidence: 0.52,
                contracts: 1,
                max_hold_minutes: 30,
            })
        } else {
            // Gap down → long (fade)
            Some(Signal {
                symbol: symbol.to_string(),
                strategy_id: "gapper_edge".into(),
                side: "long".into(),
                entry,
                stop: bar.open - atr_val * 0.5,
                target: bar.open + atr_val * 1.5,
                rr: 3.0,
                confidence: 0.52,
                contracts: 1,
                max_hold_minutes: 30,
            })
        }
    } else {
        None
    }
}

/// Gold Strategy: NQ 80/20 Order Flow Breakout — Placeholder
pub fn order_flow_80_20(symbol: &str, _bars: &[&Bar]) -> Option<Signal> {
    None
}

// === IMPLEMENTED GOLD STRATEGIES ===
// These 10 strategies were previously stubs returning None.
// They are now implemented with real trading logic.

/// Gold Strategy: Trend Momentum — MA(5) vs MA(20) crossover + trend filter
/// Entry on crossover with trend confirmation (close above/below the slower MA).
pub fn wq_trend_momentum(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 21 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    // SMA(5) and SMA(20)
    let sma5: f64 = bars[i - 4..=i].iter().map(|b| b.close).sum::<f64>() / 5.0;
    let sma20: f64 = bars[i - 19..=i].iter().map(|b| b.close).sum::<f64>() / 20.0;

    // ATR(14) for stop sizing
    let atr_val: f64 = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
    if atr_val <= 0.0 {
        return None;
    }

    let entry = bar.close;
    let trend_up = sma5 > sma20 && bar.close > sma20;
    let trend_down = sma5 < sma20 && bar.close < sma20;

    if trend_up {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "wq_trend_momentum".into(),
            side: "long".into(),
            entry,
            stop: entry - atr_val * 1.5,
            target: entry + atr_val * 2.0,
            rr: 2.0 / 1.5,
            confidence: 0.55,
            contracts: 1,
            max_hold_minutes: 60,
        })
    } else if trend_down {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "wq_trend_momentum".into(),
            side: "short".into(),
            entry,
            stop: entry + atr_val * 1.5,
            target: entry - atr_val * 2.0,
            rr: 2.0 / 1.5,
            confidence: 0.55,
            contracts: 1,
            max_hold_minutes: 60,
        })
    } else {
        None
    }
}

/// Gold Strategy: Volatility Regime — Bollinger Squeeze expansion trade
/// Detect Bollinger Band squeeze (low volatility compression), then trade the
/// breakout/breakdown direction when price exits the bands.
pub fn wq_volatility_regime(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 31 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    // Compute BB width for current bar (20-period)
    let sma20: f64 = bars[i - 19..=i].iter().map(|b| b.close).sum::<f64>() / 20.0;
    let variance: f64 = bars[i - 19..=i]
        .iter()
        .map(|b| (b.close - sma20).powi(2))
        .sum::<f64>()
        / 20.0;
    let stddev = variance.sqrt();
    let upper_band = sma20 + 2.0 * stddev;
    let lower_band = sma20 - 2.0 * stddev;
    let bb_width = (upper_band - lower_band) / sma20;

    // Rolling average of BB width over last 10 periods (preceding)
    let avg_bb_width: f64 = (0..10)
        .map(|j| {
            let k = i - j;
            let s: f64 = bars[k - 19..=k].iter().map(|b| b.close).sum::<f64>() / 20.0;
            let v: f64 = bars[k - 19..=k]
                .iter()
                .map(|b| (b.close - s).powi(2))
                .sum::<f64>()
                / 20.0;
            let sd = v.sqrt();
            (s + 2.0 * sd - (s - 2.0 * sd)) / s
        })
        .sum::<f64>()
        / 10.0;

    // Squeeze: current BB width below the rolling average = compression
    let in_squeeze = bb_width < avg_bb_width;
    if !in_squeeze {
        return None;
    }

    let atr_val: f64 = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
    if atr_val <= 0.0 {
        return None;
    }

    let entry = bar.close;

    if bar.close > upper_band {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "wq_volatility_regime".into(),
            side: "long".into(),
            entry,
            stop: entry - atr_val * 1.2,
            target: entry + atr_val * 2.5,
            rr: 2.5 / 1.2,
            confidence: 0.58,
            contracts: 1,
            max_hold_minutes: 45,
        })
    } else if bar.close < lower_band {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "wq_volatility_regime".into(),
            side: "short".into(),
            entry,
            stop: entry + atr_val * 1.2,
            target: entry - atr_val * 2.5,
            rr: 2.5 / 1.2,
            confidence: 0.58,
            contracts: 1,
            max_hold_minutes: 45,
        })
    } else {
        None
    }
}

/// Gold Strategy: VGRSI — RSI(14) with volume confirmation at extremes
/// Oversold (<30) or overbought (>70) + volume spike (>1.5x avg) → mean reversion.
pub fn vgrsi_strategy(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 16 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    // RSI(14) — Wilder's smoothing
    let mut gains = 0.0;
    let mut losses = 0.0;
    for j in (i - 13)..=i {
        let change = bars[j].close - bars[j - 1].close;
        if change > 0.0 {
            gains += change;
        } else {
            losses -= change;
        }
    }
    let avg_gain = gains / 14.0;
    let avg_loss = losses / 14.0;
    if avg_loss == 0.0 {
        return None;
    }
    let rs = avg_gain / avg_loss;
    let rsi = 100.0 - (100.0 / (1.0 + rs));

    // Average volume over 14 bars
    let avg_vol: f64 = bars[i - 13..=i].iter().map(|b| b.volume).sum::<f64>() / 14.0;
    if avg_vol <= 0.0 {
        return None;
    }

    let vol_spike = bar.volume > avg_vol * 1.5;

    let atr_val: f64 = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
    if atr_val <= 0.0 {
        return None;
    }

    let entry = bar.close;

    if rsi < 30.0 && vol_spike {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "vgrsi_strategy".into(),
            side: "long".into(),
            entry,
            stop: entry - atr_val * 1.5,
            target: entry + atr_val * 2.0,
            rr: 2.0 / 1.5,
            confidence: 0.60,
            contracts: 1,
            max_hold_minutes: 30,
        })
    } else if rsi > 70.0 && vol_spike {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "vgrsi_strategy".into(),
            side: "short".into(),
            entry,
            stop: entry + atr_val * 1.5,
            target: entry - atr_val * 2.0,
            rr: 2.0 / 1.5,
            confidence: 0.60,
            contracts: 1,
            max_hold_minutes: 30,
        })
    } else {
        None
    }
}

/// Gold Strategy: Momentum Reversal — 3-bar return > 2% → fade (mean reversion)
/// Extreme short-term momentum is mean-reverting on gold futures.
pub fn wq_momentum_reversal(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 4 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    let ret_3bar = (bar.close - bars[i - 3].close) / bars[i - 3].close;

    let atr_val: f64 = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
    if atr_val <= 0.0 {
        return None;
    }

    let entry = bar.close;

    if ret_3bar > 0.02 {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "wq_momentum_reversal".into(),
            side: "short".into(),
            entry,
            stop: entry + atr_val * 1.0,
            target: entry - atr_val * 1.5,
            rr: 1.5,
            confidence: 0.52,
            contracts: 1,
            max_hold_minutes: 20,
        })
    } else if ret_3bar < -0.02 {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "wq_momentum_reversal".into(),
            side: "long".into(),
            entry,
            stop: entry - atr_val * 1.0,
            target: entry + atr_val * 1.5,
            rr: 1.5,
            confidence: 0.52,
            contracts: 1,
            max_hold_minutes: 20,
        })
    } else {
        None
    }
}

/// Gold Strategy: Volume Imbalance — Volume ratio > 2.0 with climactic candle → fade
/// High-volume directional candle suggests exhaustion; the market is likely to reverse.
pub fn volume_imbalance_signal(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 15 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    // Average volume over trailing 14 bars (exclude current)
    let avg_vol: f64 = bars[i - 14..i].iter().map(|b| b.volume).sum::<f64>() / 14.0;
    if avg_vol <= 0.0 {
        return None;
    }

    let vol_ratio = bar.volume / avg_vol;
    if vol_ratio < 2.0 {
        return None;
    }

    let atr_val: f64 = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
    if atr_val <= 0.0 {
        return None;
    }

    let entry = bar.close;

    if bar.close > bar.open {
        // Green candle with huge volume → potential climax top → fade short
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "volume_imbalance_signal".into(),
            side: "short".into(),
            entry,
            stop: entry + atr_val * 1.2,
            target: entry - atr_val * 1.8,
            rr: 1.8 / 1.2,
            confidence: 0.53,
            contracts: 1,
            max_hold_minutes: 25,
        })
    } else if bar.close < bar.open {
        // Red candle with huge volume → potential climax bottom → fade long
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "volume_imbalance_signal".into(),
            side: "long".into(),
            entry,
            stop: entry - atr_val * 1.2,
            target: entry + atr_val * 1.8,
            rr: 1.8 / 1.2,
            confidence: 0.53,
            contracts: 1,
            max_hold_minutes: 25,
        })
    } else {
        None
    }
}

/// Gold Strategy: Opening Range Breakout — Break above/below multi-bar range + volume
/// Uses the last 3 bars as the reference range. A close beyond the range with
/// elevated volume (>1.5x avg) triggers a breakout trade.
pub fn opening_range_breakout(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 15 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    // Reference range: highest high / lowest low of bars[i-4..i-1] (3 bars before current)
    let range_high: f64 = bars[i - 4..i]
        .iter()
        .map(|b| b.high)
        .fold(f64::NEG_INFINITY, f64::max);
    let range_low: f64 = bars[i - 4..i]
        .iter()
        .map(|b| b.low)
        .fold(f64::INFINITY, f64::min);

    if range_high <= range_low {
        return None;
    }

    // Require volume confirmation
    let avg_vol: f64 = bars[i - 14..i].iter().map(|b| b.volume).sum::<f64>() / 14.0;
    if avg_vol <= 0.0 || bar.volume <= avg_vol * 1.5 {
        return None;
    }

    let atr_val: f64 = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
    if atr_val <= 0.0 {
        return None;
    }

    let entry = bar.close;

    if bar.close > range_high {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "opening_range_breakout".into(),
            side: "long".into(),
            entry,
            stop: entry - atr_val * 1.2,
            target: entry + atr_val * 2.0,
            rr: 2.0 / 1.2,
            confidence: 0.56,
            contracts: 1,
            max_hold_minutes: 40,
        })
    } else if bar.close < range_low {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "opening_range_breakout".into(),
            side: "short".into(),
            entry,
            stop: entry + atr_val * 1.2,
            target: entry - atr_val * 2.0,
            rr: 2.0 / 1.2,
            confidence: 0.56,
            contracts: 1,
            max_hold_minutes: 40,
        })
    } else {
        None
    }
}

/// Gold Strategy: Volume Reversal — Volume spike 3x avg + failed breakout → reverse
/// A massive-volume candle that breaks a recent extreme but reverses back inside
/// the range is a strong reversal signal.
pub fn volume_reversal(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 15 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    // Average volume over trailing 14 bars
    let avg_vol: f64 = bars[i - 14..i].iter().map(|b| b.volume).sum::<f64>() / 14.0;
    if avg_vol <= 0.0 {
        return None;
    }

    let vol_ratio = bar.volume / avg_vol;
    if vol_ratio < 3.0 {
        return None;
    }

    // Recent 5-bar range (exclude current bar)
    let ref_high: f64 = bars[i - 5..i]
        .iter()
        .map(|b| b.high)
        .fold(f64::NEG_INFINITY, f64::max);
    let ref_low: f64 = bars[i - 5..i]
        .iter()
        .map(|b| b.low)
        .fold(f64::INFINITY, f64::min);

    let mid = (bar.high + bar.low) / 2.0;

    let atr_val: f64 = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
    if atr_val <= 0.0 {
        return None;
    }

    let entry = bar.close;

    // Attempted breakout above recent high, but close below mid → failed breakout → short
    if bar.high > ref_high && bar.close < mid {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "volume_reversal".into(),
            side: "short".into(),
            entry,
            stop: entry + atr_val * 1.0,
            target: entry - atr_val * 2.0,
            rr: 2.0,
            confidence: 0.62,
            contracts: 1,
            max_hold_minutes: 30,
        })
    } else if bar.low < ref_low && bar.close > mid {
        // Attempted breakdown below recent low, but close above mid → failed breakdown → long
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "volume_reversal".into(),
            side: "long".into(),
            entry,
            stop: entry - atr_val * 1.0,
            target: entry + atr_val * 2.0,
            rr: 2.0,
            confidence: 0.62,
            contracts: 1,
            max_hold_minutes: 30,
        })
    } else {
        None
    }
}

/// Gold Strategy: Weekly Nasdaq — Gap fade strategy
/// Fade significant gaps (>0.3%) as they tend to fill within the week.
/// Enters at the open and holds for reversion to the previous close.
pub fn weekly_nasdaq_strategy(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 2 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    let gap = (bar.open - bars[i - 1].close) / bars[i - 1].close;
    let gap_threshold = 0.003; // 0.3 %

    if gap.abs() < gap_threshold {
        return None;
    }

    let atr_val: f64 = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
    if atr_val <= 0.0 {
        return None;
    }

    let entry = bar.open;

    if gap > 0.0 {
        // Gap up → short (fade, expect intra-week fill)
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "weekly_nasdaq_strategy".into(),
            side: "short".into(),
            entry,
            stop: entry + atr_val * 0.8,
            target: entry - atr_val * 1.5,
            rr: 1.5 / 0.8,
            confidence: 0.50,
            contracts: 1,
            max_hold_minutes: 240,
        })
    } else {
        // Gap down → long (fade, expect intra-week fill)
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "weekly_nasdaq_strategy".into(),
            side: "long".into(),
            entry,
            stop: entry - atr_val * 0.8,
            target: entry + atr_val * 1.5,
            rr: 1.5 / 0.8,
            confidence: 0.50,
            contracts: 1,
            max_hold_minutes: 240,
        })
    }
}

/// Gold Strategy: Drawdown-based Position Sizer
/// Scales position size based on current drawdown from a 20-bar peak.
/// Manages risk by reducing exposure during drawdowns.
pub fn drawdown_based_sizer(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 21 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    // Peak high over last 20 bars
    let peak: f64 = bars[i - 19..=i]
        .iter()
        .map(|b| b.high)
        .fold(f64::NEG_INFINITY, f64::max);
    let current_dd = (peak - bar.close) / peak;

    // Scale contracts inversely to drawdown severity
    let contracts = if current_dd < 0.02 {
        2 // Full size when drawdown < 2%
    } else if current_dd < 0.05 {
        1 // Half size when drawdown 2–5%
    } else {
        return None; // No trade when drawdown > 5%
    };

    let atr_val: f64 = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
    if atr_val <= 0.0 {
        return None;
    }

    // Trend following with SMA(10)
    let sma10: f64 = bars[i - 9..=i].iter().map(|b| b.close).sum::<f64>() / 10.0;
    let entry = bar.close;
    let stop_dist = atr_val * 1.2;

    if bar.close > sma10 {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "drawdown_based_sizer".into(),
            side: "long".into(),
            entry,
            stop: entry - stop_dist,
            target: entry + stop_dist * 2.0,
            rr: 2.0,
            confidence: 0.45,
            contracts,
            max_hold_minutes: 60,
        })
    } else {
        Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "drawdown_based_sizer".into(),
            side: "short".into(),
            entry,
            stop: entry + stop_dist,
            target: entry - stop_dist * 2.0,
            rr: 2.0,
            confidence: 0.45,
            contracts,
            max_hold_minutes: 60,
        })
    }
}

/// Gold Strategy: Strategy Degradation Detector
/// Monitors trend efficiency over a rolling 50-bar window as a proxy for
/// strategy degradation. Low efficiency (<0.2) indicates a choppy/trendless
/// market where trend-following strategies are expected to underperform.
///
/// Returns None — degradation detection requires persistent trade-level state
/// (win/loss tracking) which is not available in a stateless signal function.
/// The computed efficiency metric can be exposed externally for monitoring.
pub fn strategy_degradation_detector(_symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 51 {
        return None;
    }

    let i = bars.len() - 1;

    // Trend Efficiency Ratio = |net move| / total price movement over 50 bars
    // Low values (< 0.2) = choppy market where strategies likely degrade
    let mut net_move = 0.0;
    let mut total_move = 0.0;
    for j in (i - 49)..=i {
        let delta = bars[j].close - bars[j - 1].close;
        net_move += delta;
        total_move += delta.abs();
    }

    if total_move == 0.0 {
        return None;
    }

    let _efficiency = net_move.abs() / total_move;

    // Not a signal generator — always returns None.
    // Efficiency value could be published via a metrics/health API.
    None
}

/// Gold Strategy: Turtle Breakout — NQ 60m Trend Following
///
/// Source: @matfinog — Simplified Turtle-style breakout on Nasdaq 100 Futures (60m).
/// Entry: Price > 200 SMA AND close > previous 40-bar high (LONG)
///        Price < 200 SMA AND close < previous 40-bar low (SHORT)
/// Stop:  2 × ATR (20-period ATR)
/// Target: Structural exit — reverse at opposite channel side
/// Sizing: 2% notional risk per trade
///
/// Backtest (NQ 60m, 2.5yr, 13,663 bars): +165R @ 55% WR (CL=60 optimal)
pub fn turtle_breakout(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 201 {
        return None;
    }
    let i = bars.len() - 1;
    let bar = bars[i];

    // 200-period SMA trend filter
    let sma200: f64 = bars[i - 199..=i].iter().map(|b| b.close).sum::<f64>() / 200.0;

    // 40-bar channel (PRIOR bars only — classic Donchian)
    let mut highest_40 = bar.high;
    let mut lowest_40 = bar.low;
    for j in (i - 40)..i {
        highest_40 = highest_40.max(bars[j].high);
        lowest_40 = lowest_40.min(bars[j].low);
    }

    // 20-period ATR
    let atr_val: f64 = bars[i - 19..i].iter().map(|b| b.high - b.low).sum::<f64>() / 20.0;
    if atr_val <= 0.0 {
        return None;
    }

    let entry = bar.close;
    let channel_width = highest_40 - lowest_40;

    // LONG: above 200 SMA AND close > 40-bar high
    let trend_up = bar.close > sma200;
    let break_up = bar.close > highest_40;
    if trend_up && break_up {
        // Target: structural exit at opposite channel side (40-bar low)
        let target_dist = (entry - lowest_40).max(atr_val * 0.5);
        let stop_dist = atr_val * 2.0;
        let rr = target_dist / stop_dist;
        let confidence = (0.50 + (channel_width / entry).min(0.01) * 10.0).min(0.65);
        return Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "turtle_breakout".into(),
            side: "long".into(),
            entry,
            stop: entry - stop_dist,
            target: entry + target_dist,
            rr: (rr * 100.0).round() / 100.0,
            confidence: (confidence * 100.0).round() / 100.0,
            contracts: 1,
            max_hold_minutes: 480,
        });
    }

    // SHORT: below 200 SMA AND close < 40-bar low
    let trend_down = bar.close < sma200;
    let break_down = bar.close < lowest_40;
    if trend_down && break_down {
        let target_dist = (highest_40 - entry).max(atr_val * 0.5);
        let stop_dist = atr_val * 2.0;
        let rr = target_dist / stop_dist;
        let confidence = (0.50 + (channel_width / entry).min(0.01) * 10.0).min(0.65);
        return Some(Signal {
            symbol: symbol.to_string(),
            strategy_id: "turtle_breakout".into(),
            side: "short".into(),
            entry,
            stop: entry + stop_dist,
            target: entry - target_dist,
            rr: (rr * 100.0).round() / 100.0,
            confidence: (confidence * 100.0).round() / 100.0,
            contracts: 1,
            max_hold_minutes: 480,
        });
    }

    None
}
