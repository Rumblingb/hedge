//! param_sweep.rs — Parameterized strategy testing for optimization sweeps.
//! Runs a single strategy with custom parameters on a CSV.
//!
//! USAGE: cargo run --bin param_sweep -- --strategy <name> --csv <path> [--symbol <sym>] --params <k=v,k=v,...>
//!
//! Parameters per strategy:
//!   orb-breakout: range_window, vol_threshold, exit_offset
//!   wq-trend-mom: sma_short, sma_long, vol_threshold, exit_offset
//!   wq-vol-regime: short_lookback, long_lookback, short_threshold, long_threshold, exit_offset

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

fn run_strategy(bars: &[Bar], sid: &str, params: &HashMap<String, f64>) -> Vec<Trade> {
    let mut trades = Vec::new();
    if bars.len() < 50 { return trades; }
    let n = bars.len();

    match sid {
        "orb-breakout" => {
            let range_window = params.get("range_window").copied().unwrap_or(12.0) as usize;
            let vol_threshold = params.get("vol_threshold").copied().unwrap_or(1.3);
            let exit_offset = params.get("exit_offset").copied().unwrap_or(5.0) as usize;

            // Ensure we have enough bars for the range window
            for i in range_window..n.saturating_sub(exit_offset) {
                let end = i.min(range_window);
                let range_high = bars[0..end].iter().map(|b| b.high).fold(0.0_f64, f64::max);
                let range_low = bars[0..end].iter().map(|b| b.low).fold(f64::MAX, f64::min);
                let range = range_high - range_low;
                if range <= 0.0 { continue; }
                let atr_val = bars[i.saturating_sub(14)..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+exit_offset].close;
                let avg_vol = avg_vol_window(bars, i, 10);
                if avg_vol <= 0.0 { continue; }
                if bars[i].close > range_high && bars[i].volume as f64 > avg_vol * vol_threshold {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if bars[i].close < range_low && bars[i].volume as f64 > avg_vol * vol_threshold {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        "wq-trend-mom" => {
            let sma_short = params.get("sma_short").copied().unwrap_or(20.0) as usize;
            let sma_long = params.get("sma_long").copied().unwrap_or(50.0) as usize;
            let vol_threshold = params.get("vol_threshold").copied().unwrap_or(1.3);
            let exit_offset = params.get("exit_offset").copied().unwrap_or(5.0) as usize;

            let min_bars = sma_long + exit_offset + 5;
            for i in sma_long..n.saturating_sub(exit_offset) {
                let sma_short_val = sma(&bars[..=i], sma_short);
                let sma_long_val = sma(&bars[..=i], sma_long);
                let avg_vol: f64 = bars[i.saturating_sub(10)..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
                if avg_vol <= 0.0 { continue; }
                let vol_ratio = bars[i].volume as f64 / avg_vol;
                let atr_val = bars[i.saturating_sub(14)..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+exit_offset].close;
                if bars[i].close > sma_short_val && sma_short_val > sma_long_val && vol_ratio > vol_threshold {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if bars[i].close < sma_short_val && sma_short_val < sma_long_val && vol_ratio > vol_threshold {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        "wq-vol-regime" => {
            let short_lookback = params.get("short_lookback").copied().unwrap_or(10.0) as usize;
            let long_lookback = params.get("long_lookback").copied().unwrap_or(30.0) as usize;
            let short_threshold = params.get("short_threshold").copied().unwrap_or(1.5);
            let long_threshold = params.get("long_threshold").copied().unwrap_or(0.7);
            let exit_offset = params.get("exit_offset").copied().unwrap_or(5.0) as usize;

            let min_bars = long_lookback + exit_offset + 5;
            for i in long_lookback..n.saturating_sub(exit_offset) {
                let short_vol: f64 = bars[i.saturating_sub(short_lookback)..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / short_lookback as f64;
                let long_vol: f64 = bars[i.saturating_sub(long_lookback)..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / long_lookback as f64;
                if long_vol <= 0.0 { continue; }
                let vol_ratio = short_vol / long_vol;
                let atr_val = bars[i.saturating_sub(14)..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+exit_offset].close;
                if vol_ratio > short_threshold {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                } else if vol_ratio < long_threshold {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                }
            }
        }

        _ => {
            eprintln!("Unknown strategy: {}", sid);
        }
    }
    trades
}

fn parse_params(param_str: &str) -> HashMap<String, f64> {
    let mut params = HashMap::new();
    for pair in param_str.split(',') {
        let parts: Vec<&str> = pair.split('=').collect();
        if parts.len() == 2 {
            if let Ok(val) = parts[1].trim().parse::<f64>() {
                params.insert(parts[0].trim().to_string(), val);
            }
        }
    }
    params
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();

    let csv_path = args.iter()
        .position(|a| a == "--csv")
        .and_then(|i| args.get(i+1))
        .map(|s| s.as_str())
        .unwrap_or("data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv");

    let strategy = args.iter()
        .position(|a| a == "--strategy")
        .and_then(|i| args.get(i+1))
        .map(|s| s.as_str())
        .unwrap_or("orb-breakout");

    let target_symbol = args.iter()
        .position(|a| a == "--symbol")
        .and_then(|i| args.get(i+1))
        .map(|s| s.as_str())
        .unwrap_or("NQ");

    let param_str = args.iter()
        .position(|a| a == "--params")
        .and_then(|i| args.get(i+1))
        .map(|s| s.as_str())
        .unwrap_or("");

    let params = parse_params(param_str);

    // Read CSV
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
        return Ok(());
    }

    // Group by symbol
    let mut by_symbol: HashMap<String, Vec<Bar>> = HashMap::new();
    for b in all_bars {
        by_symbol.entry(b.symbol.clone()).or_default().push(b);
    }

    // For param sweep output, just report each symbol's results
    for (symbol, bars) in &by_symbol {
        let trades = run_strategy(bars, strategy, &params);

        if trades.is_empty() {
            println!("{}|{}|0|0|0|0.00|0.00", strategy, symbol);
        } else {
            let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
            let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
            let losses = trades.len() - wins;
            let wr = wins as f64 / trades.len() as f64 * 100.0;

            // Filter: at most 1 trade per 2 bars
            let mut filtered: Vec<Trade> = trades.clone();
            filtered.sort_by(|a, b| a.entry_ts.cmp(&b.entry_ts));
            let mut deduped = Vec::new();
            let mut last_idx: usize = 0;
            for t in &filtered {
                let idx = bars.iter().position(|b| b.ts == t.entry_ts).unwrap_or(0);
                if idx >= last_idx + 2 {
                    deduped.push(t.clone());
                    last_idx = idx;
                }
            }

            let fcnt = deduped.len();
            let fpnl: f64 = if fcnt > 0 {
                let fr: f64 = deduped.iter().map(|t| t.r_multiple).sum();
                let fwins = deduped.iter().filter(|t| t.r_multiple > 0.0).count();
                let fwr = fwins as f64 / fcnt as f64 * 100.0;
                let avg_risk = deduped.iter().map(|t| (t.entry - t.exit).abs()).sum::<f64>() / fcnt as f64;
                let point_val = if symbol == "NQ" { 20.0 } else if symbol == "ES" { 50.0 } else { 10.0 };
                fr * avg_risk * point_val - fcnt as f64 * 5.0
            } else { 0.0 };

            // Output pipe-delimited for easy parsing
            // strategy|symbol|trades|filtered|wins|wr%|totalR|filteredPnL
            println!("{}|{}|{}|{}|{}|{:.1}|{:.2}|{:.0}",
                strategy, symbol,
                trades.len(), fcnt, wins, wr, total_r, fpnl);
        }
    }

    Ok(())
}
