//! multi_pipeline.rs — Run the full Rust strategy pipeline on ALL symbols in a CSV.
//! Tests WQ alphas + gold strategies (where implemented) on every symbol found.
//! Reports per-symbol, per-strategy, aggregated results.
//!
//! USAGE: cargo run --bin multi_pipeline -- <csv_path>
//!   or:  cargo run --bin multi_pipeline -- <csv_path> --symbol NQ

use std::collections::HashMap;
use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader};

#[derive(Debug, Clone)]
struct Bar {
    ts: String,
    symbol: String,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: u64,
}

#[derive(Debug, Clone)]
struct Trade {
    strategy_id: String,
    symbol: String,
    side: String,
    entry: f64,
    exit: f64,
    entry_ts: String,
    exit_ts: String,
    r_multiple: f64,
    contracts: u32,
}

/// Simple backtest for a single strategy and symbol.
fn run_backtest(bars: &[Bar], strategy_id: &str) -> Vec<Trade> {
    let mut trades = Vec::new();
    if bars.len() < 50 {
        return trades;
    }

    match strategy_id {
        "wq-alpha-009" => {
            for i in 30..bars.len() {
                let avg_vol: f64 =
                    bars[i - 20..i].iter().map(|b| b.volume as f64).sum::<f64>() / 20.0;
                let price_range = bars[i - 20..i]
                    .iter()
                    .fold(0.0_f64, |acc, b| acc.max(b.high - b.low))
                    / 2.0;
                if price_range <= 0.0 {
                    continue;
                }
                let spike_vol = bars[i].volume as f64 > avg_vol * 1.8;
                let near_high = bars[i].close > bars[i].high - price_range * 0.3;
                let near_low = bars[i].close < bars[i].low + price_range * 0.3;

                if spike_vol && near_high {
                    let stop = bars[i].high + price_range * 0.5;
                    let target = bars[i].close - price_range * 1.5;
                    let rr = (bars[i].close - target).abs() / (stop - bars[i].close).abs();
                    if rr >= 1.5 {
                        let exit_ts = bars[(i + 5).min(bars.len() - 1)].ts.clone();
                        let exit_close = bars[(i + 5).min(bars.len() - 1)].close;
                        let r = (bars[i].close - exit_close) / (stop - bars[i].close);
                        trades.push(Trade {
                            strategy_id: "wq-alpha-009".into(),
                            symbol: bars[i].symbol.clone(),
                            side: "short".into(),
                            entry: bars[i].close,
                            exit: exit_close,
                            entry_ts: bars[i].ts.clone(),
                            exit_ts,
                            r_multiple: r,
                            contracts: 1,
                        });
                    }
                } else if spike_vol && near_low {
                    let stop = bars[i].low - price_range * 0.5;
                    let target = bars[i].close + price_range * 1.5;
                    let rr = (target - bars[i].close).abs() / (bars[i].close - stop).abs();
                    if rr >= 1.5 {
                        let exit_ts = bars[(i + 5).min(bars.len() - 1)].ts.clone();
                        let exit_close = bars[(i + 5).min(bars.len() - 1)].close;
                        let r = (exit_close - bars[i].close) / (bars[i].close - stop);
                        trades.push(Trade {
                            strategy_id: "wq-alpha-009".into(),
                            symbol: bars[i].symbol.clone(),
                            side: "long".into(),
                            entry: bars[i].close,
                            exit: exit_close,
                            entry_ts: bars[i].ts.clone(),
                            exit_ts,
                            r_multiple: r,
                            contracts: 1,
                        });
                    }
                }
            }
        }
        "wq-alpha-001" => {
            for i in 20..bars.len() - 3 {
                let roc = (bars[i].close - bars[i - 3].close) / bars[i - 3].close;
                let avg_vol: f64 =
                    bars[i - 10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
                let atr_val: f64 =
                    bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 {
                    continue;
                }
                let exit_close = bars[i + 3].close;

                if roc > 0.001 && bars[i].volume as f64 > avg_vol * 1.2 {
                    trades.push(Trade {
                        strategy_id: "wq-alpha-001".into(),
                        symbol: bars[i].symbol.clone(),
                        side: "long".into(),
                        entry: bars[i].close,
                        exit: exit_close,
                        entry_ts: bars[i].ts.clone(),
                        exit_ts: bars[i + 3].ts.clone(),
                        r_multiple: (exit_close - bars[i].close) / atr_val,
                        contracts: 1,
                    });
                } else if roc < -0.001 && bars[i].volume as f64 > avg_vol * 1.2 {
                    trades.push(Trade {
                        strategy_id: "wq-alpha-001".into(),
                        symbol: bars[i].symbol.clone(),
                        side: "short".into(),
                        entry: bars[i].close,
                        exit: exit_close,
                        entry_ts: bars[i].ts.clone(),
                        exit_ts: bars[i + 3].ts.clone(),
                        r_multiple: (bars[i].close - exit_close) / atr_val,
                        contracts: 1,
                    });
                }
            }
        }
        _ => {}
    }
    trades
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let csv_path = args
        .get(1)
        .map(|s| s.as_str())
        .unwrap_or("data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv");
    let target_symbol = args
        .iter()
        .position(|a| a == "--symbol")
        .and_then(|i| args.get(i + 1))
        .map(|s| s.as_str())
        .unwrap_or("ALL");

    let file = File::open(csv_path)?;
    let reader = BufReader::new(file);
    let mut all_bars: Vec<Bar> = Vec::new();

    for line in reader.lines().skip(1) {
        let line = line?;
        let parts: Vec<&str> = line.split(',').collect();
        if parts.len() >= 7 {
            let symbol = parts[1].trim().to_uppercase();
            if target_symbol == "ALL" || symbol == target_symbol {
                all_bars.push(Bar {
                    ts: parts[0].trim().to_string(),
                    symbol,
                    open: parts[2].parse::<f64>().unwrap_or(0.0),
                    high: parts[3].parse::<f64>().unwrap_or(0.0),
                    low: parts[4].parse::<f64>().unwrap_or(0.0),
                    close: parts[5].parse::<f64>().unwrap_or(0.0),
                    volume: parts[6].parse::<u64>().unwrap_or(0),
                });
            }
        }
    }

    if all_bars.is_empty() {
        println!("No data loaded for symbol={}", target_symbol);
        return Ok(());
    }

    // Group by symbol
    let mut by_symbol: HashMap<String, Vec<Bar>> = HashMap::new();
    for b in all_bars {
        by_symbol.entry(b.symbol.clone()).or_default().push(b);
    }

    println!("=== MULTI-ASSET RUST PIPELINE ===");
    println!("CSV: {}", csv_path);
    println!(
        "Symbols: {}",
        by_symbol.keys().cloned().collect::<Vec<_>>().join(", ")
    );
    println!();

    let strategies = ["wq-alpha-009", "wq-alpha-001"];
    let mut grand_total_pnl = 0.0_f64;
    let mut grand_total_trades = 0;

    for (symbol, bars) in &by_symbol {
        println!("-- {} ({} bars) --", symbol, bars.len());
        let mut sym_total_r = 0.0_f64;
        let mut sym_total_trades = 0;

        for sid in &strategies {
            let trades = run_backtest(bars, sid);
            let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
            let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
            let losses = trades.iter().filter(|t| t.r_multiple <= 0.0).count();
            let total = trades.len();

            if total > 0 {
                println!(
                    "  {}: {} trades, {}/{} W/L ({:.1}%), total R {:.2}",
                    sid,
                    total,
                    wins,
                    losses,
                    wins as f64 / total as f64 * 100.0,
                    total_r
                );
                sym_total_r += total_r;
                sym_total_trades += total;
            }
        }

        // Priority filter (at most 1 trade per 2 bars)
        let all_trades: Vec<Trade> = by_symbol
            .get(symbol)
            .map(|_| {
                let mut all: Vec<Trade> = Vec::new();
                for sid in &strategies {
                    all.extend(run_backtest(bars, sid));
                }
                all.sort_by(|a, b| a.entry_ts.cmp(&b.entry_ts));
                let mut filtered = Vec::new();
                let mut last_idx: usize = 0;
                for t in &all {
                    let idx = bars.iter().position(|b| b.ts == t.entry_ts).unwrap_or(0);
                    if idx > last_idx + 2 {
                        filtered.push(t.clone());
                        last_idx = idx;
                    }
                }
                filtered
            })
            .unwrap_or_default();

        if !all_trades.is_empty() {
            let pnl_r: f64 = all_trades.iter().map(|t| t.r_multiple).sum();
            let wins = all_trades.iter().filter(|t| t.r_multiple > 0.0).count();
            let losses = all_trades.iter().filter(|t| t.r_multiple <= 0.0).count();
            let total = all_trades.len();
            let wr = wins as f64 / total as f64 * 100.0;
            let avg_risk = all_trades
                .iter()
                .map(|t| (t.entry - t.exit).abs())
                .sum::<f64>()
                / total as f64;
            let nq_point_value = if symbol == "NQ" {
                20.0
            } else if symbol == "ES" {
                50.0
            } else {
                10.0
            };
            let gross_pnl = pnl_r * avg_risk * nq_point_value;
            let friction = total as f64 * 5.0; // $5 round trip
            let net_pnl = gross_pnl - friction;

            println!(
                "  Combined (filtered): {} trades, {}/{} W/L ({:.1}% WR), PnL +${:.0}",
                total, wins, losses, wr, net_pnl
            );
            grand_total_pnl += net_pnl;
            grand_total_trades += total;
        }
        println!();
    }

    println!("=== TOTAL ===");
    println!(
        "All trades: {}, Net PnL: +${:.0}",
        grand_total_trades, grand_total_pnl
    );

    Ok(())
}
