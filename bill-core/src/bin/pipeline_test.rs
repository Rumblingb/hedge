//! Quick pipeline runner — tests ALL strategies on a given CSV at full depth.
//! Usage: cargo run --bin pipeline-test <csv_path> [max_bars]
use bill_core::run_pipeline;
use std::env;

fn main() -> anyhow::Result<()> {
    let args: Vec<String> = env::args().collect();
    let csv_path = args
        .get(1)
        .expect("Usage: pipeline-test <csv_path> [max_bars]");
    let max_bars = args.get(2).and_then(|s| s.parse::<usize>().ok());

    let result = run_pipeline(csv_path, max_bars)?;

    println!("=== PIPELINE RESULTS ===");
    println!("Data: {}", csv_path);
    println!(
        "Bars: {}",
        if max_bars.unwrap_or(0) > 0 {
            format!("{} (limited)", max_bars.unwrap())
        } else {
            "all".into()
        }
    );
    println!("Trades: {}", result.trades.len());
    println!(
        "Wins/Losses: {}/{} ({}%)",
        result.wins,
        result.losses,
        (result.win_rate * 100.0) as u32
    );
    println!("Total R: {:.2}", result.total_r);
    println!("Avg R per trade: {:.3}", result.average_r);
    println!("Max DD in R: {:.2}", result.max_drawdown_r);
    println!("Profit Factor: {:.2}", result.profit_factor);

    // Per-strategy breakdown
    let mut strat_trades: std::collections::HashMap<String, Vec<f64>> =
        std::collections::HashMap::new();
    for t in &result.trades {
        strat_trades
            .entry(t.strategy_id.clone())
            .or_default()
            .push(t.net_r);
    }
    println!();
    println!("=== PER-STRATEGY ===");
    let mut sorted: Vec<_> = strat_trades.into_iter().collect();
    sorted.sort_by(|a, b| b.1.len().cmp(&a.1.len()));
    for (sid, rs) in &sorted {
        let wins = rs.iter().filter(|r| **r > 0.0).count();
        let losses = rs.len() - wins;
        let total_r: f64 = rs.iter().sum();
        let avg_r = total_r / rs.len() as f64;
        let wr_pct = (wins as f64 / rs.len().max(1) as f64 * 100.0) as u32;
        println!(
            "{:30} | {:3} trades | {:3}/{:3} W/L ({}%) | {:+.2}R avg | {:+.2}R total",
            sid,
            rs.len(),
            wins,
            losses,
            wr_pct,
            avg_r,
            total_r
        );
    }

    Ok(())
}
