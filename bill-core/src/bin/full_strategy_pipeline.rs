//! full_strategy_pipeline.rs — Run ALL Rust strategies on ALL symbols in a CSV.
//! Tests: wq-alpha-009, wq-alpha-001, wq-alpha-012 + 10 gold strategies
//! Uses time-based exit (bar+N close) for all strategies.
//!
//! USAGE: cargo run --bin full_strategy_pipeline -- <csv_path>

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

fn atr(bars: &[Bar], period: usize) -> f64 {
    if bars.len() < period { return 0.0; }
    bars[bars.len()-period..].iter().map(|b| b.high - b.low).sum::<f64>() / period as f64
}

fn sma(bars: &[Bar], period: usize) -> f64 {
    if bars.len() < period { return 0.0; }
    bars[bars.len()-period..].iter().map(|b| b.close).sum::<f64>() / period as f64
}

fn run_strategy(bars: &[Bar], sid: &str) -> Vec<Trade> {
    let mut trades = Vec::new();
    if bars.len() < 50 { return trades; }
    let n = bars.len();

    match sid {
        // === WQ ALPHA 009: Volume spike fade at price extremes ===
        "wq-alpha-009" => {
            for i in 30..n {
                let avg_vol: f64 = bars[i-20..i].iter().map(|b| b.volume as f64).sum::<f64>() / 20.0;
                let price_range = bars[i-20..i].iter().fold(0.0_f64, |acc, b| acc.max(b.high - b.low)) / 2.0;
                if price_range <= 0.0 { continue; }
                let spike_vol = bars[i].volume as f64 > avg_vol * 1.8;
                if !spike_vol { continue; }
                let exit_idx = (i+5).min(n-1);
                let exit = bars[exit_idx].close;

                if bars[i].close > bars[i].high - price_range * 0.3 {
                    let rr = (bars[i].close - exit) / (bars[i].high + price_range * 0.5 - bars[i].close);
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[exit_idx].ts.clone(),
                        r_multiple: rr, contracts: 1,
                    });
                } else if bars[i].close < bars[i].low + price_range * 0.3 {
                    let rr = (exit - bars[i].close) / (bars[i].close - (bars[i].low - price_range * 0.5));
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[exit_idx].ts.clone(),
                        r_multiple: rr, contracts: 1,
                    });
                }
            }
        }

        // === WQ ALPHA 001: 3-bar momentum with volume confirmation ===
        "wq-alpha-001" => {
            for i in 20..n-3 {
                let roc = (bars[i].close - bars[i-3].close) / bars[i-3].close;
                let avg_vol: f64 = bars[i-10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+3].close;
                if roc > 0.001 && bars[i].volume as f64 > avg_vol * 1.2 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+3].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if roc < -0.001 && bars[i].volume as f64 > avg_vol * 1.2 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+3].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        // === WQ ALPHA 012: Vol-regime breakout ===
        "wq-alpha-012" => {
            for i in 120..n-5 {
                let recent_vol: f64 = bars[i-20..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / 20.0;
                let hist_vol: f64 = bars[i-120..i-20].iter().map(|b| (b.high - b.low)).sum::<f64>() / 100.0;
                if hist_vol <= 0.0 { continue; }
                let vol_ratio = recent_vol / hist_vol;
                let avg_vol: f64 = bars[i-10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
                let exit = bars[i+5].close;
                if vol_ratio < 0.6 && bars[i].volume as f64 > avg_vol * 1.5 {
                    let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                    if atr_val <= 0.0 { continue; }
                    if bars[i].close > sma(&bars[..=i], 20) {
                        trades.push(Trade {
                            strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                            side: "long".into(), entry: bars[i].close, exit,
                            entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                            r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                        });
                    } else {
                        trades.push(Trade {
                            strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                            side: "short".into(), entry: bars[i].close, exit,
                            entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                            r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                        });
                    }
                }
            }
        }

        // === GOLD: Larry Williams Donchian Breakout (20-bar) ===
        "lw-donchian" => {
            for i in 20..n-5 {
                let mut highest = bars[i].high;
                let mut lowest = bars[i].low;
                for j in (i-19)..=i {
                    highest = highest.max(bars[j].high);
                    lowest = lowest.min(bars[j].low);
                }
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+5].close;
                if bars[i].close >= highest {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if bars[i].close <= lowest {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        // === GOLD: Gapper Edge — fade gap > 2% ===
        "gapper-edge" => {
            for i in 3..n-3 {
                let gap = (bars[i].open - bars[i-1].close) / bars[i-1].close;
                if gap.abs() <= 0.02 { continue; }
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+3].close;
                if gap > 0.0 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].open, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+3].ts.clone(),
                        r_multiple: (bars[i].open - exit) / atr_val, contracts: 1,
                    });
                } else {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].open, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+3].ts.clone(),
                        r_multiple: (exit - bars[i].open) / atr_val, contracts: 1,
                    });
                }
            }
        }

        // === GOLD: WQ Trend Momentum ===
        "wq-trend-mom" => {
            for i in 40..n-5 {
                let sma20 = sma(&bars[..=i], 20);
                let sma50 = sma(&bars[..=i], 50);
                let avg_vol: f64 = bars[i-10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
                if avg_vol <= 0.0 { continue; }
                let vol_ratio = bars[i].volume as f64 / avg_vol;
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+5].close;
                if bars[i].close > sma20 && sma20 > sma50 && vol_ratio > 1.3 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if bars[i].close < sma20 && sma20 < sma50 && vol_ratio > 1.3 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        // === GOLD: WQ Volatility Regime ===
        "wq-vol-regime" => {
            for i in 30..n-5 {
                let short_vol: f64 = bars[i-10..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / 10.0;
                let long_vol: f64 = bars[i-30..i].iter().map(|b| (b.high - b.low)).sum::<f64>() / 30.0;
                if long_vol <= 0.0 { continue; }
                let vol_ratio = short_vol / long_vol;
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+5].close;
                if vol_ratio > 1.5 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                } else if vol_ratio < 0.7 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                }
            }
        }

        // === GOLD: VGRSI Strategy (Rak arXiv:2605.01300) ===
        "vgrsi" => {
            for i in 30..n-5 {
                let gains: f64 = bars[i-14..i].iter().map(|b| b.close.max(b.open) - b.open).filter(|&d| d > 0.0).sum();
                let losses: f64 = bars[i-14..i].iter().map(|b| b.open - b.close.min(b.open)).filter(|&d| d > 0.0).sum();
                if losses == 0.0 && gains == 0.0 { continue; }
                let rs = if losses > 0.0 { gains / losses } else { 2.0 };
                let rsi = 100.0 - (100.0 / (1.0 + rs));
                let vol_ratio = (bars[i].high - bars[i].low) / bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() * 14.0;
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+5].close;
                if rsi < 35.0 && vol_ratio > 1.2 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if rsi > 65.0 && vol_ratio > 1.2 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        // === GOLD: WQ Momentum Reversal (RSI-based) ===
        "wq-mom-rev" => {
            for i in 20..n-5 {
                let gains: f64 = bars[i-14..i].iter().map(|b| (b.close - b.open).max(0.0)).sum();
                let losses: f64 = bars[i-14..i].iter().map(|b| (b.open - b.close).max(0.0)).sum();
                if losses == 0.0 && gains == 0.0 { continue; }
                let rs = if losses > 0.0 { gains / losses } else { 2.0 };
                let rsi = 100.0 - (100.0 / (1.0 + rs));
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+5].close;
                if rsi < 25.0 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if rsi > 75.0 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        // === GOLD: Volume Imbalance Signal (Cartea SSRN) ===
        "vol-imbalance" => {
            for i in 15..n-5 {
                let up_vol: f64 = bars[i-10..i].iter().map(|b| if b.close > b.open { b.volume as f64 } else { 0.0 }).sum();
                let dn_vol: f64 = bars[i-10..i].iter().map(|b| if b.close < b.open { b.volume as f64 } else { 0.0 }).sum();
                if up_vol + dn_vol <= 0.0 { continue; }
                let imb = (up_vol - dn_vol) / (up_vol + dn_vol);
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+5].close;
                if imb > 0.6 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if imb < -0.6 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        // === GOLD: Opening Range Breakout (Zarattini SSRN) ===
        "orb-breakout" => {
            for i in 14..n-5 {
                let range_high = bars[0..12].iter().map(|b| b.high).fold(0.0_f64, f64::max);
                let range_low = bars[0..12].iter().map(|b| b.low).fold(f64::MAX, f64::min);
                let range = range_high - range_low;
                if range <= 0.0 { continue; }
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+5].close;
                if bars[i].close > range_high && bars[i].volume as f64 > avg_vol_window(bars, i, 10) * 1.3 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if bars[i].close < range_low && bars[i].volume as f64 > avg_vol_window(bars, i, 10) * 1.3 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        // === GOLD: Volume Reversal (Jegadeesh & Wu) ===
        "vol-reversal" => {
            for i in 30..n-5 {
                let avg_vol: f64 = bars[i-20..i].iter().map(|b| b.volume as f64).sum::<f64>() / 20.0;
                if avg_vol <= 0.0 { continue; }
                let vol_ratio = bars[i].volume as f64 / avg_vol;
                let ret = (bars[i].close - bars[i-5].close) / bars[i-5].close;
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+5].close;
                if ret > 0.02 && vol_ratio > 2.0 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                } else if ret < -0.02 && vol_ratio > 2.0 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                }
            }
        }

        // === GOLD: Weekly Nasdaq Strategy ===
        "weekly-nq" => {
            for i in 14..n-5 {
                let week_open = bars[i-5].open;
                let week_ret = (bars[i].close - week_open) / week_open;
                let avg_vol: f64 = bars[i-5..i].iter().map(|b| b.volume as f64).sum::<f64>() / 5.0;
                let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
                if atr_val <= 0.0 { continue; }
                let exit = bars[i+5].close;
                if week_ret < -0.02 && bars[i].volume as f64 > avg_vol * 1.5 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "long".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (exit - bars[i].close) / atr_val, contracts: 1,
                    });
                } else if week_ret > 0.02 && bars[i].volume as f64 > avg_vol * 1.5 {
                    trades.push(Trade {
                        strategy_id: sid.into(), symbol: bars[i].symbol.clone(),
                        side: "short".into(), entry: bars[i].close, exit,
                        entry_ts: bars[i].ts.clone(), exit_ts: bars[i+5].ts.clone(),
                        r_multiple: (bars[i].close - exit) / atr_val, contracts: 1,
                    });
                }
            }
        }

        _ => {}
    }
    trades
}

fn avg_vol_window(bars: &[Bar], idx: usize, window: usize) -> f64 {
    if idx < window || bars.len() < idx { return 0.0; }
    bars[idx-window..idx].iter().map(|b| b.volume as f64).sum::<f64>() / window as f64
}

fn report(trades: &[Trade], label: &str) -> (usize, f64) {
    if trades.is_empty() { return (0, 0.0); }
    let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
    let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
    let losses = trades.iter().filter(|t| t.r_multiple <= 0.0).count();
    let total = trades.len();
    let wr = if total > 0 { wins as f64 / total as f64 * 100.0 } else { 0.0 };
    println!("  {}: {} trades, {}/{} W/L ({:.1}%), total R {:.2}", label, total, wins, losses, wr, total_r);
    (total, total_r)
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

    let mut by_symbol: HashMap<String, Vec<Bar>> = HashMap::new();
    for b in all_bars {
        by_symbol.entry(b.symbol.clone()).or_default().push(b);
    }

    let strategies = ["wq-alpha-009", "wq-alpha-001", "wq-alpha-012",
        "lw-donchian", "gapper-edge", "wq-trend-mom", "wq-vol-regime",
        "vgrsi", "wq-mom-rev", "vol-imbalance", "orb-breakout",
        "vol-reversal", "weekly-nq"];

    println!("=== FULL STRATEGY PIPELINE ===");
    println!("CSV: {}", csv_path);
    println!("Strategies: {}", strategies.join(", "));
    println!("Symbols: {}", by_symbol.keys().cloned().collect::<Vec<_>>().join(", "));
    println!();

    let mut grand_total = 0;
    let mut grand_pnl = 0.0_f64;

    for (symbol, bars) in &by_symbol {
        println!("-- {} ({} bars) --", symbol, bars.len());
        let mut all_strat_trades: Vec<Trade> = Vec::new();

        for sid in &strategies {
            let trades = run_strategy(bars, sid);
            let (cnt, total_r) = report(&trades, sid);
            all_strat_trades.extend(trades);
            grand_total += cnt;
        }

        // Priority filter: at most 1 trade per 2 bars
        all_strat_trades.sort_by(|a, b| a.entry_ts.cmp(&b.entry_ts));
        let mut filtered = Vec::new();
        let mut last_idx: usize = 0;
        for t in &all_strat_trades {
            let idx = bars.iter().position(|b| b.ts == t.entry_ts).unwrap_or(0);
            if idx >= last_idx + 2 {
                filtered.push(t.clone());
                last_idx = idx;
            }
        }

        let fcnt = filtered.len();
        if fcnt > 0 {
            let fpnl: f64 = filtered.iter().map(|t| t.r_multiple).sum();
            let fwins = filtered.iter().filter(|t| t.r_multiple > 0.0).count();
            let fwr = fwins as f64 / fcnt as f64 * 100.0;
            let avg_risk = filtered.iter().map(|t| (t.entry - t.exit).abs()).sum::<f64>() / fcnt as f64;
            let point_val = if symbol == "NQ" { 20.0 } else if symbol == "ES" { 50.0 } else { 10.0 };
            let gross = fpnl * avg_risk * point_val;
            let net = gross - fcnt as f64 * 5.0;
            println!("  COMBINED (filtered): {} trades, {}/{} W/L ({:.1}% WR), PnL +${:.0}", fcnt, fwins, fcnt-fwins, fwr, net);
            grand_pnl += net;
        }
        println!();
    }

    println!("=== GRAND TOTAL ===");
    println!("All trades: {}, Net PnL: +${:.0}", grand_total, grand_pnl);
    Ok(())
}
