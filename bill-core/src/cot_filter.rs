// cot_filter.rs — COT (Commitment of Traders) positioning regime filter.
//
// Uses weekly CFTC Traders in Financial Futures (TFF) report data
// to detect extreme institutional positioning for ES and NQ futures.
// Contrarian signal: fade extreme commercial/dealer positioning.

use std::collections::HashMap;

/// COT record for a single market on a single date
#[derive(Debug, Clone)]
pub struct CotRecord {
    pub report_date: String, // YYYY-MM-DD
    pub market_name: String,
    pub open_interest: f64,
    pub dealer_long: f64,
    pub dealer_short: f64,
    pub asset_mgr_long: f64,
    pub asset_mgr_short: f64,
    pub lev_money_long: f64,
    pub lev_money_short: f64, // leveraged money = hedge funds
}

impl CotRecord {
    /// Net dealer (commercial) position as % of open interest
    pub fn dealer_net_pct(&self) -> f64 {
        if self.open_interest <= 0.0 {
            0.0
        } else {
            (self.dealer_long - self.dealer_short) / self.open_interest
        }
    }

    /// Net asset manager position
    pub fn asset_mgr_net_pct(&self) -> f64 {
        if self.open_interest <= 0.0 {
            0.0
        } else {
            (self.asset_mgr_long - self.asset_mgr_short) / self.open_interest
        }
    }

    /// Net leveraged money (hedge fund) position
    pub fn lev_money_net_pct(&self) -> f64 {
        if self.open_interest <= 0.0 {
            0.0
        } else {
            (self.lev_money_long - self.lev_money_short) / self.open_interest
        }
    }
}

/// COT positioning signal
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum CotSignal {
    /// Dealer positioning extremely bearish (dealers very short → fade short → be long)
    Bullish,
    /// Dealer positioning moderate — no strong signal
    Neutral,
    /// Dealer positioning extremely bullish (dealers very long → fade long → be short)
    Bearish,
}

/// Detect regime from a history of COT records for a single market.
/// Uses z-score of dealer net positioning over the lookback period.
/// Contrarian logic: when dealers are extremely net short, the market tends to reverse up.
pub fn detect_cot_regime(records: &[CotRecord], lookback: usize) -> CotSignal {
    if records.len() < 4 {
        return CotSignal::Neutral;
    }

    let window = &records[records.len().saturating_sub(lookback)..];
    let net_pcts: Vec<f64> = window.iter().map(|r| r.dealer_net_pct()).collect();
    let n = net_pcts.len() as f64;

    let mean: f64 = net_pcts.iter().sum::<f64>() / n;
    let variance: f64 = if n > 1.0 {
        net_pcts.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / (n - 1.0)
    } else {
        0.0
    };
    let std = variance.sqrt().max(0.0001);
    let current = *net_pcts.last().unwrap_or(&0.0);
    let z = (current - mean) / std;

    // Contrarian: extreme dealer positioning → fade
    if z > 2.0 {
        CotSignal::Bearish // Dealers extremely long → fade for short
    } else if z < -2.0 {
        CotSignal::Bullish // Dealers extremely short → fade for long
    } else if z > 1.5 {
        CotSignal::Bearish // Moderate overextension
    } else if z < -1.5 {
        CotSignal::Bullish
    } else {
        CotSignal::Neutral
    }
}

/// Quick COT regime from just the latest record and historical context.
/// Returns a position sizing multiplier for the given market.
pub fn cot_position_multiplier(latest: &CotRecord, history: &[CotRecord], lookback: usize) -> f64 {
    match detect_cot_regime(history, lookback) {
        CotSignal::Bullish => 1.2, // Dealer short extreme → go long → size up
        CotSignal::Bearish => 0.8, // Dealer long extreme → go short → size down
        CotSignal::Neutral => 1.0,
    }
}

/// Parse COT TFF CSV lines into records for a specific market name.
pub fn parse_cot_csv(csv_content: &str, market_name: &str) -> Vec<CotRecord> {
    let mut records = Vec::new();

    for line in csv_content.lines().skip(1) {
        // skip header
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        // CSV with quotes — split by commas outside of quotes
        let fields: Vec<&str> = trimmed.split(',').map(|f| f.trim_matches('"')).collect();

        if fields.len() < 20 {
            continue;
        }
        let name = fields[0];
        if name != market_name {
            continue;
        }

        let report_date = fields[2].to_string();

        let parse_f64 = |idx: usize| -> f64 {
            if idx < fields.len() {
                fields[idx].parse::<f64>().unwrap_or(0.0)
            } else {
                0.0
            }
        };

        // TFF CSV format (from CFTC):
        // 0: Market_and_Exchange_Names
        // 2: Report_Date_as_YYYY-MM-DD
        // 7: Open_Interest_All
        // 8: Dealer_Positions_Long_All (TFF = "Dealer")
        // 9: Dealer_Positions_Short_All
        // 10: Dealer_Positions_Spread_All (ignored)
        // 11: Asset_Mgr_Positions_Long_All
        // 12: Asset_Mgr_Positions_Short_All
        // 14: Lev_Money_Positions_Long_All
        // 15: Lev_Money_Positions_Short_All

        records.push(CotRecord {
            report_date,
            market_name: name.to_string(),
            open_interest: parse_f64(7),
            dealer_long: parse_f64(8),
            dealer_short: parse_f64(9),
            asset_mgr_long: parse_f64(11),
            asset_mgr_short: parse_f64(12),
            lev_money_long: parse_f64(14),
            lev_money_short: parse_f64(15),
        });
    }

    records.sort_by(|a, b| a.report_date.cmp(&b.report_date));
    records
}

// ─── VIX Regime Quick Check ──────────────────────────────────────────

/// Check if a given VIX + VIX3M pair indicates steep contango (risk-on).
/// Returns: (regime_name, es_mult, nq_mult)
pub fn check_vix_regime(vix: f64, vix3m: f64) -> (&'static str, f64, f64) {
    if vix <= 0.0 || vix3m <= 0.0 {
        return ("no-data", 0.5, 0.5);
    }

    let slope = (vix3m - vix) / vix;

    if slope > 0.08 {
        ("steep-contango", 1.0, 0.8) // Risk-on: full ES, 80% NQ
    } else if slope > 0.03 {
        ("mild-contango", 0.8, 0.6)
    } else if slope < -0.08 {
        ("panic-backwardation", 0.3, 0.0) // Panic: no NQ
    } else if slope < -0.03 {
        ("mild-backwardation", 0.5, 0.2)
    } else {
        ("flat", 0.6, 0.5)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_es_records() -> Vec<CotRecord> {
        // 8 neutral + 4 extremely short weeks → z < -2
        let mut records = Vec::new();
        // 8 weeks: neutral
        for i in 0..8 {
            records.push(CotRecord {
                report_date: format!("2026-{:02}-01", i + 1),
                market_name: "E-MINI S&P 500".to_string(),
                open_interest: 2_000_000.0,
                dealer_long: 200_000.0,
                dealer_short: 200_000.0,
                asset_mgr_long: 500_000.0,
                asset_mgr_short: 300_000.0,
                lev_money_long: 200_000.0,
                lev_money_short: 400_000.0,
            });
        }
        // 4 weeks: massive short buildup
        for i in 0..4 {
            let short = 200_000.0 + (i as f64 + 1.0) * 400_000.0; // 600K, 1M, 1.4M, 1.8M
            records.push(CotRecord {
                report_date: format!("2026-{:02}-01", i + 9),
                market_name: "E-MINI S&P 500".to_string(),
                open_interest: 2_000_000.0,
                dealer_long: 200_000.0,
                dealer_short: short,
                asset_mgr_long: 500_000.0,
                asset_mgr_short: 300_000.0,
                lev_money_long: 200_000.0,
                lev_money_short: 400_000.0,
            });
        }
        // Last: net_pct = (200K - 1.8M) / 2M = -0.80 → z = -2.26
        records
    }

    #[test]
    fn test_cot_extreme_short_triggers_bullish() {
        let records = sample_es_records();
        let signal = detect_cot_regime(&records, 10);
        // Last record has dealers extremely short (z < -2)
        assert_eq!(signal, CotSignal::Bullish);
    }

    #[test]
    fn test_cot_neutral() {
        let mut records = Vec::new();
        for i in 0..10 {
            records.push(CotRecord {
                report_date: format!("{}", 2026_01_01 + i),
                market_name: "E-MINI S&P 500".to_string(),
                open_interest: 2_000_000.0,
                dealer_long: 200_000.0,
                dealer_short: 200_000.0, // Flat position
                asset_mgr_long: 500_000.0,
                asset_mgr_short: 300_000.0,
                lev_money_long: 200_000.0,
                lev_money_short: 400_000.0,
            });
        }
        assert_eq!(detect_cot_regime(&records, 10), CotSignal::Neutral);
    }

    #[test]
    fn test_vix_steep_contango() {
        let (name, es, nq) = check_vix_regime(17.19, 20.50);
        assert_eq!(name, "steep-contango");
        assert!((es - 1.0).abs() < 0.01);
        assert!((nq - 0.8).abs() < 0.01);
    }

    #[test]
    fn test_vix_panic() {
        let (name, _, nq) = check_vix_regime(35.0, 25.0);
        assert_eq!(name, "panic-backwardation");
        assert!((nq - 0.0).abs() < 0.01);
    }

    #[test]
    fn test_cot_position_multiplier() {
        let records = sample_es_records();
        let mult = cot_position_multiplier(records.last().unwrap(), &records, 10);
        assert!(mult > 1.0, "dealer short extreme → increase position size");
    }
}
