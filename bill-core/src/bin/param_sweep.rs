//! param_sweep.rs — Run a single strategy with configurable parameters.
//! USAGE: cargo run --bin param_sweep -- --csv <path> --symbol <NQ> --strategy <name> [params]
//!
//! Strategy-specific parameters (with defaults matching full_strategy_pipeline):
//!
//! orb-breakout:  --range-window 12 --vol-threshold 1.3 --exit-offset 8
//! wq-trend-mom:  --sma-short 20 --sma-long 50 --vol-threshold 1.3 --exit-offset 8
//! wq-vol-regime: --short-lookback 10 --long-lookback 30 --short-threshold 1.5 --long-threshold 0.7 --exit-offset 5
//!
//! Output: JSON line with params and results.

use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader};

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

fn parse_f64(s: &str, default: f64) -> f64 {
    s.parse::<f64>().unwrap_or(default)
}

fn parse_usize(s: &str, default: usize) -> usize {
    s.parse::<usize>().unwrap_or(default)
}

fn run_orb_breakout(bars: &[Bar], range_window: usize, vol_threshold: f64, exit_offset: usize) -> Vec<Trade> {
    let mut trades = Vec::new();
    let min_start = range_window.max(14);
    if bars.len() < min_start + exit_offset + 5 { return trades; }
    let n = bars.len();
    let exit_offset = exit_offset.min(n.saturating_sub(2));
    for i in min_start..n.saturating_sub(exit_offset) {
        let range_high = bars[i-range_window..i].iter().map(|b| b.high).fold(0.0_f64, f64::max);
        let range_low = bars[i-range_window..i].iter().map(|b| b.low).fold(f64::MAX, f64::min);
        let range = range_high - range_low;
        if range <= 0.0 { continue; }
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
    if bars.len() < sma_long + exit_offset + 2 { return trades; }
    let n = bars.len();
    let exit_offset = exit_offset.min(n.saturating_sub(2));
    for i in sma_long..n.saturating_sub(exit_offset) {
        let s = sma(&bars[..=i], sma_short);
        let l = sma(&bars[..=i], sma_long);
        if s <= 0.0 || l <= 0.0 { continue; }
        let avg_vol: f64 = bars[i-10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
        if avg_vol <= 0.0 { continue; }
        let vol_ratio = bars[i].volume as f64 / avg_vol;
        let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 { continue; }
        let exit = bars[i+exit_offset].close;
        if bars[i].close > s && s > l && vol_ratio > vol_threshold {
            trades.push(Trade {
                strategy_id: "wq-trend-mom".into(), symbol: bars[i].symbol.clone(),
                side: "long".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
            });
        } else if bars[i].close < s && s < l && vol_ratio > vol_threshold {
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
    if bars.len() < long_lookback + exit_offset + 5 { return trades; }
    let n = bars.len();
    let exit_offset = exit_offset.min(n.saturating_sub(2));
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

fn report_json(trades: &[Trade], params: &[(String, String)]) -> String {
    let total = trades.len();
    if total == 0 {
        let pstr: Vec<String> = params.iter().map(|(k,v)| format!("\"{}\":\"{}\"", k, v)).collect();
        return format!("{{{},\"trades\":0,\"wins\":0,\"losses\":0,\"wr\":0.0,\"total_r\":0.0,\"avg_r\":0.0}}", pstr.join(","));
    }
    let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
    let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
    let losses = trades.iter().filter(|t| t.r_multiple <= 0.0).count();
    let wr = wins as f64 / total as f64 * 100.0;
    let avg_r = total_r / total as f64;
    let pstr: Vec<String> = params.iter().map(|(k,v)| format!("\"{}\":\"{}\"", k, v)).collect();
    format!("{{{},\"trades\":{},\"wins\":{},\"losses\":{},\"wr\":{:.1},\"total_r\":{:.2},\"avg_r\":{:.2}}}",
        pstr.join(","), total, wins, losses, wr, total_r, avg_r)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let mut i = 1;
    let mut csv_path = String::new();
    let mut symbol = String::from("ALL");
    let mut strategy = String::new();
    let mut orb_range_window: usize = 12;
    let mut orb_vol_threshold: f64 = 1.3;
    let mut orb_exit_offset: usize = 8;
    let mut trend_sma_short: usize = 20;
    let mut trend_sma_long: usize = 50;
    let mut trend_vol_threshold: f64 = 1.3;
    let mut trend_exit_offset: usize = 8;
    let mut vol_short_lookback: usize = 10;
    let mut vol_long_lookback: usize = 30;
    let mut vol_short_threshold: f64 = 1.5;
    let mut vol_long_threshold: f64 = 0.7;
    let mut vol_exit_offset: usize = 5;

    while i < args.len() {
        match args[i].as_str() {
            "--csv" => { i += 1; csv_path = args[i].clone(); }
            "--symbol" => { i += 1; symbol = args[i].clone(); }
            "--strategy" => { i += 1; strategy = args[i].clone(); }
            "--range-window" => { i += 1; orb_range_window = parse_usize(&args[i], 12); }
            "--vol-threshold" => { i += 1; let v = parse_f64(&args[i], 1.3); orb_vol_threshold = v; trend_vol_threshold = v; }
            "--exit-offset" => { i += 1; let v = parse_usize(&args[i], 5); orb_exit_offset = v; trend_exit_offset = v; vol_exit_offset = v; }
            "--sma-short" => { i += 1; trend_sma_short = parse_usize(&args[i], 20); }
            "--sma-long" => { i += 1; trend_sma_long = parse_usize(&args[i], 50); }
            "--short-lookback" => { i += 1; vol_short_lookback = parse_usize(&args[i], 10); }
            "--long-lookback" => { i += 1; vol_long_lookback = parse_usize(&args[i], 30); }
            "--short-threshold" => { i += 1; vol_short_threshold = parse_f64(&args[i], 1.5); }
            "--long-threshold" => { i += 1; vol_long_threshold = parse_f64(&args[i], 0.7); }
            _ => {}
        }
        i += 1;
    }

    if csv_path.is_empty() || strategy.is_empty() {
        eprintln!("Usage: param_sweep --csv <path> --strategy <name> [--symbol NQ] [params...]");
        eprintln!("Strategies: orb-breakout, wq-trend-mom, wq-vol-regime");
        std::process::exit(1);
    }

    let file = File::open(&csv_path)?;
    let reader = BufReader::new(file);
    let mut all_bars: Vec<Bar> = Vec::new();
    for line in reader.lines().skip(1) {
        let line = line?;
        let parts: Vec<&str> = line.split(',').collect();
        if parts.len() >= 7 {
            let sym = parts[1].trim().to_uppercase();
            if symbol == "ALL" || sym == symbol {
                all_bars.push(Bar {
                    ts: parts[0].trim().to_string(),
                    symbol: sym,
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
        eprintln!("No data for symbol={}", symbol);
        std::process::exit(1);
    }

    let mut params = Vec::new();
    params.push(("csv".to_string(), csv_path));
    params.push(("symbol".to_string(), symbol.clone()));
    params.push(("strategy".to_string(), strategy.clone()));

    let trades = match strategy.as_str() {
        "orb-breakout" => {
            params.push(("range_window".to_string(), orb_range_window.to_string()));
            params.push(("vol_threshold".to_string(), orb_vol_threshold.to_string()));
            params.push(("exit_offset".to_string(), orb_exit_offset.to_string()));
            run_orb_breakout(&all_bars, orb_range_window, orb_vol_threshold, orb_exit_offset)
        }
        "wq-trend-mom" => {
            params.push(("sma_short".to_string(), trend_sma_short.to_string()));
            params.push(("sma_long".to_string(), trend_sma_long.to_string()));
            params.push(("vol_threshold".to_string(), trend_vol_threshold.to_string()));
            params.push(("exit_offset".to_string(), trend_exit_offset.to_string()));
            run_wq_trend_mom(&all_bars, trend_sma_short, trend_sma_long, trend_vol_threshold, trend_exit_offset)
        }
        "wq-vol-regime" => {
            params.push(("short_lookback".to_string(), vol_short_lookback.to_string()));
            params.push(("long_lookback".to_string(), vol_long_lookback.to_string()));
            params.push(("short_threshold".to_string(), vol_short_threshold.to_string()));
            params.push(("long_threshold".to_string(), vol_long_threshold.to_string()));
            params.push(("exit_offset".to_string(), vol_exit_offset.to_string()));
            run_wq_vol_regime(&all_bars, vol_short_lookback, vol_long_lookback, vol_short_threshold, vol_long_threshold, vol_exit_offset)
        }
        _ => {
            eprintln!("Unknown strategy: {}", strategy);
            std::process::exit(1);
        }
    };

    println!("{}", report_json(&trades, &params));
    Ok(())
}
