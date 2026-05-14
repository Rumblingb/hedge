//! param_sweep.rs — Parameter sweeping engine for top 3 strategies.
//! Same as full_strategy_pipeline but reads param overrides from env vars.
//!
//! USAGE: VAR1=val VAR2=val cargo run --bin param_sweep -- <csv_path> --symbol NQ
//!
//! Env vars for orb-breakout:
//!   ORB_RANGE_WINDOW (default 12), ORB_VOL_THRESHOLD (default 1.3), ORB_EXIT_OFFSET (default 5)
//!
//! Env vars for wq-trend-mom:
//!   WQ_SMA_SHORT (default 20), WQ_SMA_LONG (default 50), WQ_VOL_THRESHOLD (default 1.3), WQ_EXIT_OFFSET (default 5)
//!
//! Env vars for wq-vol-regime:
//!   WV_SHORT_LOOKBACK (default 10), WV_LONG_LOOKBACK (default 30),
//!   WV_SHORT_THRESHOLD (default 1.5), WV_LONG_THRESHOLD (default 0.7), WV_EXIT_OFFSET (default 5)
//!
//! Use --strategy orb-breakout to run only that strategy (optional filter).

use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::collections::HashMap;

#[derive(Debug, Clone)]
struct Bar {
    ts: String, symbol: String, open: f64, high: f64, low: f64, close: f64, volume: u64,
}

#[derive(Debug, Clone)]
struct Trade {
    strategy_id: String, symbol: String, side: String,
    entry: f64, exit: f64, entry_ts: String, exit_ts: String,
    r_multiple: f64, contracts: u32,
}

fn env_f64(name: &str, default: f64) -> f64 {
    env::var(name).ok().and_then(|v| v.parse().ok()).unwrap_or(default)
}

fn env_usize(name: &str, default: usize) -> usize {
    env::var(name).ok().and_then(|v| v.parse().ok()).unwrap_or(default)
}

fn atr(bars: &[Bar], period: usize) -> f64 {
    if bars.len() < period { return 0.0; }
    bars[bars.len()-period..].iter().map(|b| b.high - b.low).sum::<f64>() / period as f64
}

fn sma(bars: &[Bar], period: usize) -> f64 {
    if bars.len() < period { return 0.0; }
    bars[bars.len()-period..].iter().map(|b| b.close).sum::<f64>() / period as f64
}

fn avg_vol_window(bars: &[Bar], idx: usize, window: usize) -> f64 {
    if idx < window || bars.len() < idx { return 0.0; }
    bars[idx-window..idx].iter().map(|b| b.volume as f64).sum::<f64>() / window as f64
}

fn run_strategy(bars: &[Bar], sid: &str, only_strategy: &str) -> Vec<Trade> {
    let mut trades = Vec::new();
    if bars.len() < 50 { return trades; }
    let n = bars.len();

    // Check strategy filter
    if only_strategy != "ALL" && sid != only_strategy {
        return trades;
    }

    match sid {
        "orb-breakout" => {
            let range_window = env_usize("ORB_RANGE_WINDOW", 12);
            let vol_threshold = env_f64("ORB_VOL_THRESHOLD", 1.3);
            let exit_offset = env_usize("ORB_EXIT_OFFSET", 5);

            // Fixed opening range: first `range_window` bars of the dataset (matching original behavior)
            let range_high = bars[0..range_window.min(n)].iter().map(|b| b.high).fold(0.0_f64, f64::max);
            let range_low = bars[0..range_window.min(n)].iter().map(|b| b.low).fold(f64::MAX, f64::min);
            let range = range_high - range_low;
            if range <= 0.0 { return trades; }

            for i in (range_window.max(14))..n {
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit_idx = (i + exit_offset).min(n - 1);
                let exit = bars[exit_idx].close;

                if bars[i].close > range_high && bars[i].volume as f64 > avg_vol_window(bars, i, 10) * vol_threshold {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[exit_idx].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if bars[i].close < range_low && bars[i].volume as f64 > avg_vol_window(bars, i, 10) * vol_threshold {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[exit_idx].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        "wq-trend-mom" => {
            let sma_short = env_usize("WQ_SMA_SHORT", 20);
            let sma_long = env_usize("WQ_SMA_LONG", 50);
            let vol_threshold = env_f64("WQ_VOL_THRESHOLD", 1.3);
            let exit_offset = env_usize("WQ_EXIT_OFFSET", 5);
            let min_bars = sma_long + exit_offset + 5;

            for i in min_bars..n {
                if i < sma_long { continue; }
                let sma_s = sma(&bars[..=i], sma_short);
                let sma_l = sma(&bars[..=i], sma_long);
                let avg_vol: f64 = bars[i-10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
                if avg_vol <= 0.0 { continue; }
                let vol_ratio = bars[i].volume as f64 / avg_vol;
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit_idx = (i + exit_offset).min(n - 1);
                let exit = bars[exit_idx].close;

                if bars[i].close > sma_s && sma_s > sma_l && vol_ratio > vol_threshold {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[exit_idx].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if bars[i].close < sma_s && sma_s < sma_l && vol_ratio > vol_threshold {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[exit_idx].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        "wq-vol-regime" => {
            let short_lookback = env_usize("WV_SHORT_LOOKBACK", 10);
            let long_lookback = env_usize("WV_LONG_LOOKBACK", 30);
            let short_threshold = env_f64("WV_SHORT_THRESHOLD", 1.5);
            let long_threshold = env_f64("WV_LONG_THRESHOLD", 0.7);
            let exit_offset = env_usize("WV_EXIT_OFFSET", 5);
            let min_bars = long_lookback + exit_offset + 5;

            for i in min_bars..n {
                let short_vol: f64 = bars[i-short_lookback..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / short_lookback as f64;
                let long_vol: f64 = bars[i-long_lookback..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / long_lookback as f64;
                if long_vol <= 0.0 { continue; }
                let vol_ratio = short_vol / long_vol;
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit_idx = (i + exit_offset).min(n - 1);
                let exit = bars[exit_idx].close;

                if vol_ratio > short_threshold {
                    // Low expansion → short (vol spike, mean reversion)
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[exit_idx].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                } else if vol_ratio < long_threshold {
                    // Low contraction → long (quiet → breakout)
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[exit_idx].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                }
            }
        }

        _ => {}
    }
    trades
}

fn report(trades: &[Trade], label: &str) -> (usize, f64, f64) {
    if trades.is_empty() { return (0, 0.0, 0.0); }
    let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
    let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
    let losses = trades.iter().filter(|t| t.r_multiple <= 0.0).count();
    let total = trades.len();
    let wr = if total > 0 { wins as f64 / total as f64 * 100.0 } else { 0.0 };
    println!("  {}: {} trades, {}/{} W/L ({:.1}%), total R {:.2}", label, total, wins, losses, wr, total_r);
    (total, total_r, wr)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let csv_path = args.get(1).map(|s| s.as_str()).unwrap_or("data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv");
    let target_symbol = args.iter().position(|a| a == "--symbol").and_then(|i| args.get(i+1)).map(|s| s.as_str()).unwrap_or("ALL");
    let only_strategy = args.iter().position(|a| a == "--strategy").and_then(|i| args.get(i+1)).map(|s| s.as_str()).unwrap_or("ALL");

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

    let mut by_symbol: HashMap<String, Vec<Bar>> = HashMap::new();
    for b in all_bars {
        by_symbol.entry(b.symbol.clone()).or_default().push(b);
    }

    let strategies = ["orb-breakout", "wq-trend-mom", "wq-vol-regime"];

    println!("=== PARAM SWEEP ===");
    println!("CSV: {}", csv_path);
    println!("Strategies: {}", if only_strategy == "ALL" { strategies.join(", ") } else { only_strategy.to_string() });
    println!("Symbol: {}", target_symbol);
    println!();

    // Print env overrides
    for (k, v) in env::vars() {
        if k.starts_with("ORB_") || k.starts_with("WQ_") || k.starts_with("WV_") {
            println!("  {} = {}", k, v);
        }
    }
    println!();

    let mut grand_total = 0;
    let mut grand_pnl = 0.0_f64;

    for (symbol, bars) in &by_symbol {
        println!("-- {} ({} bars) --", symbol, bars.len());

        for sid in &strategies {
            if only_strategy != "ALL" && *sid != only_strategy { continue; }
            let trades = run_strategy(bars, sid, only_strategy);
            let (cnt, total_r, _) = report(&trades, sid);
            grand_total += cnt;
        }
        println!();
    }

    println!("=== GRAND TOTAL: {} trades ===", grand_total);
    Ok(())
}
