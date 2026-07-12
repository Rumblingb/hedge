# External Alpha Dataset Audit + Integration Plan — 2026-05-26

Root: `/Volumes/Seagate Expansion Drive/hedge-data/external-alpha-2026-05-25`  
Feature root: `/Volumes/Seagate Expansion Drive/hedge-data/features`

## Feature artifacts
- `/Volumes/Seagate Expansion Drive/hedge-data/features/equities_breadth/equities_5m_breadth_2026-03.parquet` — rows=1,295, size=0.16MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_15_minute.parquet` — rows=6,739, size=0.25MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_1_hour.parquet` — rows=10,504, size=0.44MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_1_minute.parquet` — rows=6,554, size=0.20MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_2_hour.parquet` — rows=5,479, size=0.24MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_30_minute.parquet` — rows=9,165, size=0.37MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_3_hour.parquet` — rows=5,712, size=0.26MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_3_minute.parquet` — rows=6,786, size=0.22MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_45_minute.parquet` — rows=6,179, size=0.26MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_4_hour.parquet` — rows=5,817, size=0.27MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_5_minute.parquet` — rows=5,452, size=0.19MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_daily.parquet` — rows=6,648, size=0.30MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_monthly.parquet` — rows=317, size=0.02MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_weekly.parquet` — rows=1,372, size=0.07MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/polymarket_btc_updown/btc_15m_resolved_top25_features.parquet` — rows=17,946, size=0.09MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/polymarket_btc_updown/btc_15m_top10_features.parquet` — rows=282, size=0.01MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/polymarket_btc_updown/btc_5m_resolved_all_features.parquet` — rows=232,725, size=1.20MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/polymarket_btc_updown/btc_5m_resolved_top25_features.parquet` — rows=10,329, size=0.07MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/polymarket_btc_updown/test_btc_15m_features.parquet` — rows=72, size=0.01MB
- `/Volumes/Seagate Expansion Drive/hedge-data/features/sp500_options/daily_regime_features.parquet` — rows=903, size=0.09MB

## Source footprint
- `hf/BrockMisner__polymarket-btc-updown` — files=188, size=12.70GB
- `hf/Bose345__sp500_earnings_transcripts` — files=8, size=1.82GB
- `hf/TeraflopAI__SEC-EDGAR` — files=2,833, size=197.26GB
- `hf/fabhaus__equities_5m_stockprices` — files=12, size=16.41GB
- `kaggle/youneseloiarm__nasdaq-cme-future-nq` — files=14, size=0.01GB
- `kaggle/shubhamcodez__s-and-p-500-daily-options-data-2010-2023` — files=1, size=0.23GB
- `github/vol-regime-prediction` — files=71, size=0.02GB
- `github/polymarket-microstructure` — files=243, size=0.01GB

## SEC progress
- COMPLETE: verified against Hugging Face remote tree on 2026-05-26T08:55Z.
- remote_parquet_count=2,551
- local_parquet_count=2,551
- missing_count=0
- local_parquet_payload=~274.75GiB (`du -sh` ~275G)

## Gold extracted / required

### P0 — Polymarket BTC up/down (direct Gengar edge)
- Full BrockMisner dataset is local: markets, spot, prices, ticks, orderbook.
- Built feature tables:
  - `btc_5m_resolved_all_features.parquet`: label-ready 5m BTC market/orderbook/tick/spot join.
  - `btc_15m_resolved_top25_features.parquet`: quick research table for top-volume resolved markets.
- Gold features to wire: `spot_distance_to_strike_pct`, `seconds_to_expiry_bucket`, `avg_spread`, `up/down_depth_imbalance`, `trade_flow_imbalance`, `spot_mom_3bar/12bar`, `spot_vol_12bar/48bar`.
- Use as offline calibration for Gengar oracle lag: only trade when spot move leads probability, spread/depth are sane, and time-to-expiry/liquidity bucket historically has positive expectancy.

### P0 — Polymarket microstructure repo
- Local repo contains reusable measures for spread, depth, effective spread, impact/Kyle lambda, latency, intensity, participants, wash/longshot/depth-decay/stylized-fact checks.
- Critical gold: README states public WebSocket trade-direction inference agrees with on-chain ground truth only ~59%; effective half-spread sign flips 67%, Kyle λ sign flips 60%. Therefore Gengar must treat inferred side/impact as noisy unless confirmed on-chain or robust to sign flips.
- Backlog: vendor selected `polydata/measures/*`, `polydata/resample.py`, and stylized-fact checks into research sandbox; do not import raw websocket assumptions into production without tests against BrockMisner ticks.

### P0 — NQ futures Kaggle
- Converted all CSV timeframes into canonical parquet under `features/nq_futures/`.
- Gold: offline NQ benchmark for ORB/daily-range-breakout/session filters independent of broker exports.
- Required next wiring: add these parquet files to Bill data catalog; run ORB/DRB smoke backtests on 1m/5m and compare against current broker-derived curves.

### P1 — S&P 500 options daily 2010-2023
- Built `features/sp500_options/daily_regime_features.parquet` with 903 daily rows.
- Gold features: put/call volume ratio, 5-45D ATM IV, 25-delta skew proxy, front ATM gamma proxy, call/put volume walls and wall distance from underlying.
- Required next wiring: align daily features to NQ/SPY sessions and use as risk-council filter; avoid treating volume walls as true max-pain because dataset lacks OI.

### P1 — vol-regime-prediction repo
- Gold is feature taxonomy, not executable alpha by itself: realized vol windows, Parkinson RV, VRP, VIX term structure, SKEW, put/call ratios, options IV surface/Greeks, FRED macro.
- Important leakage warning from repo: `vrp_forward` / forward-looking VRP must never be used as predictor; only ex-post label/evaluation.
- Required next wiring: port free CBOE/FRED/Yahoo collectors or reproduce columns from existing Bill data; keep Alpha Vantage premium options optional.

### P2 — fabhaus equities 5m
- Full corpus is ~478GB; cannot fit alongside SEC on current 932GiB external disk. Downloaded selected high-value 2026-03 month for schema and feature development.
- Built `features/equities_breadth/equities_5m_breadth_2026-03.parquet`.
- Gold features: cross-sectional advancer/decliner ratio, unusual-volume ratio, RSI breadth, mega-cap average return/volume/RSI/valuation gap. Use as NQ lead/lag and breadth-risk overlay.

### P2 — earnings transcripts / SEC EDGAR
- Earnings transcript full dataset local: 33,362 rows with symbol, quarter/year/date, content, structured speaker/text blocks.
- SEC EDGAR mirror is complete locally: 2,551/2,551 parquet files, ~275G.
- Gold use only after P0/P1 market data is wired: mega-cap earnings week sentiment/shock tags, sector stress tags, filing-risk themes. Do not let text research delay executable market-feature integration.

## Concrete repo artifacts created/updated
- `/Users/brain/hedge/ops/download_external_alpha_2026_05_25.sh`
- `/Users/brain/hedge/scripts/build_polymarket_btc_features.py`
- `/Users/brain/hedge/scripts/build_external_alpha_features.py`
  - `normalize-nq`
  - `sp500-options-daily`
  - `equities-breadth`

## Execution order from here
1. Register `features/polymarket_btc_updown/btc_5m_resolved_all_features.parquet` into Gengar research harness and run expectancy by bucket: spot lead/lag × spread × depth imbalance × time-to-expiry.
2. Register `features/nq_futures/nq_1_minute.parquet` and `nq_5_minute.parquet` into Bill data catalog; run ORB/DRB smoke tests.
3. Join `sp500_options/daily_regime_features.parquet` to NQ daily/session returns; quantify whether put/call, skew, gamma proxy improve veto/risk sizing.
4. Use `equities_breadth/equities_5m_breadth_2026-03.parquet` as prototype breadth overlay; backfill 2024-01 and 2025-01 only if the prototype shows predictive value.
5. Vendor microstructure measures after tests; enforce no WebSocket-inferred trade-direction dependency without on-chain validation or sign-flip robust metrics.
6. Do not start full fabhaus mirror on the current disk; free space is ~154GiB and full corpus is ~478GB.
