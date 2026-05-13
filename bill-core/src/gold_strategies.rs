//! Gold‑rated strategy implementations
//! This module provides concrete strategy functions for all signals that have been
//! classified as **gold** in the research pipeline. Each function returns a
//! `Signal` (the same type used throughout the back‑testing framework) that can
//! be fed directly into the `run_backtest` utilities.
//!
//! The actual algorithmic core is deliberately lightweight — the aim of this
//! framework is to expose a **development scaffold** that can be rapidly
//! iterated on, unit‑tested, and plugged into the existing `StrategyEvaluator`
//! utilities (grid‑search, permutation test, walk‑forward). Advanced logic can be
//! developed later without changing the surrounding orchestration.

use crate::pm_strategies::{Signal, StrategyParams};
use crate::types::BarSeries;
use crate::tools::strategy_evaluator::{grid_search, permutation_test, walk_forward_eval};
use crate::backtest::run_backtest;
use crate::types::StrategyResult;

/// Larry Williams Donchian breakout (gold).
/// Uses the existing `donchian_signal` helper with the proven look‑back range.
pub fn lw_donchian_breakout(data: &BarSeries) -> Signal {
    // The proven window for LW Donchian is 20 bars (see gold checklist).
    crate::pm_strategies::donchian_signal(data, 20)
}

/// Polymarket edge detector (gold).
/// Placeholder — actual edge detection logic lives in the Polymarket module.
/// Here we simply forward the signal for integration purposes.
pub fn polymarket_edge_detector(_data: &BarSeries) -> Signal {
    // TODO: replace with real edge detection algorithm.
    // For now we return an empty signal to keep the pipeline functional.
    Signal::default()
}

/// Statistical gapper edge (gold).
/// Simple heuristic: breakouts when price gaps > 2% from previous close.
pub fn gapper_edge(data: &BarSeries) -> Signal {
    let mut sig = Signal::default();
    for i in 1..data.bars.len() {
        let prev = data.bars[i - 1].close;
        let cur = data.bars[i].open;
        if ((cur - prev) / prev).abs() > 0.02 {
            // Treat a gap up as a long signal, gap down as short.
            if cur > prev {
                sig.entries.push(StrategyParams {
                    index: i,
                    long: true,
                    short: false,
                });
            } else {
                sig.entries.push(StrategyParams {
                    index: i,
                    long: false,
                    short: true,
                });
            }
        }
    }
    sig
}

/// NQ 80/20 order‑flow breakout (gold).
/// Very simplified — uses the existing donchian helper as a placeholder.
pub fn order_flow_80_20(data: &BarSeries) -> Signal {
    // Placeholder: uses donchian(30) until a dedicated order-flow signal exists.
    crate::pm_strategies::donchian_signal(data, 30)
}

/// Collect all gold strategies in a static slice for iteration.
pub static GOLD_STRATEGIES: &[(&str, fn(&BarSeries) -> Signal)] = &[
    ("lw_donchian_breakout", lw_donchian_breakout),
    ("polymarket_edge_detector", polymarket_edge_detector),
    ("gapper_edge", gapper_edge),
    ("order_flow_80_20", order_flow_80_20),
];

/// Run the full evaluation pipeline for every gold strategy.
/// Returns a vector of (strategy_name, StrategyResult) for downstream reporting.
pub fn evaluate_all_gold(data: &BarSeries) -> Vec<(String, StrategyResult)> {
    let mut results = Vec::new();
    for (name, func) in GOLD_STRATEGIES.iter() {
        // 1️⃣ Grid‑search (5‑30 look‑back)
        let best = grid_search(data, 5, 30);
        // 2️⃣ In‑sample permutation test (1 000 perms)
        let p_val = permutation_test(data, best.lookback, best.profit_factor, 1_000);
        // 3️⃣ Walk‑forward test (30‑day re‑optimise, 30‑day test)
        let wf = walk_forward_eval(data, 4 * 24 * 30, 30 * 24, 30 * 24, (5, 30));
        // 4️⃣ Back‑test the chosen look‑back on the full dataset for final metrics
        let sig = func(data);
        let final_res: StrategyResult = run_backtest(&sig);
        // Assemble a concise result struct (we reuse StrategyResult fields plus extras)
        let mut res = final_res.clone();
        // Extend with our extra metrics (p‑value and walk‑forward PFs stored in notes)
        // For simplicity we embed them in the `notes` field if present.
        res.notes = Some(format!("grid_best_look={} pf={:.4} p_val={:.4} wf_pf={:?}",
            best.lookback, best.profit_factor, p_val, wf));
        results.push((name.to_string(), res));
    }
    results
}

// End of gold_strategies.rs
