#!/usr/bin/env python3
"""Train an XGBoost model to predict inside days for NQ futures.

An inside day = today's high < yesterday's high AND today's low > yesterday's low.
Inside days often precede breakout days — the XGBoost model scores
'is this likely an inside day' so breakout strategies can hold fire.
"""
import json, os, sys, numpy as np
from datetime import datetime, timezone

try:
    import xgboost as xgb
except ImportError:
    print("ERROR: xgboost not installed. Run: pip3 install xgboost", file=sys.stderr)
    sys.exit(1)

DATA_DIR = os.path.expanduser("~/.rumbling-hedge/models")
MODEL_PATH = os.path.join(DATA_DIR, "inside_day_xgb_model.json")
STATE_DIR = os.path.expanduser("~/.rumbling-hedge/state")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STATE_DIR, exist_ok=True)

def load_bars(csv_path):
    """Load OHLCV bars from CSV."""
    import csv
    bars = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                bars.append({
                    "date": row.get("ts", row.get("Date", "")),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0) or 0),
                })
            except (ValueError, KeyError):
                continue
    return bars

def is_inside_day(bar, prev):
    """True if today's range is fully inside yesterday's."""
    return bar["high"] < prev["high"] and bar["low"] > prev["low"]

def extract_features(bars, i):
    """Feature engineering for inside-day prediction."""
    b = bars[i]
    p = bars[i-1]
    pp = bars[i-2] if i >= 2 else p
    
    features = {}
    features["range_today"] = b["high"] - b["low"]
    features["range_yesterday"] = p["high"] - p["low"]
    features["range_ratio"] = features["range_today"] / max(features["range_yesterday"], 0.01)
    features["body_today"] = abs(b["close"] - b["open"])
    features["body_ratio"] = features["body_today"] / max(features["range_today"], 0.01)
    features["volume_ratio"] = b["volume"] / max(p["volume"], 1)
    features["prev_return_pct"] = (p["close"] - pp["close"]) / pp["close"] * 100 if pp["close"] > 0 else 0
    features["gap_pct"] = (b["open"] - p["close"]) / p["close"] * 100 if p["close"] > 0 else 0
    features["high_low_range_30"] = np.max([bars[j]["high"] - bars[j]["low"] for j in range(max(0, i-30), i)]) if i >= 30 else features["range_today"]
    features["range_vs_30_max"] = features["range_today"] / max(features["high_low_range_30"], 0.01)
    return features

def train():
    """Train the XGBoost model on NQ 60-day data."""
    csv_path = "data/free/NQ-30m-60d.csv"
    if not os.path.exists(csv_path):
        print(f"ERROR: Data file not found: {csv_path}", file=sys.stderr)
        return
    
    bars = load_bars(csv_path)
    if len(bars) < 50:
        print(f"ERROR: Need 50+ bars, got {len(bars)}", file=sys.stderr)
        return
    
    print(f"Loaded {len(bars)} bars from {csv_path}")
    
    # Build feature matrix
    X, y = [], []
    for i in range(3, len(bars)):
        feat = extract_features(bars, i)
        label = 1 if is_inside_day(bars[i], bars[i-1]) else 0
        X.append([feat[k] for k in sorted(feat.keys())])
        y.append(label)
    
    X = np.array(X)
    y = np.array(y)
    
    # Train/test split (80/20 time-series)
    split = int(len(X) * 0.8)
    X_train, y_train = X[:split], y[:split]
    X_test, y_test = X[split:], y[split:]
    
    print(f"Training: {len(X_train)} samples, Test: {len(X_test)}")
    print(f"Inside-day rate: train={y_train.mean():.3f}, test={y_test.mean():.3f}")
    
    # Train XGBoost
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss",
        early_stopping_rounds=20,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    
    # Evaluate
    train_acc = (model.predict(X_train) == y_train).mean()
    test_acc = (model.predict(X_test) == y_test).mean()
    print(f"Train accuracy: {train_acc:.4f}")
    print(f"Test accuracy: {test_acc:.4f}")
    
    # Feature importance
    feature_names = sorted(feat.keys())
    importance = model.feature_importances_
    print("\nTop features:")
    for idx in np.argsort(importance)[-5:][::-1]:
        print(f"  {feature_names[idx]}: {importance[idx]:.4f}")
    
    # Save model
    model.save_model(MODEL_PATH)
    print(f"\nModel saved to {MODEL_PATH}")
    
    # Save state
    state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "train_accuracy": float(train_acc),
        "test_accuracy": float(test_acc),
        "feature_names": feature_names,
    }
    state_path = os.path.join(STATE_DIR, "inside_day_model_state.json")
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    print(f"State saved to {state_path}")

def predict_latest():
    """Score the latest bar for inside-day probability."""
    if not os.path.exists(MODEL_PATH):
        print(f"Model not found. Run with --train first.", file=sys.stderr)
        return
    
    model = xgb.XGBClassifier()
    model.load_model(MODEL_PATH)
    
    csv_path = "data/free/NQ-30m-60d.csv"
    bars = load_bars(csv_path)
    if len(bars) < 3:
        return
    
    feat = extract_features(bars, len(bars) - 1)
    feature_names = sorted(feat.keys())
    X = np.array([[feat[k] for k in feature_names]])
    
    prob = model.predict_proba(X)[0][1]
    
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "inside_day_probability": float(prob),
        "is_inside_day": bool(prob > 0.5),
        "is_compressed": bool(prob > 0.35),
        "latest_bar": {
            "high": float(bars[-1]["high"]),
            "low": float(bars[-1]["low"]),
            "close": float(bars[-1]["close"]),
        }
    }
    
    out_path = os.path.join(STATE_DIR, "inside_day_prediction.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Inside-day probability: {prob:.4f} {'(INSIDE DAY)' if prob > 0.5 else '(not inside day)'}")
    print(f"Output written to {out_path}")
    return output

if __name__ == "__main__":
    if "--train" in sys.argv:
        train()
    elif "--predict" in sys.argv:
        predict_latest()
    else:
        # Default: train then predict
        train()
        predict_latest()
