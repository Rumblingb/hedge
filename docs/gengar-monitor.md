# Gengar Live Paper-Trading Monitor

## Quick Start
```bash
cd /Users/brain/hedge
npx tsx src/prediction/gengarMonitor.ts
```

## What It Does
1. Aligns to 5-min BTCUSDT windows (Binance)
2. Fetches Polymarket CLOB V2 order books for BTC 5-min UP/DOWN tokens
3. Runs the full 5-gate gengar chain every 2 seconds
4. Logs valid signals to `.rumbling-hedge/journal/gengar-signals.jsonl`

## Gates (in order)
1. **Entry Window**: 240s → 10s remaining (enters mid-window)
2. **BTC Delta**: ≥ 0.06% (6 bps minimum move)
3. **Price Range**: 0.50 ≤ market_price ≤ 0.90
4. **Probability**: ≥ 0.80 (gengar Brownian motion)
5. **Edge**: prob - market_price ≥ 0.05 (5%)

## Calibration (from gengar bot v13)
- vol = 0.12 (percentage points, i.e. 12 bps 5-min vol)
- quarter-Kelly sizing, $5 min / $25 max per trade
- Hold to resolution (5-min window close)
- Symmetric: same prob formula for UP and DOWN

## Signal Format
```json
{
  "ts": "2026-05-08T13:30:00Z",
  "side": "UP",
  "prob": 0.92,
  "edge": 0.15,
  "marketPrice": 0.68,
  "deltaBps": 0.54,
  "kellyFraction": 0.12,
  "recommendedBet": 25.00,
  "secondsRemaining": 180,
  "btcOpen": 74000,
  "btcNow": 74400,
  "upPrice": 0.68,
  "downPrice": 0.35
}
```

## Cron Integration
```bash
# Schedule via cronjob tool or launchd
# Suggested: run during US/EU market hours, Mon-Fri
```

## Paper Trading Validation
- Track P&L in gengar-signals.jsonl
- Each signal: profit = 1.0 - entryPrice if correct, -entryPrice if wrong
- Resolution determined by BTC close vs open at window end
