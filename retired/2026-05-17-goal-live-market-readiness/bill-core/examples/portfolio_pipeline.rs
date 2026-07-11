// portfolio_pipeline.rs — Institutional pipeline: signals + VIX regime + Kelly + CPPI.

use bill_core;
use bill_core::portfolio::*;
use std::collections::HashMap;

fn sep() -> String {
    std::iter::repeat('=').take(60).collect()
}

fn main() -> anyhow::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: portfolio_pipeline <csv_path> [vx1] [vx2] [initial_capital_r]");
        std::process::exit(1);
    }

    let csv_path = &args[1];
    let vx1: f64 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(17.19);
    let vx2: f64 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(20.50);
    let initial_capital_r: f64 = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(100.0);
    let max_bars: Option<usize> = args.get(5).and_then(|s| s.parse().ok());

    let result = bill_core::run_pipeline(csv_path, max_bars)?;

    println!("{}", sep());
    println!("BILL/HEDGE - INSTITUTIONAL PORTFOLIO PIPELINE");
    println!("{}", sep());
    println!("CSV: {}", csv_path);
    println!("Initial Capital: {:.1}R", initial_capital_r);
    println!("");

    // VIX regime
    let (vix_regime, es_size, nq_size) = detect_vix_regime(vx1, vx2);
    println!("VIX REGIME: {:?}", vix_regime);
    println!("  VIX={:.2}, VIX3M={:.2} -> slope={:.1}%", vx1, vx2, (vx2 - vx1) / vx1 * 100.0);
    println!("  ES sizing: {:.1}x", es_size);
    println!("  NQ sizing: {:.1}x", nq_size);
    println!("");

    println!("BASE PIPELINE (15 strategies, WQ-priority):");
    println!("  Total trades: {}", result.total_trades);
    println!("  Win rate: {:.1}%", result.win_rate * 100.0);
    println!("  Total R: {:.2}", result.total_r);
    println!("  Avg R/trade: {:.3}", result.average_r);
    println!("  Max DD: {:.2}R", result.max_drawdown_r);
    println!("  Profit factor: {:.3}", result.profit_factor);
    println!("");

    // Per-strategy analysis
    let mut strat_returns: HashMap<String, Vec<f64>> = HashMap::new();
    for trade in &result.trades {
        strat_returns.entry(trade.strategy_id.clone()).or_default().push(trade.gross_r);
    }

    println!("PER-STRATEGY KELLY ANALYSIS:");
    let mut strategies: Vec<(String, f64, f64, f64)> = Vec::new();
    for (sid, returns) in &strat_returns {
        let n = returns.len() as f64;
        let wins = returns.iter().filter(|r| **r > 0.0).count() as f64;
        let losses = n - wins;
        let win_rate = if n > 0.0 { wins / n } else { 0.0 };
        let avg_win = if wins > 0.0 {
            returns.iter().filter(|r| **r > 0.0).sum::<f64>() / wins
        } else { 0.0 };
        let avg_loss = if losses > 0.0 {
            returns.iter().filter(|r| **r <= 0.0).sum::<f64>().abs() / losses
        } else { 0.0 };
        let kelly = kelly_fraction(win_rate, avg_win, avg_loss);
        let net_r: f64 = returns.iter().sum();
        println!("  {:>20}: {:4} tr, WR={:.0}%, K={:.3}, NetR={:+.1}",
            sid, returns.len(), win_rate * 100.0, kelly, net_r);
        strategies.push((sid.clone(), win_rate, avg_win, avg_loss));
    }

    // Kelly allocation
    let kelly_stats: Vec<(f64, f64, f64)> = strategies.iter()
        .map(|(_, wr, aw, al)| (*wr, *aw, *al))
        .collect();
    let kelly_weights = kelly_allocate(&kelly_stats);

    println!("\nKELLY ALLOCATION:");
    for (i, (sid, _, _, _)) in strategies.iter().enumerate() {
        if i < kelly_weights.len() && kelly_weights[i] > 0.005 {
            println!("  {:>20}: {:.1}%", sid, kelly_weights[i] * 100.0);
        }
    }

    // CPPI simulation
    let mut cppi = CppiState::new(initial_capital_r, 0.85, 3.0);
    for trade in &result.trades {
        cppi.update(trade.net_r);
    }

    let cppi_return = ((cppi.value - initial_capital_r) / initial_capital_r) * 100.0;

    println!("\nCPPI DRAWDOWN CONTROL (3x mult, 85% floor):");
    println!("  Start: {:.1}R", initial_capital_r);
    println!("  Final: {:.1}R", cppi.value);
    println!("  Return: {:.1}%", cppi_return);
    println!("  Alive: {}", cppi.is_alive());
    println!("  Exposure: {:.1}%", cppi.exposure_pct * 100.0);

    // VIX-adjusted projection
    let es_nq_avg = (es_size + nq_size) / 2.0;
    let vix_cppi_final = initial_capital_r + (cppi.value - initial_capital_r) * es_nq_avg;

    println!("\nVIX-ADJUSTED PROJECTION (avg mult={:.2}x):", es_nq_avg);
    println!("  CPPI Final: {:.1}R", vix_cppi_final);
    println!("");

    println!("{}", sep());
    println!("RECOMMENDATION:");
    if cppi_return > 10.0 && result.profit_factor > 0.8 {
        println!("  SYSTEM VIABLE - Positive projected return with risk controls");
    } else if result.total_r > 50.0 && result.max_drawdown_r < initial_capital_r * 0.3 {
        println!("  HIGH-CONFIDENCE - Strong gross edge, CPPI handles drawdowns");
    } else {
        let blocker = if result.total_r <= 0.0 {
            "Net R negative - need better edge or lower friction"
        } else if result.max_drawdown_r > initial_capital_r * 0.5 {
            "Drawdown too large for CPPI floor"
        } else {
            "Needs more data for significance"
        };
        println!("  {}", blocker);
    }
    println!("{}", sep());

    Ok(())
}
