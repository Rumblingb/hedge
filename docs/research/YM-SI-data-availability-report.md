# YM (Dow Jones $5 E-mini) and SI (Silver) Data Availability Report

Generated: 2026-06-10

## Executive Summary

**No YM or SI futures data exists in the system.** Both symbols are already recognized by the data pipeline (`KNOWN_SYMBOLS` in `build_data_master_csv.py` includes both), but no CSV files, archives, or API endpoints have been configured to fetch them.

---

## Data Sources Checked

### 1. ALL-6MARKETS*.csv (`data/free/`)
The 6 markets are: **6E, CL, ES, GC, NQ, ZN** — no YM or SI.
- Available timeframes: 1m, 5m, 15m, 30m, 60m, 1d
- Available depths: 5d, 10d, 21d, 30d, 60d
- ~27K rows per timeframe for the combined 6-market file

### 2. TopstepX/ProjectX API (preferred data path)
- **Existing scripts** provide a working architecture:
  - `topstep_readonly_bar_archive.py` — accumulates 1m bars into CSV archives
  - `topstep_market_data_smoke.py` — smoke-tests bar retrieval for NQ/MNQ
  - `topstep_realtime_proof.py` — realtime quote subscriptions (supports NQ, MNQ, ES)
- **Currently hardcoded to NQ/MNQ only** — `SYMBOLS = [("NQ", "F.US.ENQ"), ("MNQ", "F.US.MNQ")]`
- **API endpoints used**:
  - `POST /api/Auth/loginKey` — authentication
  - `POST /api/Contract/search` — contract search (takes searchText, returns contracts with symbolId)
  - `POST /api/History/retrieveBars` — bar retrieval (contractId, startTime, endTime, unit, limit)
  - `wss://rtc.topstepx.com/hubs/market` — realtime SignalR hub
- **API docs referenced**: `https://gateway.docs.projectx.com/docs/api-reference/market-data/search-contracts/`

### 3. `external/nq-quant/data/`
Contains only NQ-related build scripts (resampler, cleaner, loader, merge_10yr). No YM/SI data.

### 4. `data/free/` (full inventory of 182 CSV files)
All 182 files checked. None contain YM or SI futures bar data:
- NQ, ES, GC, CL, 6E, ZN only for futures
- The `30yr-cross-asset-market-data.csv` has a "Dow Jones" and "Silver" column, but these are **index/spot price references**, not futures OHLCV data
- The `futures-daily-with-features-24tickers.csv` contains 24 tickers but YM/SI are not among them

### 5. `.rumbling-hedge/research/topstep-readonly-bars/`
Contains only `NQ-1m-topstep-readonly.csv` (3,667 rows, 7 sessions) and `MNQ-1m-topstep-readonly.csv` (same count). No YM/SI.

### 6. `data/research/`
Contains ALL-6MARKETS data and individual instrument CSVs (6E, CL, ES, GC, NQ, ZN only). No YM/SI.

---

## Data Acquisition Plan

### Recommended Data Frequencies

To match the existing 6-market pipeline:

| Frequency | Depth | Priority | Use Case |
|-----------|-------|----------|----------|
| **1m bars** | Latest ~60 days | HIGH | Bar archive accumulation (like current NQ/MNQ) |
| **15m bars** | Latest 60 days | HIGH | Pattern research, ORB strategies |
| **60m bars** | Latest 60 days | MEDIUM | Trend/momentum, vol-regime overlay |
| **Daily bars** | 1+ years | MEDIUM | Long-term bias, seasonality |
| **5m bars** | Latest 60 days | LOW | Scalping research |

### Recommended Date Range

| Phase | Instrument | Bar Size | Range | Purpose |
|-------|-----------|----------|-------|---------|
| Phase 1 | YM, SI | 1m | June 2026 ongoing | Broker-relevant realtime archive (matches NQ/MNQ) |
| Phase 2 | YM, SI | 1m | March–June 2026 | Historical current session (~60 days) |
| Phase 3 | YM, SI | 15m, 60m | 60 days | Multi-timeframe research |
| Phase 4 | YM, SI | Daily | 1+ years | Macro research |

### How to Get It: TopstepX ProjectX API

The existing code in `topstep_market_data_smoke.py` provides a blueprint:

**Step 1 — Discover Contract IDs:**
Use `POST /api/Contract/search` with searchText="YM" and "SI" to get contract IDs.

ProjectX symbol ID conventions (inferred from existing data):
- NQ: `F.US.ENQ` (E-mini Nasdaq 100)
- MNQ: `F.US.MNQ` (Micro E-mini Nasdaq 100)
- ES: `F.US.EP` (E-mini S&P 500)
- **YM (Dow): Likely `F.US.YM`** (E-mini Dow $5)
- **SI (Silver): Likely `F.US.SI`** (Silver futures)
- Contract IDs follow pattern: `CON.{symbolId}.M26` (e.g., `CON.F.US.YM.M26` for June 2026)

**Step 2 — Fetch Bars:**
Use `POST /api/History/retrieveBars` with:
```python
{
    "contractId": "CON.F.US.YM.M26",  # replace with actual
    "live": false,                     # or true for realtime
    "startTime": "2026-03-01T00:00:00Z",
    "endTime": "2026-06-10T00:00:00Z",
    "unit": 2,                        # 2 = minute bars
    "unitNumber": 1,                  # 1-minute bars
    "limit": 500,
    "includePartialBar": False,
}
```

Unit codes used by the API:
- The `unit` parameter: looking at existing code, `unit_number=1` with `unit=2` produces 1-minute bars. This is the ProjectX API convention.

**Step 3 — Extend Existing Scripts:**
Modify `topstep_readonly_bar_archive.py` to add YM and SI to the `SYMBOLS` list:
```python
SYMBOLS = [
    ("NQ", "F.US.ENQ"),
    ("MNQ", "F.US.MNQ"),
    ("YM", "F.US.YM"),   # Add after confirming contract ID
    ("SI", "F.US.SI"),   # Add after confirming contract ID
]
```

### Alternative Data Sources

If TopstepX doesn't cover YM/SI (unlikely — Topstep supports both for trading):

| Source | Pros | Cons |
|--------|------|------|
| **Databento** | High quality, historical depth | Cost, needs API key configuration |
| **Yahoo Finance** | Free, easy | Delayed, unreliable intraday |
| **Polygon.io** | Good futures coverage | Paid API key |
| **Kaggle** | Some futures datasets | Inconsistent quality, stale |
| **csv download from broker** | Most accurate | Manual process |

### Recommended Acquisition Priority

1. **Immediately**: Run contract search against TopstepX API to confirm YM/SI contract IDs
2. **Week 1**: Extend `topstep_readonly_bar_archive.py` to accumulate YM/SI 1m bars
3. **Week 2**: Build ALL-6MARKETS-style combined files for YM+SI alongside existing markets
4. **Week 2-3**: Historical backfill (fetch older bars if API supports lookback > 240 min)
5. **Week 3+**: Multi-timeframe derived datasets (15m, 60m, daily)

### Existing Data Volumes (for reference)

| Instrument | 1m bars (5 days) | 15m bars (60 days) | 60m bars (60 days) |
|-----------|-----------------|-------------------|-------------------|
| 6E | ~4,727 | ~4,510 | ~1,128 |
| ALL-6 (combined) | ~31,850 | ~27,176 | ~6,804 |

YM and SI should produce similar volumes per instrument.

---

## Files That Need Modification

1. **`scripts/topstep_readonly_bar_archive.py`** — Add YM/SI to `SYMBOLS` list (lines 40, 239)
2. **`scripts/topstep_market_data_smoke.py`** — Add YM/SI to the symbol check loop (line 277)
3. **`scripts/topstep_realtime_proof.py`** — Add YM/SI contract specs (line 35)
4. **`scripts/build_data_master_csv.py`** — Already recognizes YM/SI in `KNOWN_SYMBOLS` (line 33) — no change needed
5. **`scripts/build_longterm_dataset.py`** — May want to extend if building YM/SI datasets

---

## Key Files Referenced

| File | Purpose |
|------|---------|
| `scripts/topstep_readonly_bar_archive.py` | Bar accumulation script (hardcoded to NQ/MNQ) |
| `scripts/topstep_market_data_smoke.py` | Market data smoke test + API helpers |
| `scripts/topstep_realtime_proof.py` | Realtime quote subscription (NQ, MNQ, ES) |
| `scripts/build_data_master_csv.py` | Data catalog builder (knows YM/SI) |
| `scripts/futures_data_requirements.py` | Data requirements checklist (NQ-only) |
| `data/free/ALL-6MARKETS-*.csv` | The 6-market combined files |
| `.rumbling-hedge/research/topstep-readonly-bars/` | Current NQ/MNQ 1m archives |
| `.rumbling-hedge/state/topstep-market-data-smoke.latest.json` | Last API smoke test result |
| `.rumbling-hedge/state/topstep-readonly-bar-archive.latest.json` | Last archive run result |
