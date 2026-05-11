pub mod backtest;
pub mod gold_strategies;
pub mod indicators;
pub mod pm_strategies;
pub mod strategy;
pub mod types;

use types::{Bar, Signal};

/// Generate signals for a symbol's bars using registered strategies.
/// Takes &[&Bar] — no cloning needed.
pub fn generate_signals(symbol: &str, bar_refs: &[&Bar]) -> Vec<(usize, Signal)> {
    let mut signals = Vec::new();

    for i in 20..bar_refs.len() {
        let window = &bar_refs[..=i];

        if let Some(signal) = strategy::wq_alpha_009(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = strategy::wq_alpha_012(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = strategy::wq_alpha_001(symbol, window) {
            signals.push((i, signal));
        }

        // Gold strategies
        if let Some(signal) = gold_strategies::lw_donchian_breakout(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::gapper_edge(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::order_flow_80_20(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::polymarket_edge_detector(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::strategy_degradation_detector(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::drawdown_based_sizer(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::volume_reversal(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::opening_range_breakout(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::volume_imbalance_signal(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::weekly_nasdaq_strategy(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::wq_momentum_reversal(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::wq_volatility_regime(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::wq_trend_momentum(symbol, window) {
            signals.push((i, signal));
        }
        if let Some(signal) = gold_strategies::vgrsi_strategy(symbol, window) {
            signals.push((i, signal));
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
