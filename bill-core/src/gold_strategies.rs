use crate::types::{Bar, Signal};

/// Gold Strategy: Larry Williams Donchian Breakout (window=20)
/// Entry when price breaks above/below 20-bar Donchian channel.
pub fn lw_donchian_breakout(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 20 { return None; }
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
    if stop_dist <= 0.0 { return None; }
    
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
    if bars.len() < 3 { return None; }
    let i = bars.len() - 1;
    let bar = bars[i];
    
    let gap = (bar.open - bars[i - 1].close) / bars[i - 1].close;
    if gap.abs() > 0.02 {
        let entry = bar.open;
        let atr_val: f64 = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 { return None; }
        
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

// === PHANTOM STRATEGY STUBS ===
// These 10 strategies were referenced in lib.rs but never implemented.
// They are registered for completeness and return None (no signals).

pub fn wq_trend_momentum(_symbol: &str, _bars: &[&Bar]) -> Option<Signal> { None }
pub fn wq_volatility_regime(_symbol: &str, _bars: &[&Bar]) -> Option<Signal> { None }
pub fn vgrsi_strategy(_symbol: &str, _bars: &[&Bar]) -> Option<Signal> { None }
pub fn wq_momentum_reversal(_symbol: &str, _bars: &[&Bar]) -> Option<Signal> { None }
pub fn volume_imbalance_signal(_symbol: &str, _bars: &[&Bar]) -> Option<Signal> { None }
pub fn opening_range_breakout(_symbol: &str, _bars: &[&Bar]) -> Option<Signal> { None }
pub fn volume_reversal(_symbol: &str, _bars: &[&Bar]) -> Option<Signal> { None }
pub fn weekly_nasdaq_strategy(_symbol: &str, _bars: &[&Bar]) -> Option<Signal> { None }
pub fn drawdown_based_sizer(_symbol: &str, _bars: &[&Bar]) -> Option<Signal> { None }
pub fn strategy_degradation_detector(_symbol: &str, _bars: &[&Bar]) -> Option<Signal> { None }
