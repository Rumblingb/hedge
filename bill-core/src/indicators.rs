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
