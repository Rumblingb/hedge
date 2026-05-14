
use bill_core::types::{load_bars_csv, Bar};
use std::collections::HashMap;

fn get_session(hour: u32, min: u32) -> &'static str {
    let m = hour * 60 + min;
    if m < 180 { "asia" }
    else if m < 420 { "london" }
    else if m < 570 { "premarket" }
    else if m < 960 { "ny" }
    else if m < 1140 { "afterhours" }
    else { "asia" }
}

fn session_should_trade(session: &str) -> bool {
    matches!(session, "ny" | "asia" | "afterhours")
}

fn get_session_params(session: &str) -> (usize, f64, usize) {
    match session {
        "ny" => (12, 1.5, 8),      // w12_v1.5_e8: R+250, balanced long/short
        "asia" => (8, 1.3, 3),     // w8_v1.3_e3: fast scalps
        "afterhours" => (8, 1.3, 3), // same as asia
        _ => (0, 0.0, 0),           // don't trade
    }
}

fn run_session_orb(sg: &[&Bar], w: usize, v: f64, e: usize) -> Vec<(f64, String, String)> {
    let mut trades = Vec::new();
    if sg.len() < w + e + 20 { return trades; }
    let mut ss = 0;
    for si in 0..sg.len() {
        if si > 0 && sg[si].ts[..10] != sg[si-1].ts[..10] { ss = si; }
        if si - ss < w || si < e || si + e >= sg.len() { continue; }
        let range_high = sg[ss..ss+w].iter().map(|b| b.high).fold(0.0_f64, f64::max);
        let range_low = sg[ss..ss+w].iter().map(|b| b.low).fold(f64::MAX, f64::min);
        if range_high - range_low <= 0.0 { continue; }
        let avg_v = sg[si-10..si].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
        if avg_v <= 0.0 || sg[si].volume as f64 < avg_v * v { continue; }
        let atr = sg[si-14..si].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr <= 0.0 { continue; }
        let bar = sg[si];
        let ex = sg[si + e];
        let side; let rr;
        if bar.close > range_high { side = "long"; rr = (ex.close - bar.close) / atr; }
        else if bar.close < range_low { side = "short"; rr = (bar.close - ex.close) / atr; }
        else { continue; }
        trades.push((rr, side.to_string(), bar.symbol.clone()));
    }
    trades
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let path = args.get(1).expect("Usage: session_audit <csv>");
    let bars = load_bars_csv(path).expect("Failed");

    // Group by symbol then by session
    let mut all_trades: HashMap<String, Vec<(f64, String)>> = HashMap::new();
    let mut session_trades: HashMap<String, Vec<(f64, String)>> = HashMap::new();
    let mut skipped = 0;

    for sym in &["NQ", "ES"] {
        let sym_bars: Vec<&Bar> = bars.iter().filter(|b| b.symbol == *sym).collect();
        let mut daily_groups: HashMap<String, Vec<&Bar>> = HashMap::new();
        for b in &sym_bars {
            daily_groups.entry(b.ts[..10].to_string()).or_default().push(b);
        }

        for (date, day_bars) in &daily_groups {
            // Determine session from first bar of the day
            if day_bars.is_empty() { continue; }
            let hour: u32 = day_bars[0].ts[11..13].parse().unwrap_or(0);
            let min: u32 = day_bars[0].ts[14..16].parse().unwrap_or(0);
            let session = get_session(hour, min);

            if !session_should_trade(session) {
                skipped += day_bars.len();
                continue;
            }

            let (w, v, e) = get_session_params(session);
            if w == 0 { skipped += day_bars.len(); continue; }

            let trades = run_session_orb(&day_bars, w, v, e);
            for (r, s, _) in trades {
                session_trades.entry(session.to_string()).or_default().push((r, s.clone()));
                all_trades.entry("TOTAL".to_string()).or_default().push((r, s.clone()));
            }
        }
    }

    // Report
    println!("
=== SESSION-AWARE ORB — REPORT ===");
    println!("Skipped {} bars (London + Premarket = no edge)", skipped);
    
    for (name, trades) in [("TOTAL", &all_trades), ("ny", &session_trades), ("asia", &session_trades), ("afterhours", &session_trades)] {
        let t = match *name {
            "TOTAL" => &all_trades.get("TOTAL").cloned().unwrap_or_default(),
            n => &session_trades.get(n).cloned().unwrap_or_default(),
        };
        if t.is_empty() { continue; }
        let total_r: f64 = t.iter().map(|(r,_)| r).sum();
        let wins = t.iter().filter(|(r,_)| *r > 0.0).count();
        let wr = wins as f64 / t.len() as f64 * 100.0;
        let avg_r = total_r / t.len() as f64;
        let longs = t.iter().filter(|(_,s)| s == "long").count();
        let shorts = t.iter().filter(|(_,s)| s == "short").count();
        let long_wr = t.iter().filter(|(r,s)| s == "long" && *r > 0.0).count() as f64 / longs.max(1) as f64 * 100.0;
        let short_wr = t.iter().filter(|(r,s)| s == "short" && *r > 0.0).count() as f64 / shorts.max(1) as f64 * 100.0;
        
        // Max consec
        let max_consec = t.iter().fold((0usize, 0usize), |(mx, cur), (r,_)| {
            if *r <= 0.0 { (mx.max(cur+1), cur+1) } else { (mx, 0) }
        }).0;
        
        println!("
── {} ──", name.to_uppercase());
        println!("  Trades: {}, WR: {:.1}%", t.len(), wr);
        println!("  Total R: {:.1}, Avg R: {:.4}", total_r, avg_r);
        println!("  Long: {} (WR {:.1}%), Short: {} (WR {:.1}%)", longs, long_wr, shorts, short_wr);
        println!("  Max consecutive losses: {}", max_consec);
        
        // Kelly
        let avg_win = t.iter().filter(|(r,_)| *r > 0.0).map(|(r,_)| *r).sum::<f64>() / wins.max(1) as f64;
        let avg_loss = t.iter().filter(|(r,_)| *r <= 0.0).map(|(r,_)| r.abs()).sum::<f64>() / (t.len() - wins).max(1) as f64;
        let kelly = if avg_loss > 0.0 { (wins as f64 / t.len() as f64) - (1.0 - wins as f64 / t.len() as f64) / (avg_win / avg_loss).max(0.01) } else { 0.0 };
        println!("  Kelly: {:.1}%", kelly * 100.0);

        if *name == "TOTAL" {
            // already printed in the report
        }
    }

    // Final judgment
    let total = all_trades.get("TOTAL").map(|t| t.len()).unwrap_or(0);
    let total_r: f64 = all_trades.get("TOTAL").map(|t| t.iter().map(|(r,_)| r).sum()).unwrap_or(0.0);
    let total_wins = all_trades.get("TOTAL").map(|t| t.iter().filter(|(r,_)| *r > 0.0).count()).unwrap_or(0);
    let total_wr = if total > 0 { total_wins as f64 / total as f64 * 100.0 } else { 0.0 };
    
    println!("
{}", "#".repeat(70));
    println!(" SESSION-AWARE ORB — VERDICT");
    if total_r > 0.0 && total_wr > 50.0 {
        println!(" ✅ APPROVED: R+{:.1} at {:.1}% WR — skip London+Premarket", total_r, total_wr);
        println!("    Trade only NY (09:30-16:00), Asia (19:00-03:00), After-hours (16:00-19:00)");
        println!("    Use w12_v1.5_e8 for NY, w8_v1.3_e3 for Asia/After-hours");
    } else {
        println!(" ⚠️  Review needed");
    }
    println!("{}", "#".repeat(70));
}

