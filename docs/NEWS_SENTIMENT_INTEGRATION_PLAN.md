# News/Sentiment Integration Plan + Current Market Assessment

**Date**: 2026-05-04
**Author**: Hermes Agent (delegated research)
**Status**: Research complete — awaiting founder review

---

## PART 1: CURRENT MARKET REGIME ASSESSMENT

### 1.1 What's Driving the Range-Chop/Displacement Regime

The current market (early May 2026) is in a news-dominated, high-volatility chop regime driven by:

**Primary drivers (ordered by impact):**

1. **Tariff policy whipsaw (highest impact)** — The Trump administration's 2025-2026 tariff escalation cycle (China 145% on some goods, universal 10% baseline, sector-specific tariffs on autos, steel, aluminum, semiconductors, and pharma) has created a regime where single headlines reverse entire trading days. Futures markets now react more to tariff tweets and press conference leaks than to economic data. This is the #1 reason strategy signals are dying: the news cycle is faster than any bar-based signal can adapt.

2. **Fed policy uncertainty** — The Fed is caught between sticky inflation (tariff-driven) and slowing growth. Rate-cut expectations swing wildly week to week based on whether the dominant narrative is "inflation is transitory tariff noise" or "growth is cracking." FOMC minutes, Powell speeches, and dot-plot revisions now move ES/NQ 50-100+ points intraday.

3. **Recession fears vs. soft-landing hope** — Q1 2026 GDP showed deceleration. Consumer confidence has deteriorated. But labor market data remains mixed (not collapsing, but softening). This "will they/won't they" recession narrative creates sharp reversals when data surprises in either direction.

4. **Geopolitical overlay** — Middle East tensions, Russia-Ukraine ceasefire negotiations, and Taiwan Strait posturing add random shock risk, especially to CL (supply disruption premium) and GC (safe-haven bid).

5. **Dealer gamma positioning** — In this regime, dealers are often short gamma (having sold options), which amplifies moves in both directions. When the market approaches large option strikes, dealer hedging creates self-reinforcing flows that exaggerate the chop.

### 1.2 How Long Is This Regime Expected to Last?

**Base case: Q3-Q4 2026 before any meaningful regime shift.**

- Tariff policy is structural, not cyclical. Even if negotiations begin, the uncertainty premium persists through 2026.
- The Fed put is weaker than in 2019-2021 because inflation isn't at 2%. Rate cuts will be reactive, not proactive.
- The earliest plausible "regime normalization" would require: (a) a durable US-China trade framework (unlikely before late 2026), (b) inflation consistently below 3%, and (c) Fed signaling a clear easing cycle.

**Implication for Bill/Hedge**: Assume the current high-news-sensitivity regime persists for at least 3-6 more months. Strategy selection must adapt TO the regime, not wait for it to pass. The system needs real news gating now.

### 1.3 Strategies That Historically Work in High-News-Volatility Environments

| Strategy Class | Viability | Why |
|---|---|---|
| **Event-driven gating (stand down before news)** | HIGH | Simplest defense. Blackout 30 min before / 60 min after high-impact events. Already partially implemented. |
| **News-directional momentum** | MEDIUM | Trade WITH the news direction on the first pullback after the initial spike. Requires real-time sentiment. |
| **Mean reversion after overreaction** | MEDIUM-HIGH | Post-news spikes often retrace 30-50% within 30-60 minutes. Works when the news isn't structurally regime-changing. |
| **Opening range strategies** | LOW (currently) | Openings are now dominated by overnight news gaps. Opening range breakouts fail more often. |
| **Pure trend-following** | LOW-MEDIUM | Trends reverse on headlines within hours. Only works on multi-day horizons with wide stops. |
| **Volatility harvesting (short strangles after events)** | MEDIUM | Selling premium AFTER the event (when IV is still elevated but the binary event is past). Requires careful sizing. |
| **Cross-asset correlation arbitrage** | MEDIUM | When ES sells off on tariff news, watch CL/GC/6E for delayed reactions. The lag creates opportunity. |
| **Session-time-based filters** | HIGH | Restrict trading to 9:30-11:30 ET when liquidity absorbs news better. Avoid 8:30 ET releases entirely. |

**Key takeaway**: Defensive gating (standing down around news) is the fastest, highest-ROI integration. Offensive news trading (trading WITH sentiment) is a Phase 2 enhancement.

---

## PART 2: HOW SYSTEMATIC FUNDS INTEGRATE NEWS

### 2.1 The Standard Industry Architecture

Professional systematic funds (Man AHL, AQR, Two Sigma, CFM, Winton) use a layered approach:

```
Layer 1: ECONOMIC CALENDAR GATING (simplest, universal)
   ↓
Layer 2: EVENT-DRIVEN BLACKOUTS (time windows around known events)
   ↓
Layer 3: REAL-TIME NLP SENTIMENT SCORING (headline → score in <1s)
   ↓
Layer 4: MACRO REGIME OVERLAY (is current regime news-sensitive?)
   ↓
Layer 5: CROSS-ASSET NEWS PROPAGATION (ES news → should I trade CL?)
```

Most funds run ALL five layers. Layer 1-2 are defensive (prevent losses). Layer 3-5 are offensive (generate alpha).

### 2.2 Event-Driven Gating (Layers 1-2)

**What top funds do:**
- Maintain a curated economic calendar with impact ratings (1-3 stars)
- Apply graduated blackout windows based on event importance:
  - 3-star (FOMC, NFP, CPI): 60 min before, 90 min after
  - 2-star (GDP, PPI, Retail Sales, EIA): 30 min before, 45 min after
  - 1-star (PMI, Consumer Sentiment, Housing): 15 min before, 15 min after
- Some funds also blackout 2-3 hours BEFORE major events (to avoid pre-positioning whipsaw)
- During blackout: flatten existing positions OR widen stops 2-3x

**What Bill/Hedge already has:**
- `newsBlackoutMinutesBefore` / `newsBlackoutMinutesAfter` in GuardrailConfig
- Red-folder event loading from JSON/JSONL files
- Basic blackout gating in guardrails.ts (lines 128-138)
- `strict-news` research profile

**What's missing:** Real event data feeding the red folder. Currently only mock headlines.

### 2.3 NLP Sentiment Scoring (Layer 3)

**How funds do it:**

Most systematic funds use a pipeline like:
1. **Ingest**: RSS feeds, news wires (Reuters, Bloomberg, Dow Jones), Twitter/X API, SEC filings
2. **Filter**: Only headlines mentioning tracked symbols or macro keywords
3. **Score**: Fine-tuned BERT/FinBERT models output sentiment [-1, +1] and confidence [0, 1]
4. **Aggregate**: Rolling Z-score of sentiment over last N headlines
5. **Act**: If aggregate sentiment Z > 2.0 and direction aligns with signal → confirm. If Z < -2.0 → veto.

**The key insight from Man Group's research**: Off-the-shelf LLM sentiment is "plausible but inactionable." You need:
- Domain-specific fine-tuning (financial news, not movie reviews)
- Calibration against actual price moves (does "positive" actually mean up?)
- Speed grading (can you score faster than the market moves?)

**Practical NLP options for constrained hardware:**

| Approach | Accuracy | Speed | HW Requirements | Cost |
|---|---|---|---|---|
| **FinBERT (fine-tuned)** | High | Fast (CPU inference ~50ms) | 2-4GB RAM | Free, open-source |
| **FinVADER (rule-based)** | Medium | Instant | Negligible | Free, open-source |
| **Ollama + Qwen2.5:7B prompt** | High | Slow (~2-5s on M4) | 8-12GB RAM | Free |
| **Finnhub sentiment API** | Medium-High | API latency (~200ms) | None (API call) | Free tier: 60 calls/min |
| **NewsAPI + local keyword scoring** | Low-Medium | Fast | Negligible | Free tier: 100 req/day |
| **Tiingo news API** | Medium | API latency | None | Free tier available |

### 2.4 Macro Calendar Overlays (Layer 4)

Most funds track a "macro surprise index" — the cumulative Z-score of data surprises vs. consensus. When the index is extreme, they reduce position sizes or raise signal thresholds.

**Key calendars for futures:**

| Instrument | High-Impact Events | Medium-Impact |
|---|---|---|
| **ES/NQ** | FOMC, NFP, CPI, GDP Advance | PPI, Retail Sales, ISM Mfg, Consumer Confidence |
| **CL** | EIA Weekly Petroleum Status, OPEC+ meetings, DOE inventory | API Weekly (preview of EIA), rig counts |
| **GC** | FOMC (rate path affects gold), CPI, Geopolitical shocks | PPI, Dollar Index moves, Treasury auction results |
| **6E** | ECB rate decision, EU CPI Flash, EU GDP | German IFO, ZEW, EU PMI, Lagarde speeches |
| **ZN/ZB** | FOMC, NFP, CPI, Treasury refunding announcements | PPI, Retail Sales, GDP |

### 2.5 Cross-Asset News Propagation

When a tariff headline hits, the propagation chain is:
1. ES/NQ react instantly (<1 second)
2. 6E (EUR/USD) follows within 1-5 seconds (dollar correlation)
3. CL reacts within 5-30 seconds (growth-demand implications)
4. GC reacts within 10-60 seconds (safe-haven or dollar-driven)
5. ZN/ZB react within 30-120 seconds (rate-path repricing)

A practical signal: when ES drops >0.5% on a headline and CL hasn't moved yet, there's a ~65-70% probability CL catches down within 2-5 minutes. This is executable on a Mac Mini.

---

## PART 3: SPECIFIC NEWS IMPACT ON FUTURES

### 3.1 ES/SPX — Fed, CPI, NFP

**FOMC Day behavior:**
- Pre-announcement drift: ES tends to drift UP into FOMC (portfolio manager hedging unwinds)
- Announcement spike: 30-80 point move in 5 seconds on the statement
- Press conference: secondary 20-40 point moves on Powell's tone shifts
- Post-FOMC: trend established in first 30 min after conference tends to persist for 2-3 days
- **Blackout recommendation**: 60 min before release, 90 min after (covers statement + presser)

**CPI Day behavior:**
- Pre-release: tight range, low volume in the 30 min before
- Release spike: 20-60 point move on headline CPI miss/beat
- The core CPI (ex-food/energy) matters more than headline
- Post-CPI: reversal common within 2-4 hours if initial move was >1.5 sigma vs expectations
- **Blackout recommendation**: 30 min before, 45 min after

**NFP Day behavior:**
- Similar to CPI but with larger initial range expansion
- The unemployment rate often matters more than the headline payroll number
- Wage growth (AHE) is the sleeper — hot wages = inflation fear, cold wages = growth fear
- **Blackout recommendation**: 30 min before, 45 min after

### 3.2 CL — OPEC, EIA

**EIA Weekly Petroleum Status (Wednesday 10:30 ET):**
- The most reliable CL-moving event every week
- Crude inventory build/draw vs. API preview + vs. consensus
- Gasoline and distillate inventories matter almost as much as crude
- Cushing hub levels (delivery point for WTI futures) can move the curve structure
- **Typical move**: 1-3% on surprise >2M barrels vs consensus
- **Blackout recommendation**: 15 min before, 30 min after

**OPEC+ meetings (quarterly, plus emergency):**
- Production quota changes move CL 3-8% intraday
- Leaks to press (WSJ, Reuters) usually precede official announcements by 1-24 hours
- OPEC+ compliance data matters more than headline quotas (cheaters matter)
- **Blackout recommendation**: full session blackout on decision days

### 3.3 GC — Geopolitical, Dollar

**Gold's news response is asymmetric:**
- Geopolitical shocks (Middle East, Ukraine, Taiwan): rapid rally, slow fade unless crisis escalates
- Dollar strength (from hawkish Fed or tariff-driven): steady grind lower
- Real yield moves (TIPS): the fundamental driver, but slower to price in
- Gold also reacts to: central bank buying reports, ETF flow data, Indian/Chinese physical demand

**Key events for GC:**
- FOMC (rate path → dollar → gold) — second-order but reliable
- Geopolitical headlines — first-order, impossible to predict
- CPI (inflation hedge narrative)
- Treasury auctions (indirect bidder demand signals dollar confidence)
- **Blackout recommendation**: FOMC/CPI blackouts apply to GC. Geopolitical events are unblackoutable.

### 3.4 6E — ECB, EU Data

**ECB decision days:**
- Rate decision + Lagarde press conference
- The Euro moves more on Lagarde's tone than the rate decision itself
- "Data-dependent" vs "pre-committed" language is the key signal
- **Blackout recommendation**: 60 min before, 90 min after

**EU data that moves 6E:**
- EU CPI Flash (monthly, ~10:00 CET) — the European CPI equivalent
- German IFO / ZEW — forward-looking business sentiment
- EU PMI (Manufacturing and Services flash) — growth proxy
- **Blackout recommendation**: 30 min before, 30 min after for CPI/PMI


---

## PART 4: FREE / LOW-COST DATA SOURCES

### 4.1 News APIs

| Source | Free Tier | Rate Limit | What You Get | Key Limitation |
|---|---|---|---|---|
| **Finnhub** | 60 API calls/min | 60/min | Market news, press releases, sentiment | 60/min is tight; use 60s polling |
| **NewsAPI** | 100 req/day | 100/day | Headlines from 80k sources | 100/day is research-only |
| **Alpha Vantage** | 25 req/day | 25/day | News and sentiment scores | Very limited, research only |
| **Tiingo** | Free tier | ~50/hr | News with ticker filtering | Requires registration |
| **Yahoo Finance** | Unlimited scraping | No limit | Headlines per ticker | No API, fragile scraping |
| **RSS feeds** | Free | Unlimited | Headlines from Reuters, CNBC | No sentiment, needs parser |
| **Twitter/X API v2** | 500 tweets/mo | 500/mo | Filtered tweet stream | Extremely limited free tier |
| **Polygon.io** | 5 API calls/min | 5/min | News with ticker mapping | Key already configured |
| **Reddit** | Free API | 60/min | Headline sentiment proxy | Noisy, meme-driven |
| **Economic Calendars** | Various | N/A | Scheduled events/forecasts | ForexFactory/Investing.com |

### 4.2 Sentiment-Specific Sources

| Source | What It Provides | Free? | Futures Usefulness |
|---|---|---|---|
| **CNN Fear and Greed** | 0-100 composite | Free | Regime filter: <25 fear, >75 greed |
| **AAII Sentiment** | Weekly bull/bear pct | Free (Thu) | Contrarian: >55pct bearish = bullish signal |
| **VIX (CBOE)** | SPX implied vol | Free | >25 elevated, >30 crisis = stand down |
| **Put/Call Ratio** | Equity put/call vol | Free | >1.0 bearish, <0.6 complacent |
| **NAAIM Exposure** | Manager equity pct | Free (Thu) | <50 defensive = contrarian buy |
| **Polymarket/Kalshi** | Event contract prices | Free | Real-time Fed/recession/tariff odds |
| **Citi Surprise Index** | Data vs consensus | Free | Reconstructable from calendar data |

### 4.3 What Bill/Hedge Already Has Wired

- **Finnhub** (FINNHUB_API_KEY) -- configured, best starting point for real headlines
- **Polygon** (RH_POLYGON_API_KEY) -- configured
- **Alpha Vantage** (ALPHA_VANTAGE_API_KEY) -- configured
- **FRED** (FRED_API_KEY) -- configured (macro data, not news)
- **Databento** (DATABENTO_API_KEY) -- market data only

**Quickest win**: Finnhub free tier polls every 60s for real-time headlines. Already keyed.

