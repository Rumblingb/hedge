use serde::{Deserialize, Serialize};

/// A single OHLCV bar — matches the TypeScript `Bar` interface
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Bar {
    pub ts: String,
    pub symbol: String,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

/// Load bars from a CSV file. Expects columns: ts,symbol,open,high,low,close,volume
pub fn load_bars_csv(path: &str) -> anyhow::Result<Vec<Bar>> {
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(true)
        .from_path(path)?;
    let mut bars = Vec::new();
    for result in reader.deserialize() {
        let bar: Bar = result?;
        bars.push(bar);
    }
    Ok(bars)
}

/// Group bars by symbol, preserving chronological order
pub fn group_by_symbol(bars: &[Bar]) -> Vec<(String, Vec<&Bar>)> {
    let mut groups: std::collections::BTreeMap<String, Vec<&Bar>> =
        std::collections::BTreeMap::new();
    for bar in bars {
        groups.entry(bar.symbol.clone()).or_default().push(bar);
    }
    groups.into_iter().collect()
}

/// A trade signal — matches the TypeScript `StrategySignal` interface
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Signal {
    pub symbol: String,
    pub strategy_id: String,
    pub side: String, // "long" or "short"
    pub entry: f64,
    pub stop: f64,
    pub target: f64,
    pub rr: f64,
    pub confidence: f64,
    pub contracts: u32,
    pub max_hold_minutes: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BacktestTrade {
    pub id: String,
    pub symbol: String,
    pub strategy_id: String,
    pub side: String,
    pub entry_ts: String,
    pub exit_ts: String,
    pub entry_price: f64,
    pub exit_price: f64,
    pub exit_reason: String, // "stop" | "target" | "timeout" | "flat_cutoff"
    pub pnl_points: f64,
    pub gross_r: f64,
    pub net_r: f64,
    pub status: String, // "closed"
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BacktestResult {
    pub trades: Vec<BacktestTrade>,
    pub total_trades: u32,
    pub wins: u32,
    pub losses: u32,
    pub win_rate: f64,
    pub total_r: f64,
    pub average_r: f64,
    pub max_drawdown_r: f64,
    pub profit_factor: f64,
}
