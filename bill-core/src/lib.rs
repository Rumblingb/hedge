pub mod backtest;
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
