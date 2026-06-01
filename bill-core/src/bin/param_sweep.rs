//! param_sweep.rs — Exhaustive parameter sweeps for top NQ strategies.
//!
//! USAGE:
//!   cargo run --bin param_sweep -- ../data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv --symbol NQ
//!
//! Output format:
//!   RESULT|<strategy>|<tf>|<params>|<trades>|<wins>|<wr%>|<totalR>|<avgR>

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

fn sma(bars: &[Bar], period: usize) -> f64 {
    if bars.len() < period {
        return 0.0;
    }
    bars[bars.len() - period..]
        .iter()
        .map(|b| b.close)
        .sum::<f64>()
        / period as f64
}

fn avg_vol_window(bars: &[Bar], idx: usize, window: usize) -> f64 {
    if idx < window || bars.len() <= idx {
        return 0.0;
    }
    bars[idx - window..idx]
        .iter()
        .map(|b| b.volume as f64)
        .sum::<f64>()
        / window as f64
}

fn orb_breakout(
    bars: &[Bar],
    range_window: usize,
    vol_threshold: f64,
    exit_offset: usize,
) -> (usize, usize, f64) {
    let n = bars.len();
    let mut wins = 0usize;
    let mut total_r = 0.0_f64;
    let mut count = 0usize;
    if n <= range_window + exit_offset + 14 {
        return (0, 0, 0.0);
    }

    // Match full_strategy_pipeline canonical ORB logic: fixed opening range from bar 0.
    let range_high = bars[0..range_window]
        .iter()
        .map(|b| b.high)
        .fold(0.0_f64, f64::max);
    let range_low = bars[0..range_window]
        .iter()
        .map(|b| b.low)
        .fold(f64::MAX, f64::min);
    let range = range_high - range_low;
    if range <= 0.0 {
        return (0, 0, 0.0);
    }

    for i in (range_window + 2).max(14)..n.saturating_sub(exit_offset) {
        let atr_val = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 {
            continue;
        }
        let exit = bars[i + exit_offset].close;
        let avg_vol = avg_vol_window(bars, i, 10);
        if avg_vol <= 0.0 {
            continue;
        }
        if bars[i].close > range_high && bars[i].volume as f64 > avg_vol * vol_threshold {
            let r = (exit - bars[i].close) / atr_val;
            total_r += r;
            if r > 0.0 {
                wins += 1;
            }
            count += 1;
        } else if bars[i].close < range_low && bars[i].volume as f64 > avg_vol * vol_threshold {
            let r = (bars[i].close - exit) / atr_val;
            total_r += r;
            if r > 0.0 {
                wins += 1;
            }
            count += 1;
        }
    }
    (count, wins, total_r)
}

fn wq_trend_mom(
    bars: &[Bar],
    sma_short: usize,
    sma_long: usize,
    vol_ratio_threshold: f64,
    exit_offset: usize,
) -> (usize, usize, f64) {
    let n = bars.len();
    let mut wins = 0usize;
    let mut total_r = 0.0_f64;
    let mut count = 0usize;
    // Match full_strategy_pipeline canonical loop start (line 186): starts at bar 40.
    // This preserves exact baseline behavior when ss=20, sl=50, vt=1.3, eo=8.
    if n <= 40 + exit_offset {
        return (0, 0, 0.0);
    }
    for i in 40..n.saturating_sub(exit_offset) {
        let sma_val_short = sma(&bars[..=i], sma_short);
        let sma_val_long = sma(&bars[..=i], sma_long);
        let avg_vol = avg_vol_window(bars, i, 10);
        if avg_vol <= 0.0 {
            continue;
        }
        let vol_ratio = bars[i].volume as f64 / avg_vol;
        let atr_val = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 {
            continue;
        }
        let exit = bars[i + exit_offset].close;
        if bars[i].close > sma_val_short
            && sma_val_short > sma_val_long
            && vol_ratio > vol_ratio_threshold
        {
            let r = (exit - bars[i].close) / atr_val;
            total_r += r;
            if r > 0.0 {
                wins += 1;
            }
            count += 1;
        } else if bars[i].close < sma_val_short
            && sma_val_short < sma_val_long
            && vol_ratio > vol_ratio_threshold
        {
            let r = (bars[i].close - exit) / atr_val;
            total_r += r;
            if r > 0.0 {
                wins += 1;
            }
            count += 1;
        }
    }
    (count, wins, total_r)
}

fn wq_vol_regime(
    bars: &[Bar],
    short_lookback: usize,
    long_lookback: usize,
    short_threshold: f64,
    long_threshold: f64,
    exit_offset: usize,
) -> (usize, usize, f64) {
    let n = bars.len();
    let mut wins = 0usize;
    let mut total_r = 0.0_f64;
    let mut count = 0usize;
    let start = long_lookback.max(short_lookback).max(14).max(30);
    if n <= start + exit_offset {
        return (0, 0, 0.0);
    }
    for i in start..n.saturating_sub(exit_offset) {
        let short_vol = bars[i - short_lookback..i]
            .iter()
            .map(|b| b.high - b.low)
            .sum::<f64>()
            / short_lookback as f64;
        let long_vol = bars[i - long_lookback..i]
            .iter()
            .map(|b| b.high - b.low)
            .sum::<f64>()
            / long_lookback as f64;
        if long_vol <= 0.0 {
            continue;
        }
        let vol_ratio = short_vol / long_vol;
        let atr_val = bars[i - 14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 {
            continue;
        }
        let exit = bars[i + exit_offset].close;
        if vol_ratio > short_threshold {
            let r = (bars[i].close - exit) / atr_val;
            total_r += r;
            if r > 0.0 {
                wins += 1;
            }
            count += 1;
        } else if vol_ratio < long_threshold {
            let r = (exit - bars[i].close) / atr_val;
            total_r += r;
            if r > 0.0 {
                wins += 1;
            }
            count += 1;
        }
    }
    (count, wins, total_r)
}

fn report(strategy: &str, tf: &str, params: &str, count: usize, wins: usize, total_r: f64) {
    let wr = if count > 0 {
        wins as f64 / count as f64 * 100.0
    } else {
        0.0
    };
    let avg_r = if count > 0 {
        total_r / count as f64
    } else {
        0.0
    };
    println!(
        "RESULT|{}|{}|{}|{}|{}|{:.2}|{:.2}|{:.4}",
        strategy, tf, params, count, wins, wr, total_r, avg_r
    );
}

fn run_orb_breakout(bars: &[Bar], tf: &str) {
    for rw in [8usize, 10, 12, 14, 16, 20] {
        for vt in [1.3_f64, 1.5, 2.0] {
            for eo in [3usize, 5, 8] {
                let (c, w, tr) = orb_breakout(bars, rw, vt, eo);
                report(
                    "orb-breakout",
                    tf,
                    &format!("rw={rw},vt={vt:.1},eo={eo}"),
                    c,
                    w,
                    tr,
                );
            }
        }
    }
}

fn run_wq_trend_mom(bars: &[Bar], tf: &str) {
    for ss in [10usize, 15, 20, 30] {
        for sl in [30usize, 40, 50, 60] {
            for vt in [1.3_f64, 1.5] {
                for eo in [3usize, 5, 8] {
                    let (c, w, tr) = wq_trend_mom(bars, ss, sl, vt, eo);
                    report(
                        "wq-trend-mom",
                        tf,
                        &format!("ss={ss},sl={sl},vt={vt:.1},eo={eo}"),
                        c,
                        w,
                        tr,
                    );
                }
            }
        }
    }
}

fn run_wq_vol_regime(bars: &[Bar], tf: &str) {
    // The original full_strategy_pipeline wq-vol-regime exits at bar+5.
    let eo = 5usize;
    for slk in [5usize, 10, 15, 20] {
        for llk in [20usize, 30, 40, 50] {
            for st in [1.3_f64, 1.4, 1.5, 1.6, 1.7, 2.0] {
                for lt in [0.5_f64, 0.6, 0.7, 0.8, 0.9] {
                    let (c, w, tr) = wq_vol_regime(bars, slk, llk, st, lt, eo);
                    report(
                        "wq-vol-regime",
                        tf,
                        &format!("slk={slk},llk={llk},st={st:.1},lt={lt:.1},eo={eo}"),
                        c,
                        w,
                        tr,
                    );
                }
            }
        }
    }

    // Also include the previously observed robust candidate with eo=8 for continuity.
    let (c, w, tr) = wq_vol_regime(bars, 10, 20, 1.6, 0.8, 8);
    report(
        "wq-vol-regime",
        tf,
        "slk=10,llk=20,st=1.6,lt=0.8,eo=8",
        c,
        w,
        tr,
    );
}

fn timeframe_label(csv_path: &str) -> &'static str {
    if csv_path.contains("60m") {
        "60m"
    } else if csv_path.contains("30m") {
        "30m"
    } else if csv_path.contains("15m") {
        "15m"
    } else if csv_path.contains("5m") {
        "5m"
    } else if csv_path.contains("1d") {
        "daily"
    } else {
        "?"
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let csv_path = args
        .get(1)
        .map(|s| s.as_str())
        .unwrap_or("../data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-30m.csv");
    let target_symbol = args
        .iter()
        .position(|a| a == "--symbol")
        .and_then(|i| args.get(i + 1))
        .map(|s| s.as_str())
        .unwrap_or("NQ")
        .to_uppercase();
    let tf = timeframe_label(csv_path);

    let file = File::open(csv_path)?;
    let reader = BufReader::new(file);
    let mut by_symbol: HashMap<String, Vec<Bar>> = HashMap::new();
    for line in reader.lines().skip(1) {
        let line = line?;
        let parts: Vec<&str> = line.split(',').collect();
        if parts.len() >= 7 {
            let symbol = parts[1].trim().to_uppercase();
            if target_symbol == "ALL" || symbol == target_symbol {
                by_symbol.entry(symbol.clone()).or_default().push(Bar {
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

    println!("=== PARAM SWEEP RESULTS ===");
    println!("CSV: {csv_path}");
    println!("Symbol: {target_symbol}");
    println!("FORMAT: RESULT|strategy|tf|params|trades|wins|wr%|totalR|avgR");

    for (symbol, bars) in &by_symbol {
        eprintln!("--- {symbol} {tf} ({} bars) ---", bars.len());
        if (tf == "15m" || tf == "30m") && (target_symbol == "ALL" || symbol == &target_symbol) {
            run_orb_breakout(bars, tf);
        }
        if tf == "30m" && (target_symbol == "ALL" || symbol == &target_symbol) {
            run_wq_trend_mom(bars, tf);
        }
        if tf == "60m" && (target_symbol == "ALL" || symbol == &target_symbol) {
            run_wq_vol_regime(bars, tf);
            run_turtle_breakout(bars, tf);
        }
    }

    println!("=== END ===");
    Ok(())
}

fn run_turtle_breakout(bars: &[Bar], label: &str) {
    eprintln!("Sweeping turtle-breakout on {}...", label);
    for cl in &[30usize, 40, 50, 60] {
        let (c, w, tr) = turtle_breakout_test(bars, 200, *cl, 20, 2.0);
        if c > 0 {
            report("turtle-breakout", label, &format!("cl={}", cl), c, w, tr);
        }
    }
    for am in &[1.5f64, 2.0, 2.5] {
        let (c, w, tr) = turtle_breakout_test(bars, 200, 40, 20, *am);
        if c > 0 {
            report("turtle-breakout", label, &format!("am={}", am), c, w, tr);
        }
    }
    let (c, w, tr) = turtle_breakout_test(bars, 200, 40, 20, 2.0);
    if c > 0 {
        report("turtle-breakout", label, "cl40_am2.0", c, w, tr);
    }
}

fn turtle_breakout_test(
    bars: &[Bar],
    sma: usize,
    ch: usize,
    atr_p: usize,
    am: f64,
) -> (usize, usize, f64) {
    let n = bars.len();
    if n < sma + 8 {
        return (0, 0, 0.0);
    }
    let mut c = 0usize;
    let mut w = 0usize;
    let mut tr = 0.0_f64;
    for i in sma..n - 8 {
        let sma_val: f64 = bars[i - sma + 1..=i].iter().map(|b| b.close).sum::<f64>() / sma as f64;
        let mut h40 = f64::MIN;
        let mut l40 = f64::MAX;
        for j in (i - ch)..i {
            h40 = h40.max(bars[j].high);
            l40 = l40.min(bars[j].low);
        }
        // Exit channel also uses PRIOR bars only
        // ... (exit channel uses the same pattern in the exit loop below)
        let atr: f64 = bars[i - atr_p + 1..i]
            .iter()
            .map(|b| b.high - b.low)
            .sum::<f64>()
            / atr_p as f64;
        if atr <= 0.0 {
            continue;
        }
        let entry = bars[i].close;
        let (is_long, is_short) = (
            entry > sma_val && entry > h40,
            entry < sma_val && entry < l40,
        );
        if !is_long && !is_short {
            continue;
        }
        let mut exit_idx = (i + 8).min(n - 1);
        for j in (i + 1)..(i + 8).min(n) {
            let mut jh = f64::MIN;
            let mut jl = f64::MAX;
            for k in (j - ch)..j {
                jh = jh.max(bars[k].high);
                jl = jl.min(bars[k].low);
            }
            if is_long && bars[j].close < jl {
                exit_idx = j;
                break;
            }
            if is_short && bars[j].close > jh {
                exit_idx = j;
                break;
            }
        }
        let exit = bars[exit_idx].close;
        let r = if is_long {
            (exit - entry) / atr
        } else {
            (entry - exit) / atr
        };
        c += 1;
        if r > 0.0 {
            w += 1;
        }
        tr += r;
    }
    (c, w, tr)
}
