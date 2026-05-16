//! param_sweep.rs — Run a single strategy with parameterized settings.
//! Usage: cargo run --bin param_sweep -- <csv_path> --strategy <name> [--symbol <sym>] [params...]
//!
//! Strategies and their params:
//!   orb-breakout   --range-window N --vol-threshold N --exit-offset N
//!   wq-trend-mom   --sma-short N --sma-long N --vol-threshold N --exit-offset N
//!   wq-vol-regime  --short-lookback N --long-lookback N --short-threshold N --long-threshold N --exit-offset N

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

fn sma(bars: &[Bar], period: usize) -> f64 {
    if bars.len() < period { return 0.0; }
    bars[bars.len()-period..].iter().map(|b| b.close).sum::<f64>() / period as f64
}

fn avg_vol_window(bars: &[Bar], idx: usize, window: usize) -> f64 {
    if idx < window || bars.len() < idx { return 0.0; }
    bars[idx-window..idx].iter().map(|b| b.volume as f64).sum::<f64>() / window as f64
}

fn run_orb_breakout(bars: &[Bar], range_window: usize, vol_threshold: f64, exit_offset: usize) -> Vec<Trade> {
    let mut trades = Vec::new();
    let n = bars.len();
    if n < range_window + exit_offset { return trades; }
    // Use a single fixed range from the first `range_window` bars
    let range_high = bars[0..range_window.min(n)].iter().map(|b| b.high).fold(0.0_f64, f64::max);
    let range_low = bars[0..range_window.min(n)].iter().map(|b| b.low).fold(f64::MAX, f64::min);
    let range = range_high - range_low;
    if range <= 0.0 { return trades; }
    for i in range_window..n.saturating_sub(exit_offset) {
        let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 { continue; }
        let exit = bars[i+exit_offset].close;
        if bars[i].close > range_high && bars[i].volume as f64 > avg_vol_window(bars, i, 10) * vol_threshold {
            trades.push(Trade {
                strategy_id: "orb-breakout".into(), symbol: bars[i].symbol.clone(),
                side: "long".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
            });
        } else if bars[i].close < range_low && bars[i].volume as f64 > avg_vol_window(bars, i, 10) * vol_threshold {
            trades.push(Trade {
                strategy_id: "orb-breakout".into(), symbol: bars[i].symbol.clone(),
                side: "short".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
            });
        }
    }
    trades
}

fn run_wq_trend_mom(bars: &[Bar], sma_short: usize, sma_long: usize, vol_threshold: f64, exit_offset: usize) -> Vec<Trade> {
    let mut trades = Vec::new();
    let n = bars.len();
    let min_bars = sma_long.max(40) + exit_offset;
    if n < min_bars { return trades; }
    for i in sma_long..n.saturating_sub(exit_offset) {
        let sma_s = sma(&bars[..=i], sma_short);
        let sma_l = sma(&bars[..=i], sma_long);
        let avg_vol: f64 = bars[i-10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
        if avg_vol <= 0.0 { continue; }
        let vol_ratio = bars[i].volume as f64 / avg_vol;
        let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 { continue; }
        let exit = bars[i+exit_offset].close;
        if bars[i].close > sma_s && sma_s > sma_l && vol_ratio > vol_threshold {
            trades.push(Trade {
                strategy_id: "wq-trend-mom".into(), symbol: bars[i].symbol.clone(),
                side: "long".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
            });
        } else if bars[i].close < sma_s && sma_s < sma_l && vol_ratio > vol_threshold {
            trades.push(Trade {
                strategy_id: "wq-trend-mom".into(), symbol: bars[i].symbol.clone(),
                side: "short".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
            });
        }
    }
    trades
}

fn run_wq_vol_regime(bars: &[Bar], short_lookback: usize, long_lookback: usize, short_threshold: f64, long_threshold: f64, exit_offset: usize) -> Vec<Trade> {
    let mut trades = Vec::new();
    let n = bars.len();
    if n < long_lookback + exit_offset { return trades; }
    for i in long_lookback..n.saturating_sub(exit_offset) {
        let short_vol: f64 = bars[i-short_lookback..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / short_lookback as f64;
        let long_vol: f64 = bars[i-long_lookback..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / long_lookback as f64;
        if long_vol <= 0.0 { continue; }
        let vol_ratio = short_vol / long_vol;
        let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 { continue; }
        let exit = bars[i+exit_offset].close;
        if vol_ratio > short_threshold {
            trades.push(Trade {
                strategy_id: "wq-vol-regime".into(), symbol: bars[i].symbol.clone(),
                side: "short".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
            });
        } else if vol_ratio < long_threshold {
            trades.push(Trade {
                strategy_id: "wq-vol-regime".into(), symbol: bars[i].symbol.clone(),
                side: "long".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
            });
        }
    }
    trades
}

fn report(trades: &[Trade], label: &str, params: &str) {
    if trades.is_empty() {
        println!("  {} [{}]: 0 trades, 0.00 R", label, params);
        return;
    }
    let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
    let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
    let losses = trades.iter().filter(|t| t.r_multiple <= 0.0).count();
    let total = trades.len();
    let wr = if total > 0 { wins as f64 / total as f64 * 100.0 } else { 0.0 };
    let avg_r = if total > 0 { total_r / total as f64 } else { 0.0 };
    println!("  {} [{}]: {} trades, {}/{} W/L ({:.1}%), total R {:.2}, avg R {:.3}", label, params, total, wins, losses, wr, total_r, avg_r);
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let csv_path = args.get(1).map(|s| s.as_str()).unwrap_or_else(|| {
        eprintln!("Usage: param_sweep <csv_path> --strategy <name> [options] [--symbol <sym>]");
        std::process::exit(1);
    });

    let strategy = args.iter().position(|a| a == "--strategy")
        .and_then(|i| args.get(i+1)).map(|s| s.as_str()).unwrap_or("orb-breakout");
    let target_symbol = args.iter().position(|a| a == "--symbol")
        .and_then(|i| args.get(i+1)).map(|s| s.as_str()).unwrap_or("NQ");

    // Parse optional params
    let parse_f64 = |name: &str, default: f64| -> f64 {
        args.iter().position(|a| a == name)
            .and_then(|i| args.get(i+1))
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or(default)
    };
    let parse_usize = |name: &str, default: usize| -> usize {
        args.iter().position(|a| a == name)
            .and_then(|i| args.get(i+1))
            .and_then(|s| s.parse::<usize>().ok())
            .unwrap_or(default)
    };

    // Load data
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
        eprintln!("No data loaded for symbol={}", target_symbol);
        std::process::exit(1);
    }

    let mut by_symbol: HashMap<String, Vec<Bar>> = HashMap::new();
    for b in all_bars {
        by_symbol.entry(b.symbol.clone()).or_default().push(b);
    }

    match strategy {
        "orb-breakout" => {
            let range_window = parse_usize("--range-window", 12);
            let vol_threshold = parse_f64("--vol-threshold", 1.3);
            let exit_offset = parse_usize("--exit-offset", 8);
            let params = format!("rw={},vt={},ex={}", range_window, vol_threshold, exit_offset);
            for (symbol, bars) in &by_symbol {
                let trades = run_orb_breakout(bars, range_window, vol_threshold, exit_offset);
                report(&trades, &format!("orb-breakout/{}", symbol), &params);
            }
        },
        "wq-trend-mom" => {
            let sma_short = parse_usize("--sma-short", 20);
            let sma_long = parse_usize("--sma-long", 50);
            let vol_threshold = parse_f64("--vol-threshold", 1.3);
            let exit_offset = parse_usize("--exit-offset", 8);
            let params = format!("ss={},sl={},vt={},ex={}", sma_short, sma_long, vol_threshold, exit_offset);
            for (symbol, bars) in &by_symbol {
                let trades = run_wq_trend_mom(bars, sma_short, sma_long, vol_threshold, exit_offset);
                report(&trades, &format!("wq-trend-mom/{}", symbol), &params);
            }
        },
        "wq-vol-regime" => {
            let short_lookback = parse_usize("--short-lookback", 10);
            let long_lookback = parse_usize("--long-lookback", 30);
            let short_threshold = parse_f64("--short-threshold", 1.5);
            let long_threshold = parse_f64("--long-threshold", 0.7);
            let exit_offset = parse_usize("--exit-offset", 5);
            let params = format!("slk={},llk={},st={},lt={},ex={}", short_lookback, long_lookback, short_threshold, long_threshold, exit_offset);
            for (symbol, bars) in &by_symbol {
                let trades = run_wq_vol_regime(bars, short_lookback, long_lookback, short_threshold, long_threshold, exit_offset);
                report(&trades, &format!("wq-vol-regime/{}", symbol), &params);
            }
        },
        _ => {
            eprintln!("Unknown strategy: {}", strategy);
            std::process::exit(1);
        }
    }

    Ok(())
}
