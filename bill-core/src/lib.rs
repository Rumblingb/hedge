pub mod backtest;
pub mod gold_strategies;
pub mod indicators;
pub mod pm_strategies;
pub mod strategy;
pub mod types;

use types::{Bar, Signal};

/// Generate signals for a symbol's bars using registered strategies.
/// Takes &[&Bar] — no cloning needed.
/// Selects at most 1 signal per bar (highest confidence wins) to prevent
/// strategy pile-up that causes negative total R despite positive per-strategy edge.
pub fn generate_signals(symbol: &str, bar_refs: &[&Bar]) -> Vec<(usize, Signal)> {
    // Priority ordering: WQ alphas first (proven edge), then gold strategies
    let strategy_runners: Vec<fn(&str, &[&Bar]) -> Option<Signal>> = vec![
        // WQ alphas — highest priority, proven edge on both ES & NQ
        strategy::wq_alpha_009,
        strategy::wq_alpha_001,
        strategy::wq_alpha_012,
        // Gold strategies
        gold_strategies::wq_trend_momentum,
        gold_strategies::wq_volatility_regime,
        gold_strategies::vgrsi_strategy,
        gold_strategies::wq_momentum_reversal,
        gold_strategies::volume_imbalance_signal,
        gold_strategies::opening_range_breakout,
        gold_strategies::volume_reversal,
        gold_strategies::weekly_nasdaq_strategy,
        gold_strategies::drawdown_based_sizer,
        gold_strategies::strategy_degradation_detector,
        gold_strategies::order_flow_80_20,
        gold_strategies::gapper_edge,
        gold_strategies::polymarket_edge_detector,
        gold_strategies::lw_donchian_breakout,
    ];

    let mut signals: Vec<(usize, Signal)> = Vec::new();

    for i in 20..bar_refs.len() {
        let window = &bar_refs[..=i];

        // WQ alphas have proven edge on both ES and NQ (cross-market validation).
        // If any WQ alpha fires, it takes priority — no other strategy can override.
        if let Some(signal) = strategy::wq_alpha_009(symbol, window) {
            signals.push((i, signal));
            continue;
        }
        if let Some(signal) = strategy::wq_alpha_001(symbol, window) {
            signals.push((i, signal));
            continue;
        }
        if let Some(signal) = strategy::wq_alpha_012(symbol, window) {
            signals.push((i, signal));
            continue;
        }

        // Fallback: only when NO WQ alpha fires, pick the best non-WQ strategy
        let mut best_signal: Option<Signal> = None;
        let mut best_confidence = 0.0_f64;

        let fallback_runners: Vec<fn(&str, &[&Bar]) -> Option<Signal>> = vec![
            gold_strategies::wq_trend_momentum,
            gold_strategies::wq_volatility_regime,
            gold_strategies::vgrsi_strategy,
            gold_strategies::wq_momentum_reversal,
            gold_strategies::volume_imbalance_signal,
            gold_strategies::opening_range_breakout,
            gold_strategies::volume_reversal,
            gold_strategies::weekly_nasdaq_strategy,
            gold_strategies::drawdown_based_sizer,
            gold_strategies::strategy_degradation_detector,
            gold_strategies::order_flow_80_20,
            gold_strategies::gapper_edge,
            gold_strategies::polymarket_edge_detector,
            gold_strategies::lw_donchian_breakout,
        ];

        for runner in &fallback_runners {
            if let Some(signal) = runner(symbol, window) {
                if signal.confidence > best_confidence {
                    best_signal = Some(signal.clone());
                    best_confidence = signal.confidence;
                }
            }
        }

        if let Some(signal) = best_signal {
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
