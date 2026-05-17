//! param_sweep.rs — Parameter optimization sweeps for top strategies
//!
//! USAGE: cargo run --bin param_sweep -- --csv <path> --symbol <SYM> --strategy <name>
//!   name: orb-breakout | wq-trend-mom | wq-vol-regime
//!
//! Sweeps all defined parameter combinations and reports results sorted by total R.

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

fn avg_vol(bars: &[Bar], idx: usize, window: usize) -> f64 {
    if idx < window || bars.len() < idx { return 0.0; }
    bars[idx-window..idx].iter().map(|b| b.volume as f64).sum::<f64>() / window as f64
}

fn atr(bars: &[Bar], idx: usize, period: usize) -> f64 {
    if idx < period { return 0.0; }
    bars[idx-period..idx].iter().map(|b| b.high - b.low).sum::<f64>() / period as f64
}

// === ORB BREAKOUT ===
fn run_orb_breakout(bars: &[Bar], range_window: usize, vol_threshold: f64, exit_offset: usize) -> Vec<Trade> {
    let mut trades = Vec::new();
    if bars.len() < range_window + exit_offset + 5 { return trades; }
    let n = bars.len();
    for i in range_window..n.saturating_sub(exit_offset + 2) {
        let range_high = bars[i-range_window..i].iter().map(|b| b.high).fold(0.0_f64, f64::max);
        let range_low = bars[i-range_window..i].iter().map(|b| b.low).fold(f64::MAX, f64::min);
        let range = range_high - range_low;
        if range <= 0.0 { continue; }
        let atr_val = atr(bars, i, 14);
        if atr_val <= 0.0 { continue; }
        let exit = bars[i+exit_offset].close;
        let vol_avg = avg_vol(bars, i, 10);
        if bars[i].close > range_high && bars[i].volume as f64 > vol_avg * vol_threshold {
            trades.push(Trade {
                strategy_id: format!("orb-breakout-r{}v{}e{}", range_window, vol_threshold, exit_offset),
                symbol: bars[i].symbol.clone(),
                side: "long".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
            });
        } else if bars[i].close < range_low && bars[i].volume as f64 > vol_avg * vol_threshold {
            trades.push(Trade {
                strategy_id: format!("orb-breakout-r{}v{}e{}", range_window, vol_threshold, exit_offset),
                symbol: bars[i].symbol.clone(),
                side: "short".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
            });
        }
    }
    trades
}

// === WQ TREND MOM ===
fn run_wq_trend_mom(bars: &[Bar], sma_short: usize, sma_long: usize, vol_threshold: f64, exit_offset: usize) -> Vec<Trade> {
    let mut trades = Vec::new();
    let min_bars = sma_long.max(40) + exit_offset + 2;
    if bars.len() < min_bars { return trades; }
    let n = bars.len();
    for i in sma_long..n.saturating_sub(exit_offset + 2) {
        let sma_s = sma(&bars[..=i], sma_short);
        let sma_l = sma(&bars[..=i], sma_long);
        let vol_avg = avg_vol(bars, i, 10);
        if vol_avg <= 0.0 { continue; }
        let vol_ratio = bars[i].volume as f64 / vol_avg;
        let atr_val = atr(bars, i, 14);
        if atr_val <= 0.0 { continue; }
        let exit = bars[i+exit_offset].close;
        if bars[i].close > sma_s && sma_s > sma_l && vol_ratio > vol_threshold {
            trades.push(Trade {
                strategy_id: format!("wq-trend-mom-s{}l{}v{}e{}", sma_short, sma_long, vol_threshold, exit_offset),
                symbol: bars[i].symbol.clone(),
                side: "long".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
            });
        } else if bars[i].close < sma_s && sma_s < sma_l && vol_ratio > vol_threshold {
            trades.push(Trade {
                strategy_id: format!("wq-trend-mom-s{}l{}v{}e{}", sma_short, sma_long, vol_threshold, exit_offset),
                symbol: bars[i].symbol.clone(),
                side: "short".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
            });
        }
    }
    trades
}

// === DAILY RANGE BREAKOUT (prev day high/low breakout) ===
fn run_daily_range_breakout(bars: &[Bar], exit_offset: usize, vol_mult: f64) -> Vec<Trade> {
    let mut trades = Vec::new();
    if bars.len() < 30 { return trades; }
    
    // Build daily levels (date -> (high, low))
    use std::collections::HashMap;
    let mut daily: HashMap<String, (f64, f64)> = HashMap::new();
    for b in bars {
        let date = if b.ts.len() >= 10 { b.ts[..10].to_string() } else { continue; };
        let entry = daily.entry(date).or_insert((f64::MIN, f64::MAX));
        entry.0 = entry.0.max(b.high);
        entry.1 = entry.1.min(b.low);
    }
    
    let dates: Vec<&String> = daily.keys().collect();
    if dates.len() < 2 { return trades; }
    
    let n = bars.len();
    let mut prev_high = 0.0f64;
    let mut prev_low = 0.0f64;
    
    for i in exit_offset + 5..n.saturating_sub(exit_offset + 2) {
        let date = if bars[i].ts.len() >= 10 { bars[i].ts[..10].to_string() } else { continue; };
        
        // Find previous day's levels
        if let Some(&(h, l)) = daily.get(&date) {
            // Find previous date's high/low
            let mut found_prev = false;
            for j in (0..dates.len()).rev() {
                if *dates[j] < date {
                    if let Some(&(ph, pl)) = daily.get(dates[j]) {
                        prev_high = ph;
                        prev_low = pl;
                        found_prev = true;
                    }
                    break;
                }
            }
            if !found_prev { continue; }
        } else {
            continue;
        }
        
        let avg_vol: f64 = bars[i-10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
        if avg_vol <= 0.0 { continue; }
        let atr_val = atr(bars, i, 14);
        if atr_val <= 0.0 { continue; }
        let exit = bars[i+exit_offset].close;
        
        // Breakout above prev day high with volume
        if bars[i].close > prev_high && bars[i].volume as f64 > avg_vol * vol_mult {
            trades.push(Trade {
                strategy_id: format!("daily-range-breakout-e{}v{}", exit_offset, vol_mult),
                symbol: bars[i].symbol.clone(),
                side: "long".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
            });
        } else if bars[i].close < prev_low && bars[i].volume as f64 > avg_vol * vol_mult {
            trades.push(Trade {
                strategy_id: format!("daily-range-breakout-e{}v{}", exit_offset, vol_mult),
                symbol: bars[i].symbol.clone(),
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
    let min_bars = long_lookback.max(30) + exit_offset + 5;
    if bars.len() < min_bars { return trades; }
    let n = bars.len();
    for i in long_lookback..n.saturating_sub(exit_offset + 2) {
        let short_vol: f64 = bars[i-short_lookback..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / short_lookback as f64;
        let long_vol: f64 = bars[i-long_lookback..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / long_lookback as f64;
        if long_vol <= 0.0 { continue; }
        let vol_ratio = short_vol / long_vol;
        let atr_val = atr(bars, i, 14);
        if atr_val <= 0.0 { continue; }
        let exit = bars[i+exit_offset].close;
        if vol_ratio > short_threshold {
            trades.push(Trade {
                strategy_id: format!("wq-vol-regime-s{}l{}S{}L{}e{}", short_lookback, long_lookback, short_threshold, long_threshold, exit_offset),
                symbol: bars[i].symbol.clone(),
                side: "short".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
            });
        } else if vol_ratio < long_threshold {
            trades.push(Trade {
                strategy_id: format!("wq-vol-regime-s{}l{}S{}L{}e{}", short_lookback, long_lookback, short_threshold, long_threshold, exit_offset),
                symbol: bars[i].symbol.clone(),
                side: "long".into(), entry: bars[i].close, exit,
                entry_ts: bars[i].ts.clone(), exit_ts: bars[i+exit_offset].ts.clone(),
                r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
            });
        }
    }
    trades
}

fn load_data(csv_path: &str, target_symbol: &str) -> Vec<Bar> {
    let file = File::open(csv_path).expect(&format!("Cannot open {}", csv_path));
    let reader = BufReader::new(file);
    let mut all_bars: Vec<Bar> = Vec::new();
    for line in reader.lines().skip(1) {
        let line = line.unwrap();
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
    all_bars
}

fn report(trades: &[Trade], label: &str) {
    if trades.is_empty() {
        println!("  {:40}: 0 trades", label);
        return;
    }
    let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
    let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
    let losses = trades.len() - wins;
    let wr = wins as f64 / trades.len() as f64 * 100.0;
    let avg_r = total_r / trades.len() as f64;
    println!("  {:40}: {:4} trades, {:3}/{:3} W/L ({:5.1}%), total R {:+7.2}, avg R {:+.3}",
        label, trades.len(), wins, losses, wr, total_r, avg_r);
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let csv_path = args.iter()
        .position(|a| a == "--csv")
        .and_then(|i| args.get(i+1))
        .map(|s| s.as_str())
        .unwrap_or("data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv");

    let target_symbol = args.iter()
        .position(|a| a == "--symbol")
        .and_then(|i| args.get(i+1))
        .map(|s| s.as_str())
        .unwrap_or("NQ");

    let strategy = args.iter()
        .position(|a| a == "--strategy")
        .and_then(|i| args.get(i+1))
        .map(|s| s.as_str())
        .unwrap_or("orb-breakout");

    println!("=== PARAM SWEEP ===");
    println!("Strategy: {}", strategy);
    println!("CSV: {}", csv_path);
    println!("Symbol: {}", target_symbol);
    println!();

    let bars = load_data(csv_path, target_symbol);
    println!("Loaded {} bars for {}\n", bars.len(), target_symbol);

    // Group bars by symbol for per-symbol reporting
    let mut by_symbol: HashMap<String, Vec<Bar>> = HashMap::new();
    for b in &bars {
        by_symbol.entry(b.symbol.clone()).or_default().push(b.clone());
    }

    let mut results: Vec<(String, f64, usize, f64)> = Vec::new(); // (label, total_r, trades, win_rate)

    match strategy {
        "orb-breakout" => {
            let range_windows = vec![8, 10, 12, 14, 16, 20];
            let vol_thresholds = vec![1.3, 1.5, 2.0];
            let exit_offsets = vec![3, 5, 8];
            let total_combos = range_windows.len() * vol_thresholds.len() * exit_offsets.len();
            println!("Running {} orb-breakout parameter combinations...\n", total_combos);

            for &rw in &range_windows {
                for &vt in &vol_thresholds {
                    for &eo in &exit_offsets {
                        let mut all_trades = Vec::new();
                        for (_sym, sbars) in &by_symbol {
                            all_trades.extend(run_orb_breakout(sbars, rw, vt, eo));
                        }
                        let label = format!("orb-r{}v{}e{}", rw, vt, eo);
                        let total_r: f64 = all_trades.iter().map(|t| t.r_multiple).sum();
                        let wins = all_trades.iter().filter(|t| t.r_multiple > 0.0).count();
                        let wr = if all_trades.is_empty() { 0.0 } else { wins as f64 / all_trades.len() as f64 * 100.0 };
                        report(&all_trades, &label);
                        results.push((label, total_r, all_trades.len(), wr));
                    }
                }
            }
        }
        "wq-trend-mom" => {
            let sma_shorts = vec![10, 15, 20, 30];
            let sma_longs = vec![30, 40, 50, 60];
            let vol_thresholds = vec![1.3, 1.5];
            let exit_offsets = vec![3, 5, 8];
            let total_combos = sma_shorts.len() * sma_longs.len() * vol_thresholds.len() * exit_offsets.len();
            println!("Running {} wq-trend-mom parameter combinations...\n", total_combos);

            for &ss in &sma_shorts {
                for &sl in &sma_longs {
                    if ss >= sl { continue; } // short must be < long
                    for &vt in &vol_thresholds {
                        for &eo in &exit_offsets {
                            let mut all_trades = Vec::new();
                            for (_sym, sbars) in &by_symbol {
                                all_trades.extend(run_wq_trend_mom(sbars, ss, sl, vt, eo));
                            }
                            let label = format!("trend-s{}l{}v{}e{}", ss, sl, vt, eo);
                            let total_r: f64 = all_trades.iter().map(|t| t.r_multiple).sum();
                            let wins = all_trades.iter().filter(|t| t.r_multiple > 0.0).count();
                            let wr = if all_trades.is_empty() { 0.0 } else { wins as f64 / all_trades.len() as f64 * 100.0 };
                            report(&all_trades, &label);
                            results.push((label, total_r, all_trades.len(), wr));
                        }
                    }
                }
            }
        }
        "wq-vol-regime" => {
            let short_lookbacks = vec![5, 10, 15, 20];
            let long_lookbacks = vec![20, 30, 40, 50];
            let short_thresholds = vec![1.3, 1.4, 1.5, 1.6, 1.7, 2.0];
            let long_thresholds = vec![0.5, 0.6, 0.7, 0.8, 0.9];
            let exit_offset = 5; // hold constant for vol regime
            let total_combos = short_lookbacks.len() * long_lookbacks.len() * short_thresholds.len() * long_thresholds.len();
            println!("Running {} wq-vol-regime parameter combinations...\n", total_combos);

            for &sl in &short_lookbacks {
                for &ll in &long_lookbacks {
                    if sl >= ll { continue; } // short lookback must be < long
                    for &st in &short_thresholds {
                        for &lt in &long_thresholds {
                            let mut all_trades = Vec::new();
                            for (_sym, sbars) in &by_symbol {
                                all_trades.extend(run_wq_vol_regime(sbars, sl, ll, st, lt, exit_offset));
                            }
                            let label = format!("volreg-s{}l{}S{}L{}", sl, ll, st, lt);
                            let total_r: f64 = all_trades.iter().map(|t| t.r_multiple).sum();
                            let wins = all_trades.iter().filter(|t| t.r_multiple > 0.0).count();
                            let wr = if all_trades.is_empty() { 0.0 } else { wins as f64 / all_trades.len() as f64 * 100.0 };
                            report(&all_trades, &label);
                            results.push((label, total_r, all_trades.len(), wr));
                        }
                    }
                }
            }
        }
        "daily-range-breakout" => {
            let exit_offsets = vec![5, 8, 10];
            let vol_mults = vec![1.0, 1.3, 1.5, 2.0];
            let total_combos = exit_offsets.len() * vol_mults.len();
            println!("Running {} daily-range-breakout parameter combinations...\n", total_combos);

            for &eo in &exit_offsets {
                for &vm in &vol_mults {
                    let mut all_trades = Vec::new();
                    for (_sym, sbars) in &by_symbol {
                        all_trades.extend(run_daily_range_breakout(sbars, eo, vm));
                    }
                    let label = format!("drb-e{}v{}", eo, vm);
                    let total_r: f64 = all_trades.iter().map(|t| t.r_multiple).sum();
                    let wins = all_trades.iter().filter(|t| t.r_multiple > 0.0).count();
                    let wr = if all_trades.is_empty() { 0.0 } else { wins as f64 / all_trades.len() as f64 * 100.0 };
                    report(&all_trades, &label);
                    results.push((label, total_r, all_trades.len(), wr));
                }
            }
        }
        _ => {
            eprintln!("Unknown strategy: {}. Use: orb-breakout | wq-trend-mom | wq-vol-regime | daily-range-breakout", strategy);
            return;
        }
    }

    // Sort by total R descending, print top 10
    results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    println!("\n{}", "=".repeat(90));
    println!("TOP 10 PARAMETER SETS (by total R):");
    println!("{}", "=".repeat(90));
    println!("  {:40} {:>10} {:>8} {:>10}", "Parameters", "Total R", "Trades", "WinRate");
    println!("  {}", "-".repeat(72));
    for (label, total_r, trades, wr) in results.iter().take(10) {
        println!("  {:40} {:>+10.2} {:>8} {:>9.1}%", label, total_r, trades, wr);
    }
}
