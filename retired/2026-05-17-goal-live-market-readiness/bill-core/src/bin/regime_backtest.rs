//! regime_backtest.rs — Test regime-aware orb-breakout against daily data
use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader};
use bill_core::regime_detector::{detect_regime, FOMC_PARAMS, NORMAL_PARAMS, EXPIRY_PARAMS};

#[derive(Debug, Clone)]
struct Bar { ts: String, open: f64, high: f64, low: f64, close: f64, volume: u64 }

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let csv_path = args.get(1).expect("Usage: regime_backtest <csv>");

    let file = File::open(csv_path)?;
    let reader = BufReader::new(file);
    let mut bars: Vec<Bar> = Vec::new();

    for line in reader.lines().skip(1) {
        let line = line?;
        let parts: Vec<&str> = line.split(',').collect();
        if parts.len() >= 7 {
            bars.push(Bar {
                ts: parts[0].trim().to_string(),
                open: parts[2].parse().unwrap_or(0.0),
                high: parts[3].parse().unwrap_or(0.0),
                low: parts[4].parse().unwrap_or(0.0),
                close: parts[5].parse().unwrap_or(0.0),
                volume: parts[6].parse::<u64>().unwrap_or(0),
            });
        }
    }

    println!("Loaded {} bars from {}", bars.len(), csv_path);

    // Track regimes detected
    let mut fomc_days = 0;
    let mut expiry_days = 0;
    let mut normal_days = 0;
    let mut highvol_days = 0;

    for bar in &bars {
        let date = &bar.ts[..10];
        let (regime, params) = detect_regime(date, None, None);
        match regime {
            bill_core::regime_detector::MarketRegime::FOMC => {
                fomc_days += 1;
                println!("  {} → FOMC (exit={}, vol_threshold={})", date, params.exit_offset, params.orb_vol_threshold);
            }
            bill_core::regime_detector::MarketRegime::OptionsExpiry => {
                expiry_days += 1;
                if expiry_days <= 3 {
                    println!("  {} → EXPIRY (exit={})", date, params.exit_offset);
                }
            }
            bill_core::regime_detector::MarketRegime::HighVol => highvol_days += 1,
            _ => normal_days += 1,
        }
    }

    println!("\n=== REGIME SUMMARY ===");
    println!("Normal days:     {}", normal_days);
    println!("FOMC days:       {}", fomc_days);
    println!("Expiry days:     {}", expiry_days);
    println!("High vol days:   {}", highvol_days);
    println!("Total bars:      {}", bars.len());

    Ok(())
}

