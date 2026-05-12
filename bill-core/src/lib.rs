pub mod backtest;
pub mod cot_filter;
pub mod gold_strategies;
pub mod indicators;
pub mod pm_strategies;
pub mod portfolio;
pub mod strategy;
pub mod types;

use types::{Bar, Signal};

/// Generate signals for a symbol's bars using registered strategies.
/// Takes &[&Bar] — no cloning needed.
/// Selects at most 1 signal per bar (highest confidence wins) to prevent
/// strategy pile-up that causes negative total R despite positive per-strategy edge.
/// Consolidated signal generation using a single static slice.
/// The slice `ALL_STRATEGIES` contains every strategy together with a flag
/// indicating whether it is a high‑priority WQ alpha. The loop iterates once
/// over this slice, short‑circuiting on the first matching WQ alpha and otherwise
/// selecting the best‑confidence gold strategy.
pub static ALL_STRATEGIES: &[(&'static str, fn(&str, &[&Bar]) -> Option<Signal>, bool)] = &[
    // (name, runner, is_wq_alpha)
    ("wq_alpha_009", strategy::wq_alpha_009, true),
    ("wq_alpha_001", strategy::wq_alpha_001, true),
    ("wq_alpha_012", strategy::wq_alpha_012, true),
    // Gold strategies (lower priority)
    ("wq_trend_momentum", gold_strategies::wq_trend_momentum, false),
    ("wq_volatility_regime", gold_strategies::wq_volatility_regime, false),
    ("vgrsi_strategy", gold_strategies::vgrsi_strategy, false),
    ("wq_momentum_reversal", gold_strategies::wq_momentum_reversal, false),
    ("volume_imbalance_signal", gold_strategies::volume_imbalance_signal, false),
    ("opening_range_breakout", gold_strategies::opening_range_breakout, false),
    ("volume_reversal", gold_strategies::volume_reversal, false),
    ("weekly_nasdaq_strategy", gold_strategies::weekly_nasdaq_strategy, false),
    ("drawdown_based_sizer", gold_strategies::drawdown_based_sizer, false),
    ("strategy_degradation_detector", gold_strategies::strategy_degradation_detector, false),
    ("order_flow_80_20", gold_strategies::order_flow_80_20, false),
    ("gapper_edge", gold_strategies::gapper_edge, false),
    ("polymarket_edge_detector", gold_strategies::polymarket_edge_detector, false),
    ("lw_donchian_breakout", gold_strategies::lw_donchian_breakout, false),
];

pub fn generate_signals(symbol: &str, bar_refs: &[&Bar]) -> Vec<(usize, Signal)> {
    let mut signals = Vec::new();
    for i in 20..bar_refs.len() {
        let window = &bar_refs[..=i];
        let mut best_signal: Option<Signal> = None;
        let mut best_confidence = 0.0;
        for &(_, runner, is_wq) in ALL_STRATEGIES {
            if let Some(sig) = runner(symbol, window) {
                if is_wq {
                    // High‑priority WQ alphas win immediately.
                    best_signal = Some(sig);
                    break;
                } else if sig.confidence > best_confidence {
                    best_confidence = sig.confidence;
                    best_signal = Some(sig);
                }
            }
        }
        if let Some(sig) = best_signal {
            signals.push((i, sig));
        }
    }
    signals
}

/// Full pipeline: load CSV → generate signals → run backtest
pub fn run_pipeline(csv_path: &str, max_bars: Option<usize>) -> anyhow::Result<types::BacktestResult> {
    let all_bars = types::load_bars_csv(csv_path)?;
    let grouped = types::group_by_symbol(&all_bars);

    let mut all_signals: Vec<(usize, Signal)> = Vec::new();

    for (symbol, bars) in &grouped {
        let limit = max_bars.unwrap_or(bars.len()).min(bars.len());
        let window = &bars[..limit];
        let signals = generate_signals(symbol, window);
        all_signals.extend(signals);
    }

    all_signals.sort_by_key(|(idx, _)| *idx);
    Ok(backtest::run_backtest(&all_signals, &all_bars, 30))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_pipeline() {
        let result = generate_signals("ES", &[]);
        assert!(result.is_empty());
    }
}
