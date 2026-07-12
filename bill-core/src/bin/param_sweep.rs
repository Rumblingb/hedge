//! param_sweep.rs — Single-strategy parameterized backtest runner.
//! Compile once, run many times with different parameters via CLI args.
//!
//! USAGE: cargo run --bin param_sweep -- \
//!   --strategy <id> --csv <path> --symbol <SYM> \
//!   [strategy-specific params...]
//!
//! Supported strategies: orb-breakout, wq-trend-mom, wq-vol-regime

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
}

fn sma(bars: &[Bar], period: usize) -> f64 {
    if bars.len() < period || period == 0 {
        return 0.0;
    }
    bars[bars.len() - period..]
        .iter()
        .map(|b| b.close)
        .sum::<f64>()
        / period as f64
}

fn avg_vol_window(bars: &[Bar], idx: usize, window: usize) -> f64 {
    if idx < window || window == 0 {
        return 0.0;
    }
    bars[idx - window..idx]
        .iter()
        .map(|b| b.volume as f64)
        .sum::<f64>()
        / window as f64
}

fn run_orb_breakout(
    bars: &[Bar],
    range_window: usize,
    vol_threshold: f64,
    exit_offset: usize,
) -> Vec<Trade> {
    let mut trades = Vec::new();
    let n = bars.len();
    if n < range_window + exit_offset + 1 {
        return trades;
    }
    for i in (range_window + 2)..n.saturating_sub(exit_offset) {
        let range_high = bars[i - range_window..i]
            .iter()
            .map(|b| b.high)
            .fold(0.0_f64, f64::max);
        let range_low = bars[i - range_window..i]
            .iter()
            .map(|b| b.low)
            .fold(f64::MAX, f64::min);
        let range = range_high - range_low;
        if range <= 0.0 {
            continue;
        }
        let atr_val: f64 =
            bars[i.saturating_sub(14)..i]
                .iter()
                .map(|b| b.high - b.low)
                .sum::<f64>()
                / 14.0;
        if atr_val <= 0.0 {
            continue;
        }
        let exit = bars[i + exit_offset].close;
        let av = avg_vol_window(bars, i, 10);
        if av <= 0.0 {
            continue;
        }
        if bars[i].close > range_high && bars[i].volume as f64 > av * vol_threshold {
            trades.push(Trade {
                strategy_id: "orb-breakout".into(),
                symbol: bars[i].symbol.clone(),
                side: "long".into(),
                entry: bars[i].close,
                exit,
                entry_ts: bars[i].ts.clone(),
                exit_ts: bars[i + exit_offset].ts.clone(),
                r_multiple: (exit - bars[i].close) / atr_val,
            });
        } else if bars[i].close < range_low && bars[i].volume as f64 > av * vol_threshold {
            trades.push(Trade {
                strategy_id: "orb-breakout".into(),
                symbol: bars[i].symbol.clone(),
                side: "short".into(),
                entry: bars[i].close,
                exit,
                entry_ts: bars[i].ts.clone(),
                exit_ts: bars[i + exit_offset].ts.clone(),
                r_multiple: (bars[i].close - exit) / atr_val,
            });
        }
    }
    trades
}

fn run_wq_trend_mom(
    bars: &[Bar],
    sma_short: usize,
    sma_long: usize,
    vol_threshold: f64,
    exit_offset: usize,
) -> Vec<Trade> {
    let mut trades = Vec::new();
    let n = bars.len();
    let min_bars = sma_long.max(sma_short) + exit_offset;
    if n < min_bars {
        return trades;
    }
    for i in sma_long..n.saturating_sub(exit_offset) {
        let ss = sma(&bars[..=i], sma_short);
        let sl = sma(&bars[..=i], sma_long);
        if ss == 0.0 || sl == 0.0 {
            continue;
        }
        let avg_vol: f64 = avg_vol_window(bars, i, 10);
        if avg_vol <= 0.0 {
            continue;
        }
        let vol_ratio = bars[i].volume as f64 / avg_vol;
        let atr_val: f64 =
            bars[i.saturating_sub(14)..i]
                .iter()
                .map(|b| b.high - b.low)
                .sum::<f64>()
                / 14.0;
        if atr_val <= 0.0 {
            continue;
        }
        let exit = bars[i + exit_offset].close;
        if bars[i].close > ss && ss > sl && vol_ratio > vol_threshold {
            trades.push(Trade {
                strategy_id: "wq-trend-mom".into(),
                symbol: bars[i].symbol.clone(),
                side: "long".into(),
                entry: bars[i].close,
                exit,
                entry_ts: bars[i].ts.clone(),
                exit_ts: bars[i + exit_offset].ts.clone(),
                r_multiple: (exit - bars[i].close) / atr_val,
            });
        } else if bars[i].close < ss && ss < sl && vol_ratio > vol_threshold {
            trades.push(Trade {
                strategy_id: "wq-trend-mom".into(),
                symbol: bars[i].symbol.clone(),
                side: "short".into(),
                entry: bars[i].close,
                exit,
                entry_ts: bars[i].ts.clone(),
                exit_ts: bars[i + exit_offset].ts.clone(),
                r_multiple: (bars[i].close - exit) / atr_val,
            });
        }
    }
    trades
}

fn run_wq_vol_regime(
    bars: &[Bar],
    short_lookback: usize,
    long_lookback: usize,
    short_threshold: f64,
    long_threshold: f64,
    exit_offset: usize,
) -> Vec<Trade> {
    let mut trades = Vec::new();
    let n = bars.len();
    if n < long_lookback + exit_offset {
        return trades;
    }
    for i in long_lookback..n.saturating_sub(exit_offset) {
        if i < short_lookback {
            continue;
        }
        let short_vol: f64 = bars[i.saturating_sub(short_lookback)..i]
            .iter()
            .map(|b| b.high - b.low)
            .sum::<f64>()
            / short_lookback as f64;
        let long_vol: f64 = bars[i.saturating_sub(long_lookback)..i]
            .iter()
            .map(|b| b.high - b.low)
            .sum::<f64>()
            / long_lookback as f64;
        if long_vol <= 0.0 {
            continue;
        }
        let vol_ratio = short_vol / long_vol;
        let atr_val: f64 =
            bars[i.saturating_sub(14)..i]
                .iter()
                .map(|b| b.high - b.low)
                .sum::<f64>()
                / 14.0;
        if atr_val <= 0.0 {
            continue;
        }
        let exit = bars[i + exit_offset].close;
        if vol_ratio > short_threshold {
            trades.push(Trade {
                strategy_id: "wq-vol-regime".into(),
                symbol: bars[i].symbol.clone(),
                side: "short".into(),
                entry: bars[i].close,
                exit,
                entry_ts: bars[i].ts.clone(),
                exit_ts: bars[i + exit_offset].ts.clone(),
                r_multiple: (bars[i].close - exit) / atr_val,
            });
        } else if vol_ratio < long_threshold {
            trades.push(Trade {
                strategy_id: "wq-vol-regime".into(),
                symbol: bars[i].symbol.clone(),
                side: "long".into(),
                entry: bars[i].close,
                exit,
                entry_ts: bars[i].ts.clone(),
                exit_ts: bars[i + exit_offset].ts.clone(),
                r_multiple: (exit - bars[i].close) / atr_val,
            });
        }
    }
    trades
}

fn report_json(trades: &[Trade]) -> String {
    if trades.is_empty() {
        return r#"{"trades":0,"wins":0,"losses":0,"wr":0.0,"total_r":0.0,"avg_r":0.0}"#.to_string();
    }
    let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
    let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
    let losses = trades.iter().filter(|t| t.r_multiple <= 0.0).count();
    let total = trades.len();
    let wr = wins as f64 / total as f64 * 100.0;
    let avg_r = total_r / total as f64;
    let longs = trades.iter().filter(|t| t.side == "long").count();
    let shorts = trades.iter().filter(|t| t.side == "short").count();
    let long_r: f64 = trades.iter().filter(|t| t.side == "long").map(|t| t.r_multiple).sum();
    let short_r: f64 = trades.iter().filter(|t| t.side == "short").map(|t| t.r_multiple).sum();

    format!(
        r#"{{"trades":{},"wins":{},"losses":{},"wr":{:.1},"total_r":{:.2},"avg_r":{:.2},"longs":{},"shorts":{},"long_r":{:.2},"short_r":{:.2}}}"#,
        total, wins, losses, wr, total_r, avg_r, longs, shorts, long_r, short_r
    )
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();

    let get = |key: &str| -> Option<String> {
        args.iter()
            .position(|a| a == key)
            .and_then(|i| args.get(i + 1))
            .map(|s| s.to_string())
    };

    let strategy = get("--strategy").unwrap_or_else(|| "orb-breakout".into());
    let csv_path = get("--csv").unwrap_or_else(|| {
        "../data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv".into()
    });
    let symbol = get("--symbol").unwrap_or_else(|| "NQ".into());

    // Parse optional strategy params
    let param = |key: &str, default: f64| -> f64 {
        get(key).and_then(|v| v.parse().ok()).unwrap_or(default)
    };
    let param_usize = |key: &str, default: usize| -> usize {
        get(key).and_then(|v| v.parse().ok()).unwrap_or(default)
    };

    // Load bars
    let file = File::open(&csv_path)?;
    let reader = BufReader::new(file);
    let mut bars: Vec<Bar> = Vec::new();

    for line in reader.lines().skip(1) {
        let line = line?;
        let parts: Vec<&str> = line.split(',').collect();
        if parts.len() >= 7 {
            let sym = parts[1].trim().to_uppercase();
            if symbol == "ALL" || sym == symbol {
                bars.push(Bar {
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

    if bars.is_empty() {
        eprintln!("No data loaded for symbol={}", symbol);
        return Ok(());
    }

    let trades = match strategy.as_str() {
        "orb-breakout" => {
            let rw = param_usize("--range-window", 12);
            let vt = param("--vol-threshold", 1.3);
            let eo = param_usize("--exit-offset", 8);
            run_orb_breakout(&bars, rw, vt, eo)
        }
        "wq-trend-mom" => {
            let ss = param_usize("--sma-short", 20);
            let sl = param_usize("--sma-long", 50);
            let vt = param("--vol-threshold", 1.3);
            let eo = param_usize("--exit-offset", 8);
            run_wq_trend_mom(&bars, ss, sl, vt, eo)
        }
        "wq-vol-regime" => {
            let slk = param_usize("--short-lookback", 10);
            let llk = param_usize("--long-lookback", 30);
            let st = param("--short-threshold", 1.5);
            let lt = param("--long-threshold", 0.7);
            let eo = param_usize("--exit-offset", 5);
            run_wq_vol_regime(&bars, slk, llk, st, lt, eo)
        }
        _ => {
            eprintln!("Unknown strategy: {}", strategy);
            return Ok(());
        }
    };

    // Machine-parseable JSON output on stdout
    println!("{}", report_json(&trades));
    Ok(())
}
