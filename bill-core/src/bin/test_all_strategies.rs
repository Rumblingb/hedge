use anyhow::Result;
use bill_core::{ALL_STRATEGIES, types, types::Bar};
use std::collections::HashMap;

fn main() -> Result<()> {
    let csv_files = vec![
        "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv",
        "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-5m.csv",
        "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv",
        "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv",
        "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-60m.csv",
        "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-240m.csv",
        "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1d-5y.csv",
    ];

    for csv_path in &csv_files {
        println!("\n=== Processing {} ===", csv_path);
        let all_bars = types::load_bars_csv(csv_path)?;
        let grouped = types::group_by_symbol(&all_bars);

        // Map: strategy_id -> {trades, wins, losses, total_r}
        let mut stats: HashMap<String, (u32, u32, u32, f64)> = HashMap::new();

        for (symbol, bars) in &grouped {
            if bars.len() < 21 {
                // Need at least 21 bars to start generating signals (window from 0..i, i>=20)
                continue;
            }
            for i in 20..bars.len() {
                let window = &bars[0..=i];
                for &(strategy_id, runner, _) in ALL_STRATEGIES {
                    if let Some(signal) = runner(symbol, window) {
                        // Check if we can exit at bar+5
                        if i + 5 >= bars.len() {
                            continue;
                        }
                        let exit_price = bars[i + 5].close;
                        let entry_price = signal.entry;
                        let stop_price = signal.stop;
                        let side = signal.side.as_str();

                        // Calculate risk (positive value)
                        let risk = if side == "long" {
                            entry_price - stop_price
                        } else {
                            stop_price - entry_price
                        };
                        if risk <= 0.0 {
                            // Invalid signal, skip
                            continue;
                        }

                        // Calculate R-multiple
                        let r_multiple = if side == "long" {
                            (exit_price - entry_price) / risk
                        } else {
                            (entry_price - exit_price) / risk
                        };

                        let won = r_multiple > 0.0;

                        // Update stats for this strategy
                        let entry = stats
                            .entry(strategy_id.to_string())
                            .or_insert((0, 0, 0, 0.0));
                        entry.0 += 1; // trades
                        if won {
                            entry.1 += 1; // wins
                        } else {
                            entry.2 += 1; // losses
                        }
                        entry.3 += r_multiple; // total_r
                    }
                }
            }
        }

        // Print results for this timeframe
        println!(
            "{:<30} {:<8} {:<6} {:<8} {:<6} {:<10}",
            "Strategy", "Trades", "Wins", "Losses", "WR", "Total R"
        );
        println!("{:-<80}", "");
        for (strategy_id, (trades, wins, losses, total_r)) in &stats {
            let win_rate = if *trades > 0 {
                (*wins as f64) / (*trades as f64) * 100.0
            } else {
                0.0
            };
            println!(
                "{:<30} {:<8} {:<6} {:<8} {:<6.2} {:<10.2}",
                strategy_id, trades, wins, losses, win_rate, total_r
            );
        }
        println!("{:-<80}", "");
        let total_trades: u32 = stats.values().map(|v| v.0).sum();
        let total_wins: u32 = stats.values().map(|v| v.1).sum();
        let total_losses: u32 = stats.values().map(|v| v.2).sum();
        let total_r: f64 = stats.values().map(|v| v.3).sum();
        let overall_wr = if total_trades > 0 {
            (total_wins as f64) / (total_trades as f64) * 100.0
        } else {
            0.0
        };
        println!(
            "{:<30} {:<8} {:<6} {:<8} {:<6.2} {:<10.2}",
            "TOTAL", total_trades, total_wins, total_losses, overall_wr, total_r
        );
    }

    Ok(())
}
