"""HMM Regime Detection for Bill/Hedge
Fits 4-state Hidden Markov Model on 90d 1-min futures data.
States: trending-up, trending-down, range-chop, high-vol

Usage: python3 scripts/hmm_regime.py [csv_path]
Output: .rumbling-hedge/state/hmm-regime.json
"""
import sys, json, os
from pathlib import Path

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/free/ALL-6MARKETS-1m-90d-normalized.csv"
OUT_PATH = ".rumbling-hedge/state/hmm-regime.json"

try:
    import numpy as np
    from hmmlearn import hmm
except ImportError:
    os.system("pip3 install numpy hmmlearn 2>/dev/null")
    import numpy as np
    from hmmlearn import hmm

def load_csv(path):
    bars = {}
    with open(path) as f:
        header = f.readline().strip().split(',')
        for line in f:
            parts = line.strip().split(',')
            if len(parts) < 6:
                continue
            ts, sym = parts[0], parts[1]
            o, h, l, c, v = float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5]), float(parts[6]) if len(parts) > 6 else 0
            if sym not in bars:
                bars[sym] = []
            bars[sym].append({'ts': ts, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})
    return bars

def compute_features(bars):
    closes = np.array([b['close'] for b in bars])
    highs = np.array([b['high'] for b in bars])
    lows = np.array([b['low'] for b in bars])
    volumes = np.array([b['volume'] for b in bars])
    
    n = len(closes)
    if n < 20:
        return None
    
    # Returns (log)
    returns = np.diff(np.log(closes))
    returns = np.concatenate([[0], returns])
    
    # ATR(14) normalized
    tr = np.maximum(highs[1:] - lows[1:], 
                    np.maximum(np.abs(highs[1:] - closes[:-1]), 
                              np.abs(lows[1:] - closes[:-1])))
    atr14 = np.zeros(n)
    for i in range(14, n):
        atr14[i] = np.mean(tr[i-14:i])
    atr_norm = np.divide(atr14, closes, out=np.zeros_like(atr14), where=closes!=0)
    
    # Close location (0=low, 1=high)
    range_hl = highs - lows
    close_loc = np.divide(closes - lows, range_hl, out=np.full_like(closes, 0.5), where=range_hl>0)
    
    # Volume ratio (vs 20-bar avg)
    vol_ma20 = np.zeros(n)
    for i in range(20, n):
        vol_ma20[i] = np.mean(volumes[i-20:i])
    vol_ratio = np.divide(volumes, vol_ma20, out=np.ones_like(volumes), where=vol_ma20>0)
    
    # Stack features [returns, atr_norm, close_loc, vol_ratio]
    features = np.column_stack([returns, atr_norm, close_loc, vol_ratio])
    
    # Replace NaN/Inf
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
    
    return features, closes

def fit_hmm(features, n_states=4):
    model = hmm.GaussianHMM(
        n_components=n_states,
        covariance_type="full",
        n_iter=100,
        random_state=42,
        tol=1e-4,
        init_params="stmc",
        params="stmc"
    )
    model.fit(features)
    states = model.predict(features)
    return model, states

def label_states(model, features, states):
    """Label states based on feature means: trending-up, trending-down, range-chop, high-vol"""
    n_states = model.n_components
    state_means = model.means_
    
    # For each state, compute mean return (trend direction) and mean vol
    labels = []
    for i in range(n_states):
        ret_mean = state_means[i, 0]  # mean return
        vol_mean = state_means[i, 1]  # mean ATR
        close_mean = state_means[i, 2]  # mean close location
        
        # Classification logic
        if vol_mean > np.percentile(state_means[:, 1], 75):
            labels.append("high-vol")
        elif abs(ret_mean) < 0.00005 and vol_mean < np.percentile(state_means[:, 1], 50):
            labels.append("range-chop")
        elif ret_mean > 0.00005:
            labels.append("trending-up")
        else:
            labels.append("trending-down")
    
    return labels

def main():
    csv_path = Path(CSV_PATH)
    if not csv_path.exists():
        # Try relative from hedge root
        csv_path = Path(os.environ.get("HOME", "/Users/brain")) / "hedge" / CSV_PATH
    
    if not csv_path.exists():
        print(f"ERROR: CSV not found at {csv_path}")
        # Try 30d normalized as fallback
        csv_path = Path(os.environ.get("HOME", "/Users/brain")) / "hedge/data/free/ALL-6MARKETS-1m-30d-normalized.csv"
        if not csv_path.exists():
            sys.exit(1)
    
    print(f"Loading {csv_path}...")
    bars_by_symbol = load_csv(str(csv_path))
    
    results = {}
    for sym, bars in bars_by_symbol.items():
        if len(bars) < 100:
            continue
        
        result = compute_features(bars)
        if result is None:
            continue
        
        features, closes = result
        
        try:
            model, states = fit_hmm(features)
            state_labels = label_states(model, features, states)
            
            # State statistics
            state_counts = {}
            for s in states:
                state_counts[int(s)] = state_counts.get(int(s), 0) + 1
            
            # Build per-bar regime data (sample every 100 bars for efficiency)
            regime_bars = []
            step = max(1, len(states) // 500)
            for i in range(0, len(states), step):
                if i < len(bars):
                    state_idx = int(states[i])
                    regime_bars.append({
                        'ts': bars[i]['ts'],
                        'close': float(closes[i]) if i < len(closes) else 0,
                        'regime': state_labels[state_idx],
                        'state': state_idx,
                        'confidence': float(np.max(model.predict_proba(features[i:i+1])[0])) if i < len(features) else 0
                    })
            
            results[sym] = {
                'states': {i: {'label': state_labels[i], 'mean_return': float(model.means_[i, 0]),
                               'mean_vol': float(model.means_[i, 1]), 'count': state_counts.get(i, 0)}
                          for i in range(model.n_components)},
                'transition_matrix': model.transmat_.tolist(),
                'current_regime': state_labels[int(states[-1])],
                'current_state': int(states[-1]),
                'regime_bars': regime_bars[:200],  # Keep last 200 sample bars
                'n_bars': len(states),
                'dominant_regime': max(state_counts, key=state_counts.get)
            }
            print(f"  {sym}: {len(states)} bars, states={state_counts}, current={state_labels[int(states[-1])]}")
        except Exception as e:
            print(f"  {sym}: HMM fit failed - {e}")
            results[sym] = {'error': str(e), 'n_bars': len(bars)}
    
    out_dir = Path(".rumbling-hedge/state")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    output = {
        'generated_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        'csv_path': str(csv_path),
        'results': results
    }
    
    with open(OUT_PATH, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nWritten to {OUT_PATH}")
    print(f"Symbols processed: {len(results)}")
    
    # Print transition matrix for first symbol
    for sym in results:
        if 'transition_matrix' in results[sym]:
            print(f"\n{sym} transition matrix:")
            for i, row in enumerate(results[sym]['transition_matrix']):
                label = results[sym]['states'][i]['label']
                print(f"  {label}: {[f'{v:.2f}' for v in row]}")

if __name__ == "__main__":
    main()
