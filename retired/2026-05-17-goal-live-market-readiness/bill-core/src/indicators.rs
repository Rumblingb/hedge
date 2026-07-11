use crate::types::Bar;

/// Simple Moving Average over `period` bars
pub fn sma(closes: &[f64], period: usize) -> f64 {
    let slice = if closes.len() >= period {
        &closes[closes.len() - period..]
    } else {
        closes
    };
    if slice.is_empty() {
        return 0.0;
    }
    slice.iter().sum::<f64>() / slice.len() as f64
}

/// Average True Range over `period` bars
pub fn atr(bars: &[&Bar], period: usize) -> f64 {
    if bars.len() < 2 {
        return 0.0;
    }
    let slice = if bars.len() >= period + 1 {
        &bars[bars.len() - period - 1..]
    } else {
        bars
    };

    let mut true_ranges = Vec::with_capacity(slice.len() - 1);
    for i in 1..slice.len() {
        let high_low = slice[i].high - slice[i].low;
        let high_close = (slice[i].high - slice[i - 1].close).abs();
        let low_close = (slice[i].low - slice[i - 1].close).abs();
        true_ranges.push(high_low.max(high_close).max(low_close));
    }

    if true_ranges.is_empty() {
        return 0.0;
    }
    true_ranges.iter().sum::<f64>() / true_ranges.len() as f64
}

/// Standard deviation over `period` values
pub fn std_dev(values: &[f64], period: usize) -> f64 {
    let mean = sma(values, period);
    let slice = if values.len() >= period {
        &values[values.len() - period..]
    } else {
        values
    };
    if slice.len() < 2 {
        return 0.0;
    }
    let variance = slice.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / slice.len() as f64;
    variance.sqrt()
}

/// Rank values [0, 1] — lowest = 0, highest = 1
pub fn rank(values: &[f64]) -> Vec<f64> {
    let n = values.len();
    if n == 0 {
        return vec![];
    }
    let mut indexed: Vec<(usize, &f64)> = values.iter().enumerate().collect();
    indexed.sort_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal));
    let mut result = vec![0.0; n];
    for (rank_pos, (orig_idx, _)) in indexed.iter().enumerate() {
        result[*orig_idx] = (rank_pos + 1) as f64 / n as f64;
    }
    result
}

/// Returns (price change over `period` bars) for the last bar
pub fn delta(values: &[f64], period: usize) -> f64 {
    if values.len() <= period {
        return 0.0;
    }
    values[values.len() - 1] - values[values.len() - 1 - period]
}

/// Correlation between two series over `period`
pub fn correlation(a: &[f64], b: &[f64], period: usize) -> f64 {
    let n = period.min(a.len()).min(b.len());
    if n < 3 {
        return 0.0;
    }
    let sa = &a[a.len() - n..];
    let sb = &b[b.len() - n..];
    let ma = sa.iter().sum::<f64>() / n as f64;
    let mb = sb.iter().sum::<f64>() / n as f64;
    let mut cov = 0.0;
    let mut va = 0.0;
    let mut vb = 0.0;
    for i in 0..n {
        let da = sa[i] - ma;
        let db = sb[i] - mb;
        cov += da * db;
        va += da * da;
        vb += db * db;
    }
    if va > 0.0 && vb > 0.0 {
        cov / (va.sqrt() * vb.sqrt())
    } else {
        0.0
    }
}

/// Min over `period` values
pub fn ts_min(values: &[f64], period: usize) -> f64 {
    let slice = if values.len() >= period {
        &values[values.len() - period..]
    } else {
        values
    };
    slice.iter().cloned().fold(f64::INFINITY, f64::min)
}

/// Max over `period` values
pub fn ts_max(values: &[f64], period: usize) -> f64 {
    let slice = if values.len() >= period {
        &values[values.len() - period..]
    } else {
        values
    };
    slice.iter().cloned().fold(f64::NEG_INFINITY, f64::max)
}

/// Signed power: sign(x) * |x|^a
pub fn signed_power(x: f64, a: f64) -> f64 {
    x.signum() * x.abs().powf(a)
}

/// ArgMax position (0-1) over `period` values
pub fn ts_argmax(values: &[f64], period: usize) -> f64 {
    let slice = if values.len() >= period {
        &values[values.len() - period..]
    } else {
        values
    };
    if slice.is_empty() {
        return 0.0;
    }
    let mut max_val = slice[0];
    let mut max_idx = 0;
    for (i, &v) in slice.iter().enumerate() {
        if v > max_val {
            max_val = v;
            max_idx = i;
        }
    }
    max_idx as f64 / slice.len() as f64
}

/// Visibility Graph RSI (VGRSI) — Rafał Rak, arXiv:2605.01300
///
/// Computes a technical indicator based on backward visibility graph theory.
/// Points visible from the current point (strictly below the connecting line)
/// contribute their one-step price changes. The ratio of positive vs negative
/// contributions is normalized to [0, 100].
///
/// Variant A0: mean of (sum_ratio, count_ratio) — trend/persistence filter
/// Variant A1: ratio of (sum_ratio / count_ratio) — breakout/impulse detector
pub fn vgrsi(closes: &[f64], ws: usize, wv: usize, variant: &str) -> f64 {
    if closes.len() < ws + 2 {
        return 50.0; // neutral default
    }

    let t = closes.len() - 1;
    let mut s_plus = 0.0_f64;
    let mut s_minus = 0.0_f64;
    let mut n_plus: usize = 0;
    let mut n_minus: usize = 0;

    let start_j = if t >= ws { t - ws + 1 } else { 1 };

    for j in start_j..=t {
        let pj = closes[j];
        // Find visible points in [j-wv, j-1]
        let visible = find_visible_backward(closes, j, wv);
        for &i in &visible {
            if i == 0 { continue; }
            let delta = closes[i] - closes[i - 1];
            if delta > 0.0 {
                s_plus += delta;
                n_plus += 1;
            } else {
                s_minus += -delta;
                n_minus += 1;
            }
        }
    }

    let rs = if s_minus > 0.0 { s_plus / s_minus } else { f64::MAX };
    let rn = if n_minus > 0 { n_plus as f64 / n_minus as f64 } else { f64::MAX };

    let ra = match variant {
        "A1" => {
            if rn > 0.0 { rs / rn } else { rs }
        }
        _ => { // A0 (default)
            (rs + rn) / 2.0
        }
    };

    // Normalize to [0, 100]
    100.0 - 100.0 / (1.0 + ra)
}

/// Find indices of points visible from position j within the lookback window wv.
/// A point i is visible if ALL intermediate points k (i < k < j) have pk < line(i,j).
fn find_visible_backward(closes: &[f64], j: usize, wv: usize) -> Vec<usize> {
    let start = j.saturating_sub(wv);
    let mut visible = Vec::new();

    for i in (start..j).rev() {
        let pi = closes[i];
        let pj = closes[j];
        let mut is_visible = true;

        for k in (i + 1)..j {
            let pk = closes[k];
            // Line value at k: pj + (pi - pj) * (k - j) / (i - j)  (with int division)
            // Since k-j is negative and i-j is negative, ratio is positive
            let line_val = pj + (pi - pj) * (k as f64 - j as f64) / (i as f64 - j as f64);
            if pk >= line_val {
                is_visible = false;
                break;
            }
        }

        if is_visible {
            visible.push(i);
        }
    }

    visible
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sma() {
        assert_eq!(sma(&[1.0, 2.0, 3.0], 3), 2.0);
        assert_eq!(sma(&[1.0, 2.0, 3.0, 4.0, 5.0], 2), 4.5);
    }

    #[test]
    fn test_rank() {
        let r = rank(&[3.0, 1.0, 2.0]);
        assert!((r[0] - 1.0).abs() < 0.001); // 3.0 = highest
        assert!((r[1] - 1.0 / 3.0).abs() < 0.001); // 1.0 = lowest
    }

    #[test]
    fn test_delta() {
        assert_eq!(delta(&[1.0, 2.0, 3.0, 4.0], 2), 2.0); // 4 - 2
    }
}
