# CSV Data Scan - Complete Structural Analysis
## Directories: /Users/brain/hedge/data/free/ (150 files) + /Users/brain/hedge/data/research/ (70 files)
## Total: 220 CSV files analyzed

---

## 1. LONG-HISTORY DAILY FILES (Primary Backbone for Continuous Series)

| File | Ticker | Rows | Date Range | Columns | Size | Notes |
|------|--------|------|------------|---------|------|-------|
| **GC-daily-1975-2025.csv** | GC (Gold) | 12,776 | 1975-01-01 → 2025-10-14 | datetime,symbol,o,h,l,c,vol | 0.8 MB | **Gold #1: longest history, continuous daily** |
| **CL-daily-1983-2025.csv** | CL (Crude) | 10,708 | 1983-03-29 → 2025-10-30 | datetime,symbol,o,h,l,c,vol | 0.6 MB | **Crude #1: longest history, continuous daily** |
| **GOLD-daily-2000-2026.csv** | GOLD | 6,383 | 2000-08-30 → 2026-02-06 | DateTime,Date,Year,Month,Day,DayOfWeek,Quarter,O,H,L,C,Vol,Price_Change,%,MA_7,MA_30,MA_90,MA_365,Volatility_30d,Source | 1.6 MB | Gold #2: shorter but more recent, has tech indicators |
| **GOLD-1h-2000-2026.csv** | GOLD | 11,423 | 2024-02-11 → 2026-02-06 | DateTime,Date,Time,Year,Month,Day,Hour,O,H,L,C,Vol,Price_Change,% | 1.7 MB | Gold 1h: only 2yr window despite claiming "2000-2026" |
| **futures-daily-with-features-24tickers.csv** | 24 tickers | 148,664 | 2002-03-18 → 2025-09-19 | 65 cols: o,h,l,c,vol,target,bollinger,donchian,ma_cross,turtle, returns | 102 MB | **24 tickers in one file**: BP,C,CD,CL,ES,EU,FV,GC,GF,HG,HO,JY,NG,NQ,PL,RTY,S,SF,SI,TU,TY,US,W,YM. Has NaN dates for most tickers! |
| **30yr-cross-asset-market-data.csv** | Multi | 9,229 | 1995-01-02 → 2025-12-30 | 57 cols: 7 indices, 18 stocks, 4 FX, 10 commodities, 4 bonds, 2 crypto | 2.5 MB | **Excellent for cross-asset context** |
| **VIX-daily-2004-2020.csv** | VIX | 4,199 | 2004-01-02 → 2020-09-04 | Date, VIX Open,High,Low,Close | 0.1 MB | VIX daily, ends 2020 |
| **SPX-options-derived-2017-2025.csv** | SPX | 2,118 | 2017-06-01 → 2025-10-31 | date,day_name,total_volume,short_volume,long_volume,short_to_long_volume,put_to_call_volume,notional,total_open_interest,put_to_call_open_interest,num_expirations,mean_normalized_straddle_price,sd_normalized_straddle_price,mean_skew,sd_skew | 0.4 MB | SPX options data |

---

## 2. ES (E-mini S&P 500) — ALL FILES GROUPED

### 1-min Resolution
| File | Rows | Date Range | Size | Notes |
|------|------|------------|------|-------|
| **ES-1min-2000-2019.csv** | 2,563,493 | 2000-01-03 → 2019-12-31 | 116.5 MB | Original 1-min bars, 6 cols (timestamp,o,h,l,c,vol) |
| **ES-1m-20yr.csv** | 2,563,493 | 2000-01-03 → 2019-12-31 | 138.5 MB | Same data + symbol column + tick_count (8 cols) |
| **ES-1m-30d.csv** | 28,143 | 2026-04-14 → 2026-05-12 | 1.8 MB | Recent 1-min, 8 cols (Datetime,O,H,L,C,Vol,Dividends,Stock Splits) |
| **ES-1m-21d-normalized.csv** | 28,143 | 30d window | 1.7 MB | Normalized format |
| **GAP: 2020-01-01 → 2026-04-13** | | **~6.3 years missing!** | | **No 1-min ES data for this period** |

### Aggregated Timeframes (2000-2019)
| File | Rows | Period | Size |
|------|------|--------|------|
| **ES-2000-2019-5m.csv** | 807,057 | 2000-2019 | 41.5 MB |
| **ES-2000-2019-15m.csv** | 327,530 | 2000-2019 | 16.9 MB |
| **ES-2000-2019-30m.csv** | 181,829 | 2000-2019 | 9.4 MB |
| **ES-2000-2019-60m.csv** | 98,321 | 2000-2019 | 5.1 MB |
→ **All derived from the same 1-min source, cover same period, same gap after 2019**

### Short-Horizon Recent Windows
| File | Rows | Notes |
|------|------|-------|
| ES-1d-1y.csv | 251 | ~1yr daily |
| ES-1825d-1d-fresh.csv | 1,258 | ~5yr daily |
| ES-60d-15m-fresh.csv | 3,817 | 60d 15min |
| ES-5m-60d.csv, ES-15m-60d.csv, etc. | ~13K,~4.5K | Recent window data (no dates in ts col) |
| ES-60m-5d.csv, ES-30m-5d.csv, etc. | ~87-170 | Very short windows |

### ES MERGE PATH:
- **Daily:** futures-daily-with-features (ES, 2002-2025) + 30yr-cross-asset (S&P500, 1995-2025) → can cross-validate
- **Intraday:** ES-1min-2000-2019.csv + ES-1m-20yr.csv cover 2000-2019 identically (same source). Major gap 2020-early 2026. ES-1m-30d.csv covers Apr-May 2026 only.
- **Higher TF:** Derived 5m/15m/30m/60m from same 1-min source → same gap
- **SP-tick-2000-2019.csv** has 13.8M quote ticks (vol=0) for same 2000-2019 period

---

## 3. NQ (Nasdaq-100) — ALL FILES GROUPED

### 1-min Resolution
| File | Rows | Date Range | Size | Notes |
|------|------|------------|------|-------|
| **NQ-1min-2022-2025.csv** | 1,048,575 | 2022-12-26 → 2025-12-11 | 69.2 MB | 8 cols (+Vwap_RTH, Vwap_ETH), date format MM/DD/YYYY |
| **NQ-1m-3yr.csv** | 1,048,575 | 2022-12-26 → 2025-12-11 | 60.1 MB | ISO format, 7 cols, same data |
| **NQ-1m-30d.csv** | 28,144 | 2026-04-14 → 2026-05-12 | 1.9 MB | Recent window |
| **GAP: pre-2022-12-26** | | **No NQ data before late 2022!** | | **Nothing for 2000-2022 at 1-min** |

### Aggregated Timeframes (2022-2025)
| File | Rows | Period | Size |
|------|------|--------|------|
| NQ-2022-2025-5m.csv | 210,516 | 2022-2025 | 12.5 MB |
| NQ-2022-2025-15m.csv | 70,685 | 2022-2025 | 4.2 MB |
| NQ-2022-2025-30m.csv | 35,721 | 2022-2025 | 2.1 MB |
| NQ-2022-2025-60m.csv | 18,243 | 2022-2025 | 1.1 MB |
| NQ-60m-1y.csv | 13,663 | ~1yr window | — |
→ **All cover only 2022-2025 period. No pre-2022 NQ data at any resolution except via daily futures-daily-with-features.**

### NQ MERGE PATH:
- **Daily:** futures-daily-with-features (NQ, 2002-2025) — only pre-2022 daily source
- **Intraday:** NQ-1min-2022-2025.csv (converted from NQ-1m-3yr.csv? same source). NQ-1m-30d.csv extends to May 2026. No pre-2022 intraday data exists.

---

## 4. GC / GOLD — ALL FILES GROUPED

| File | Rows | Date Range | Notes |
|------|------|------------|-------|
| **GC-daily-1975-2025.csv** | 12,776 | 1975-01-01 → 2025-10-14 | **Primary daily gold** |
| **GC-weekly-2022-2025.csv** | 2,651 | 1974-12-29 → 2025-10-12 | Actually WEEKLY, starts 1974! |
| **GOLD-daily-2000-2026.csv** | 6,383 | 2000-08-30 → 2026-02-06 | Yahoo source, has tech indicators |
| **GC-4h-2022-2025.csv** | 5,858 | 2022-01-02 → 2025-10-14 | 4-hour bars |
| **GC-1h-2024-2025.csv** | 10,595 | 2024-01-01 → 2025-10-15 | 1-hour bars |
| **GOLD-1h-2000-2026.csv** | 11,423 | 2024-02-11 → 2026-02-06 | 1-hour (Yahoo), only 2yr despite name |
| **GC-1min-2025.csv** | 9,781 | 2025-10-05 → 2025-10-15 | Only 10 days of 1-min! |
| Short-horizon (5m/15m/30m/60m) | Various | 5d/30d/60d windows | No dates in ts column |

### GC MERGE PATH:
- **Daily:** GC-daily-1975-2025.csv (1975-2025) + GOLD-daily-2000-2026.csv (2000-2026, overlapping) → can merge/align for continuous daily series. GOLD has tech indicators.
- **Weekly:** Can derive from daily, but GC-weekly already exists (starts 1974!)
- **Intraday:** 4h (2022-2025) → 1h (2024-2025/2026) → 1min (only 10 days). Large gaps in intermediate periods.
- **GOLD-daily-2000-2026.csv** extends further into 2026 than GC-daily → use to extend daily series

---

## 5. CL (Crude Oil) — ALL FILES GROUPED

| File | Rows | Date Range | Notes |
|------|------|------------|-------|
| **CL-daily-1983-2025.csv** | 10,708 | 1983-03-29 → 2025-10-30 | **Primary daily crude** |
| **CL-4h-2022-2025.csv** | 5,935 | 2022-01-02 → 2025-10-31 | 4-hour bars |
| **CL-1h-2024-2025.csv** | 10,891 | 2024-01-01 → 2025-10-31 | 1-hour bars |
| **CL-30m-2025.csv** | 9,903 | 2025-01-01 → 2025-10-31 | 30-min bars |
| **CL-5m-2025.csv** | 5,519 | 2025-10-05 → 2025-10-31 | Only 26 days of 5-min |
| CL-1d-5y.csv | 1,258 | ~5yr window | Daily subset |

### CL MERGE PATH:
- **Daily:** CL-daily-1983-2025.csv → excellent continuous daily from 1983
- **Intraday:** 4h (2022-2025) → 1h (2024-2025) → 30m (2025) → 5m (Oct 2025 only). These form a hierarchy but cover different time ranges.

---

## 6. 6E (Euro FX) & ZN (10yr T-Note)

**Neither has any long-history files!** Both only appear in:
- Short-horizon window files (5d/30d/60d at 5m/15m/30m/60m resolutions)
- The multi-market ALL-6MARKETS aggregated files
- futures-daily-with-features-24tickers.csv (2002-2025 daily)
- 30yr-cross-asset-market-data.csv (Euro Currency Index, T-Note 10 Years)
- Research/ market-bars/6E-1d-1mo.csv, ZN-1d-1mo.csv (23 rows each, very recent)

**For continuous 6E/ZN series, the only options are:**
1. futures-daily-with-features-24tickers.csv (2002-2025 daily)
2. 30yr-cross-asset-market-data.csv (1995-2025, Euro Currency Index & T-Note 10 Years)
3. Aggregate recent intraday from ALL-6MARKETS files

---

## 7. MULTI-MARKET AGGREGATED FILES (NQ, ES, GC, CL, 6E, ZN)

### ALL-6MARKETS files (free/)
These contain stacked OHLCV data for all 6 instruments with a `symbol` column:
| File | Rows | Period (inferred) | Notes |
|------|------|-------------------|-------|
| ALL-6MARKETS-1m-aggregated.csv | 76,014 | ~2026-04-14 to 2026-06-02 | 1-min, 6 markets, ~49 days |
| ALL-6MARKETS-1m-30d.csv | 175,871 | ~30d window | 1-min |
| ALL-6MARKETS-1m-30d-normalized.csv | 159,522 | ~30d window | Normalized |
| ALL-6MARKETS-1m-10d-normalized.csv | 46,078 | ~10d window | |
| ALL-6MARKETS-1m-5d.csv | 31,850 | ~5d | |
| ALL-6MARKETS-5m-60d.csv | 80,475 | ~60d | 5-min |
| ALL-6MARKETS-15m-60d.csv | 27,176 | ~60d | 15-min |
| ALL-6MARKETS-30m-60d.csv | 13,566 | ~60d | 30-min |
| ALL-6MARKETS-60m-60d.csv | 6,804 | ~60d | 60-min |
→ **All cover recent windows (Apr-Jun 2026), identical schema: `ts, symbol, open, high, low, close, volume`**

### ALL-2MARKETS-NQ-ES files (free/)
Similar structure but only NQ and ES:
| File | Rows | Notes |
|------|------|-------|
| ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv | 56,287 | 21d 1-min normalized |
| ALL-2MARKETS-NQ-ES-1m-5d.csv | 10,975 | 5d 1-min |
| ALL-2MARKETS-NQ-ES-1d-5y.csv | 2,518 | 5yr daily |
| ALL-2MARKETS-NQ-ES-1d-1y.csv | 502 | 1yr daily |
| Various normalized sub-TF | Various | 5m/15m/30m/60m/240m normalized |

### Research/ ALL-6MARKETS files
| File | Rows | Period |
|------|------|--------|
| ALL-6MARKETS-1m-30d.csv | 175,871 | 2026-04-08 to 2026-05-08 |
| ALL-6MARKETS-1m-30d-normalized.csv | 159,522 | Same period |
| ALL-6MARKETS-1m-10d.csv | 46,078 | 2026-05-01 to 2026-05-11 |

### Research/ market-bars (individual instruments)
| File | Rows | Period |
|------|------|--------|
| ES-1d-1mo.csv | ~23 | 2026-05-04 to 2026-06-04 |
| NQ-1d-1mo.csv | ~23 | Same |
| GC-1d-1mo.csv | ~23 | Same |
| CL-1d-1mo.csv | ~23 | Same |
| 6E-1d-1mo.csv | ~23 | Same |
| ZN-1d-1mo.csv | ~23 | Same |
→ **Daily data for last month only (May-June 2026), all same format**

### Research/ crypto-bars
| File | Rows | Period |
|------|------|--------|
| BTCUSD-1d-1mo.csv | ~23 | 2026-05-04 to 2026-06-04 |
| ETHUSD-1d-1mo.csv | ~23 | Same |

---

## 8. RESEARCH: INDIAN MARKETS

| File | Rows | Date Range | Notes |
|------|------|------------|-------|
| **NIFTY50_all.csv** | 235,192 | 2007-11-27 → 2021-04-30 | 50 Indian stocks, 15 cols |
| 49 individual stock CSV files | ~4K-5K each | 2000-01-03 → 2021-04-30 | Same schema as NIFTY50_all |
| stock_metadata.csv | 50 | N/A | Reference data |

All Indian stocks share same format: Date,Symbol,Series,Prev Close,O,H,L,Last,Close,VWAP,Volume,Turnover,Trades,Deliverable Volume,%Deliverble

---

## 9. OTHER FILES

| File | Rows | Notes |
|------|------|-------|
| SP-tick-2000-2019.csv | 13,802,502 | **458.9 MB!** ES tick-level (quote ticks, vol=0), 2000-2019, 4 cols: date,time,price,volume |
| 30yr-symbols-reference.csv | 56 | Symbol reference for 30yr-cross-asset |
| turtle_breakout_sweep.csv | — | Strategy file |
| free-macro-context.latest.csv | 10 | Macro context data |

---

## 10. MERGE RECOMMENDATIONS FOR CONTINUOUS TIME SERIES

### ES (E-mini S&P 500) — Continuous Series
```
Best Daily:   30yr-cross-asset (S&P500, 1995-2025) → futures-daily-features (ES, 2002-2025) → market-bars/ES-1d-1mo (2026)
              30yr-cross-asset has the longest span (1995-2025) with 57 columns of cross-asset context
Best 1-min:   ES-1min-2000-2019.csv (2000-2019) → GAP 2020-2025 → ES-1m-30d.csv (Apr-May 2026)
              SP-tick-2000-2019.csv can provide tick-level backfill for 2000-2019
              NOTE: 6+ year gap in 1-min data! Fill from other sources needed.
Best 60-min:  ES-2000-2019-60m.csv (2000-2019) → GAP → ALL-6MARKETS-60m-60d (Apr-Jun 2026)
              Same 6yr gap.
```

### NQ (Nasdaq-100) — Continuous Series
```
Best Daily:   futures-daily-features (NQ, 2002-2025) → market-bars/NQ-1d-1mo (2026)
Best 1-min:   NONE before 2022-12-26 → NQ-1min-2022-2025.csv (2022-2025) → NQ-1m-30d (2026)
              MAJOR GAP: 22 years (2000-2022) with no NQ intraday data
Best 60-min:  NQ-2022-2025-60m.csv (2022-2025) → ALL-6MARKETS (2026)
```

### GC / Gold — Continuous Series (BEST COVERAGE)
```
Best Daily:   GC-daily-1975-2025.csv (1975-2025) + GOLD-daily-2000-2026.csv (2000-2026)
              → Merge: GC-daily covers 1975-2000, then use GOLD-daily for 2000-2026 (it has indicators)
              → Or GC-weekly for weekly back to 1974!
Best 4h:      GC-4h-2022-2025.csv (2022-2025)
Best 1h:      GC-1h-2024-2025.csv (2024-2025) + GOLD-1h-2000-2026.csv (only 2024-2026)
Best 1-min:   GC-1min-2025.csv (only 10 days in Oct 2025) — very limited
```

### CL (Crude Oil) — Continuous Series
```
Best Daily:   CL-daily-1983-2025.csv (1983-2025) — excellent 42yr continuous
Best 4h:      CL-4h-2022-2025.csv (2022-2025)
Best 1h:      CL-1h-2024-2025.csv (2024-2025)
Best 30m:     CL-30m-2025.csv (2025 only)
Best 5m:      CL-5m-2025.csv (Oct 2025 only)
```

### 6E (Euro FX) — Limited
```
No dedicated long-history files. Use:
- futures-daily-features (2002-2025)
- 30yr-cross-asset (Euro Currency Index, 1995-2025)
- ALL-6MARKETS aggregated for recent intraday
- Research market-bars/6E-1d-1mo for recent daily
```

### ZN (10yr T-Note) — Limited
```
Same situation as 6E:
- futures-daily-features (2002-2025)
- 30yr-cross-asset (T-Note 10 Years, 1995-2025)
- ALL-6MARKETS for recent intraday
- Research market-bars/ZN-1d-1mo for recent daily
```

### Cross-Asset Context
```
30yr-cross-asset-market-data.csv (1995-2025, 57 cols) is a GOLD MINE for multi-market context:
- 7 indices (DAX, DJI, FTSE, HSI, Nasdaq, NYSE, S&P500)
- 18 stocks (AAPL, AMZN, GOOGL, MSFT, NVDA, TSLA, etc.)
- 4 currencies (Euro, Yen, USD)
- 10 commodities (Cocoa through Silver, including WTI, Brent, Gold, Copper)
- 4 bonds (T-Bill 13wk, T-Note 5yr/10yr, T-Bond 30yr)
- 2 crypto (BTC, ETH) — only from ~2020
→ Merge with any instrument-specific file for broader context
```

---

## 11. KEY DATA QUALITY NOTES

1. **futures-daily-with-features-24tickers.csv** has date column populated for **only GF/RTY/YM** — other 21 tickers have empty dates. This is a feature-engineered dataset (Bollinger, Donchian, MA cross, Turtle, returns). Each ticker has ~6,500 rows but dates must be inferred from the index/ticker combination.

2. **The ALL-6MARKETS and ALL-2MARKETS files** use column name `ts` for timestamp but the date parser didn't catch it (named `ts` not `date`/`datetime`). These files have clean OHLCV data but the ts column format varies (ISO, with/without timezone).

3. **GOLD-daily-2000-2026.csv vs GC-daily-1975-2025.csv**: Different data sources (Yahoo Finance vs exchange data). GOLD has tech indicators, GC has longer history. Both need alignment for merged daily gold series.

4. **SP-tick-2000-2019.csv** (459MB) is ES quote-level tick data with volume=0 (quote ticks, not trade ticks). Useful for tick-level analysis but not for volume-based analysis.

5. **The "fresh" suffixed files** (ES-1825d-1d-fresh.csv, ES-60d-15m-fresh.csv, NQ-60d-1y-fresh.csv) appear to be more recently generated versions of other files.

6. **Research/ Indian markets data** ends at 2021-04-30 — stale. NIFTY50_all.csv is the comprehensive file (50 tickers in one).

---

## 12. SUMMARY: QUICK MERGE TABLE

| Instrument | Daily Source | 1-min Source | 60-min Source | Gaps |
|-----------|-------------|-------------|---------------|------|
| **ES** | futures-features (2002-2025) + 30yr-cross-asset (1995-2025) | ES-1min-2000-2019 + ES-1m-30d (2026) | ES-2000-2019-60m + ALL-6MARKETS (2026) | **6yr gap 2020-2025** |
| **NQ** | futures-features (2002-2025) | NQ-1min-2022-2025 + NQ-1m-30d (2026) | NQ-2022-2025-60m + ALL-6MARKETS (2026) | **22yr gap pre-2022** |
| **GC** | GC-daily-1975-2025 + GOLD-daily-2000-2026 | GC-1min-2025 (10 days only) | GC-1h-2024-2025 + GOLD-1h-2000-2026 | **Best coverage, minor gaps** |
| **CL** | CL-daily-1983-2025 | None | CL-1h-2024-2025 | **Best daily, limited intraday** |
| **6E** | futures-features / 30yr-cross-asset | None | ALL-6MARKETS | **No dedicated files** |
| **ZN** | futures-features / 30yr-cross-asset | None | ALL-6MARKETS | **No dedicated files** |
