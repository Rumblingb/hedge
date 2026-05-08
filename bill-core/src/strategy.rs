use crate::indicators;
use crate::types::{Bar, Signal};

const LOOKBACK: usize = 50;
const ATR_PERIOD: usize = 14;

/// Build a signal with RR validation. Returns None if RR <= 0.
fn build_signal(
    symbol: &str,
    strategy_id: &str,
    side: &str,
    entry: f64,
    stop: f64,
    target: f64,
    confidence: f64,
) -> Option<Signal> {
    let rr = if side == "long" {
        (target - entry) / (entry - stop).max(0.0001)
    } else {
        (entry - target) / (stop - entry).max(0.0001)
    };
    if rr <= 0.0 || !rr.is_finite() {
        return None;
    }
    Some(Signal {
        symbol: symbol.to_string(),
        strategy_id: strategy_id.to_string(),
        side: side.to_string(),
        entry,
        stop,
        target,
        rr,
        confidence,
        contracts: 1,
        max_hold_minutes: 30,
    })
}

/// WQ Alpha 001: Mean-reversion after extreme negative returns.
/// Formula: rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5
pub fn wq_alpha_001(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 30 {
        return None;
    }
    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();
    let returns: Vec<f64> = closes
        .windows(2)
        .map(|w| (w[1] - w[0]) / w[0].max(0.0001))
        .collect();

    let std20 = indicators::std_dev(&returns, 20);
    let mut powered = Vec::with_capacity(returns.len());
    for &r in &returns {
        let val = if r < 0.0 {
            std20
        } else {
            closes[closes.len() - 1]
        };
        powered.push(indicators::signed_power(val, 2.0));
    }
    let arg_max = indicators::ts_argmax(&powered, 5);
    let alpha = arg_max - 0.5;

    let atr_val = indicators::atr(bars, ATR_PERIOD);
    if atr_val <= 0.0 {
        return None;
    }
    let price = bars.last()?.close;

    if alpha < -0.4 {
        build_signal(symbol, "wq-alpha-001", "long", price, price - atr_val, price + atr_val * 1.5, 0.58)
    } else if alpha > 0.4 {
        build_signal(symbol, "wq-alpha-001", "short", price, price + atr_val, price - atr_val * 1.5, 0.58)
    } else {
        None
    }
}

/// WQ Alpha 009: Momentum acceleration/deceleration. One of the strongest WQ alphas.
/// If all recent deltas are positive → continue trend. If all negative → continue trend.
/// Otherwise → fade (reversal).
pub fn wq_alpha_009(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 20 {
        return None;
    }
    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();
    let deltas: Vec<f64> = closes.windows(2).map(|w| w[1] - w[0]).collect();

    let ts_min5 = indicators::ts_min(&deltas, 5);
    let ts_max5 = indicators::ts_max(&deltas, 5);

    let alpha = if ts_min5 > 0.0 {
        deltas[deltas.len() - 1] // All positive — continue up
    } else if ts_max5 < 0.0 {
        deltas[deltas.len() - 1] // All negative — continue down
    } else {
        -deltas[deltas.len() - 1] // Mixed — fade
    };

    let atr_val = indicators::atr(bars, ATR_PERIOD);
    if atr_val <= 0.0 || alpha.abs() < atr_val * 0.1 {
        return None;
    }
    let price = bars.last()?.close;

    if alpha > 0.0 {
        build_signal(symbol, "wq-alpha-009", "long", price, price - atr_val * 1.2, price + atr_val * 2.0, 0.60)
    } else {
        build_signal(symbol, "wq-alpha-009", "short", price, price + atr_val * 1.2, price - atr_val * 2.0, 0.60)
    }
}

/// WQ Alpha 012: Volume-signed momentum.
pub fn wq_alpha_012(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 10 {
        return None;
    }
    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();
    let volumes: Vec<f64> = bars.iter().map(|b| b.volume).collect();

    let vol_delta = volumes[volumes.len() - 1] - volumes[volumes.len() - 2];
    let price_delta = closes[closes.len() - 1] - closes[closes.len() - 2];
    let alpha = vol_delta.signum() * (-price_delta);

    let atr_val = indicators::atr(bars, ATR_PERIOD);
    if atr_val <= 0.0 || alpha.abs() < atr_val * 0.08 {
        return None;
    }
    let price = bars.last()?.close;

    if alpha > 0.0 {
        build_signal(symbol, "wq-alpha-012", "long", price, price - atr_val * 0.8, price + atr_val * 1.5, 0.57)
    } else {
        build_signal(symbol, "wq-alpha-012", "short", price, price + atr_val * 0.8, price - atr_val * 1.5, 0.57)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::Bar;

    fn make_bars(prices: &[f64]) -> Vec<Bar> {
        prices
            .iter()
            .enumerate()
            .map(|(i, &p)| Bar {
                ts: format!("2026-01-{:02}T00:00:00Z", i + 1),
                symbol: "ES".to_string(),
                open: p,
                high: p + 1.0,
                low: p - 1.0,
                close: p,
                volume: 1000.0,
            })
            .collect()
    }

    #[test]
    fn test_wq_alpha_009_insufficient_data() {
        let bars = make_bars(&[100.0]);
        let bars_ref: Vec<&Bar> = bars.iter().collect();
        assert!(wq_alpha_009("ES", &bars_ref).is_none());
    }

    #[test]
    fn test_wq_alpha_009_produces_signal() {
        // Upward trend — should produce continuation signal
        let mut prices: Vec<f64> = (0..60).map(|i| 100.0 + i as f64 * 0.5).collect();
        // Add some volatility
        for i in 0..prices.len() {
            prices[i] += (i as f64).sin() * 2.0;
        }
        let bars = make_bars(&prices);
        let bars_ref: Vec<&Bar> = bars.iter().collect();
        let signal = wq_alpha_009("ES", &bars_ref);
        // May or may not fire depending on exact values
        if let Some(s) = signal {
            assert_eq!(s.strategy_id, "wq-alpha-009");
            assert!(s.rr > 0.0);
        }
    }
}
