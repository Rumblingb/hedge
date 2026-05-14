//! param_sweep.rs — Parameter sweep for top 3 strategies on best timeframes
//!
//! USAGE: cargo run --bin param_sweep -- <csv_path> --symbol NQ
//!
//! Tests all parameter combinations for:
//!   1. orb-breakout on 15m (rw: 8,10,12,14,16,20 × vt: 1.3,1.5,2.0 × eo: 3,5,8)
//!   2. wq-trend-mom on 30m (ss: 10,15,20,30 × sl: 30,40,50,60 × vt: 1.3,1.5 × eo: 3,5,8)
//!   3. wq-vol-regime on 60m (sll: 5,10,15,20 × lll: 20,30,40,50 × st: 1.3,1.4,1.5,1.6,1.7,2.0 × lt: 0.5,0.6,0.7,0.8,0.9)

use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader};

#[derive(Debug, Clone)]
struct Bar {
    ts: String, symbol: String, open: f64, high: f64, low: f64, close: f64, volume: u64,
}

fn sma(bars: &[Bar], period: usize) -> f64 {
    if bars.len() < period { return 0.0; }
    bars[bars.len()-period..].iter().map(|b| b.close).sum::<f64>() / period as f64
}

fn avg_vol_window(bars: &[Bar], idx: usize, window: usize) -> f64 {
    if idx < window || bars.len() < idx { return 0.0; }
    bars[idx-window..idx].iter().map(|b| b.volume as f64).sum::<f64>() / window as f64
}

// === ORB BREAKOUT SWEEP ===
fn sweep_orb_breakout(bars: &[Bar], rw: usize, vt: f64, eo: usize) -> (usize, usize, usize, f64) {
    let n = bars.len();
    if n < 20 { return (0, 0, 0, 0.0); }
    let mut trades = 0usize;
    let mut wins = 0usize;
    let mut total_r = 0.0f64;

    // This implementation matches the original: uses first `rw` bars as the opening range
    let range_high = bars[0..rw].iter().map(|b| b.high).fold(0.0_f64, f64::max);
    let range_low = bars[0..rw].iter().map(|b| b.low).fold(f64::MAX, f64::min);
    let range = range_high - range_low;
    let start = (rw + 2).max(14);
    for i in start..(n - eo) {
        if range <= 0.0 { continue; }
        let atr_val: f64 = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 { continue; }
        let exit = bars[i+eo].close;
        let avg_vol = avg_vol_window(bars, i, 10);
        if bars[i].close > range_high && (bars[i].volume as f64) > avg_vol * vt {
            let r = (exit - bars[i].close) / atr_val;
            total_r += r;
            trades += 1;
            if r > 0.0 { wins += 1; }
        } else if bars[i].close < range_low && (bars[i].volume as f64) > avg_vol * vt {
            let r = (bars[i].close - exit) / atr_val;
            total_r += r;
            trades += 1;
            if r > 0.0 { wins += 1; }
        }
    }
    (trades, wins, trades - wins, total_r)
}

// === WQ TREND MOM SWEEP ===
fn sweep_wq_trend_mom(bars: &[Bar], ss: usize, sl: usize, vt: f64, eo: usize) -> (usize, usize, usize, f64) {
    let n = bars.len();
    if n < sl + 5 { return (0, 0, 0, 0.0); }
    let mut trades = 0usize;
    let mut wins = 0usize;
    let mut total_r = 0.0f64;

    for i in sl..(n - eo) {
        let sma_short = sma(&bars[..=i], ss);
        let sma_long = sma(&bars[..=i], sl);
        let avg_vol: f64 = bars[i-10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
        if avg_vol <= 0.0 { continue; }
        let vol_ratio = bars[i].volume as f64 / avg_vol;
        let atr_val: f64 = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 { continue; }
        let exit = bars[i+eo].close;
        if bars[i].close > sma_short && sma_short > sma_long && vol_ratio > vt {
            let r = (exit - bars[i].close) / atr_val;
            total_r += r;
            trades += 1;
            if r > 0.0 { wins += 1; }
        } else if bars[i].close < sma_short && sma_short < sma_long && vol_ratio > vt {
            let r = (bars[i].close - exit) / atr_val;
            total_r += r;
            trades += 1;
            if r > 0.0 { wins += 1; }
        }
    }
    (trades, wins, trades - wins, total_r)
}

// === WQ VOL REGIME SWEEP ===
fn sweep_wq_vol_regime(bars: &[Bar], short_lb: usize, long_lb: usize, short_th: f64, long_th: f64, eo: usize) -> (usize, usize, usize, f64) {
    let n = bars.len();
    if n < long_lb + 5 { return (0, 0, 0, 0.0); }
    if n <= eo { return (0, 0, 0, 0.0); }
    let mut trades = 0usize;
    let mut wins = 0usize;
    let mut total_r = 0.0f64;

    for i in long_lb..(n - eo) {
        let short_vol: f64 = bars[i-short_lb..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / short_lb as f64;
        let long_vol: f64 = bars[i-long_lb..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / long_lb as f64;
        if long_vol <= 0.0 { continue; }
        let vol_ratio = short_vol / long_vol;
        let atr_val: f64 = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 { continue; }
        let exit = bars[i+eo].close;
        if vol_ratio > short_th {
            let r = (bars[i].close - exit) / atr_val;
            total_r += r;
            trades += 1;
            if r > 0.0 { wins += 1; }
        } else if vol_ratio < long_th {
            let r = (exit - bars[i].close) / atr_val;
            total_r += r;
            trades += 1;
            if r > 0.0 { wins += 1; }
        }
    }
    (trades, wins, trades - wins, total_r)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let csv_path = args.get(1).map(|s| s.as_str()).unwrap_or("data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv");
    let target_symbol = args.iter().position(|a| a == "--symbol").and_then(|i| args.get(i+1)).map(|s| s.as_str()).unwrap_or("ALL");

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

    println!("=== PARAM SWEEP ===");
    println!("CSV: {}", csv_path);
    println!("Symbol: {}", target_symbol);
    println!("Bars: {}", all_bars.len());
    println!();

    // ============================
    // 1. ORB-BREAKOUT SWEEP
    // ============================
    println!("=== ORB-BREAKOUT SWEEP ===");
    println!("|  rw  |  vt  |  eo  | Trades |  W/L  |   WR   | Total R |");
    println!("|------|------|------|--------|-------|--------|---------|");
    let rw_values = [8usize, 10, 12, 14, 16, 20];
    let vt_values = [1.3f64, 1.5, 2.0];
    let eo_values = [3usize, 5, 8];
    let mut orb_results: Vec<(usize, f64, usize, usize, usize, f64)> = Vec::new();
    for &rw in &rw_values {
        for &vt in &vt_values {
            for &eo in &eo_values {
                let (t, w, l, tr) = sweep_orb_breakout(&all_bars, rw, vt, eo);
                if t > 0 {
                    let wr = w as f64 / t as f64 * 100.0;
                    orb_results.push((t, wr, w, l, eo, tr));
                    println!("| {:>4} | {:>4.1} | {:>4} | {:>6} | {:>3}/{:>3} | {:>5.1}% | {:>7.2}R |",
                             rw, vt, eo, t, w, l, wr, tr);
                }
            }
        }
    }
    // Sort by total R descending, show top 10
    orb_results.sort_by(|a, b| b.5.partial_cmp(&a.5).unwrap());
    println!();
    println!("### ORB-BREAKOUT TOP 10 ###");
    for (i, (t, wr, w, l, eo, tr)) in orb_results.iter().take(10).enumerate() {
        println!("  {}. {} trades, {}/{} {:.1}%, {:.2}R", i+1, t, w, l, wr, tr);
    }
    println!();

    // ============================
    // 2. WQ-TREND-MOM SWEEP
    // ============================
    println!("=== WQ-TREND-MOM SWEEP ===");
    println!("|  ss  |  sl  |  vt  |  eo  | Trades |  W/L  |   WR   | Total R |");
    println!("|------|------|------|------|--------|-------|--------|---------|");
    let ss_values = [10usize, 15, 20, 30];
    let sl_values = [30usize, 40, 50, 60];
    let vt_trend_values = [1.3f64, 1.5];
    let eo_trend_values = [3usize, 5, 8];
    let mut trend_results: Vec<(usize, usize, f64, usize, usize, usize, f64)> = Vec::new();
    for &ss in &ss_values {
        for &sl in &sl_values {
            for &vt in &vt_trend_values {
                for &eo in &eo_trend_values {
                    let (t, w, l, tr) = sweep_wq_trend_mom(&all_bars, ss, sl, vt, eo);
                    if t > 0 {
                        let wr = w as f64 / t as f64 * 100.0;
                        trend_results.push((ss, sl, vt, eo, t, w, tr));
                        println!("| {:>4} | {:>4} | {:>3.1} | {:>4} | {:>6} | {:>3}/{:>3} | {:>5.1}% | {:>7.2}R |",
                                 ss, sl, vt, eo, t, w, l, wr, tr);
                    }
                }
            }
        }
    }
    trend_results.sort_by(|a, b| b.6.partial_cmp(&a.6).unwrap());
    println!();
    println!("### WQ-TREND-MOM TOP 10 ###");
    for (i, (ss, sl, vt, eo, t, w, tr)) in trend_results.iter().take(10).enumerate() {
        let wr = *w as f64 / *t as f64 * 100.0;
        println!("  {}. ss={}, sl={}, vt={}, eo={}: {} trades, {:.1}%, {:.2}R",
                 i+1, ss, sl, vt, eo, t, wr, tr);
    }
    println!();

    // ============================
    // 3. WQ-VOL-REGIME SWEEP
    // ============================
    println!("=== WQ-VOL-REGIME SWEEP ===");
    println!("|  sll  |  lll  |  st  |  lt  |  eo  | Trades |  W/L  |   WR   | Total R |");
    println!("|-------|-------|------|------|------|--------|-------|--------|---------|");
    let sll_values = [5usize, 10, 15, 20];
    let lll_values = [20usize, 30, 40, 50];
    let st_values = [1.3f64, 1.4, 1.5, 1.6, 1.7, 2.0];
    let lt_values = [0.5f64, 0.6, 0.7, 0.8, 0.9];
    let eo_vol_values = [3usize, 5, 8];
    let mut vol_results: Vec<(usize, usize, f64, f64, usize, usize, usize, f64)> = Vec::new();
    for &sll in &sll_values {
        for &lll in &lll_values {
            for &st in &st_values {
                for &lt in &lt_values {
                    for &eo in &eo_vol_values {
                        let (t, w, l, tr) = sweep_wq_vol_regime(&all_bars, sll, lll, st, lt, eo);
                        if t > 0 {
                            let wr = w as f64 / t as f64 * 100.0;
                            vol_results.push((sll, lll, st, lt, eo, t, w, tr));
                            println!("| {:>5} | {:>5} | {:>3.1} | {:>3.1} | {:>4} | {:>6} | {:>3}/{:>3} | {:>5.1}% | {:>7.2}R |",
                                     sll, lll, st, lt, eo, t, w, l, wr, tr);
                        }
                    }
                }
            }
        }
    }
    vol_results.sort_by(|a, b| b.7.partial_cmp(&a.7).unwrap());
    println!();
    println!("### WQ-VOL-REGIME TOP 15 ###");
    for (i, (sll, lll, st, lt, eo, t, w, tr)) in vol_results.iter().take(15).enumerate() {
        let wr = *w as f64 / *t as f64 * 100.0;
        println!("  {}. sl={}, ll={}, st={}, lt={}, eo={}: {} trades, {:.1}%, {:.2}R",
                 i+1, sll, lll, st, lt, eo, t, wr, tr);
    }
    println!();

    // ============================
    // SUMMARY
    // ============================
    println!("=== SWEEP SUMMARY ===");
    println!("Total combos tested:");
    println!("  orb-breakout: {} combos", rw_values.len() * vt_values.len() * eo_values.len());
    println!("  wq-trend-mom: {} combos", ss_values.len() * sl_values.len() * vt_trend_values.len() * eo_trend_values.len());
    println!("  wq-vol-regime: {} combos", sll_values.len() * lll_values.len() * st_values.len() * lt_values.len() * eo_vol_values.len());

    if let Some(best) = orb_results.first() {
        println!();
        println!("🏆 BEST ORB-BREAKOUT: {:.2}R ({} trades, {:.1}% WR)", best.5, best.0, best.1);
    }
    if let Some(best) = trend_results.first() {
        println!("🏆 BEST WQ-TREND-MOM: ss={}, sl={}, vt={}, eo={} → {:.2}R ({} trades, {:.1}% WR)",
                 best.0, best.1, best.2, best.3, best.6, best.4, best.5 as f64 / best.4 as f64 * 100.0);
    }
    if let Some(best) = vol_results.first() {
        println!("🏆 BEST WQ-VOL-REGIME: sl={}, ll={}, st={}, lt={}, eo={} → {:.2}R ({} trades, {:.1}% WR)",
                 best.0, best.1, best.2, best.3, best.4, best.7, best.5, best.6 as f64 / best.5 as f64 * 100.0);
    }

    Ok(())
}
