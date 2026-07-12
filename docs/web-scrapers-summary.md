# Web Scrapers — Summary

Source: https://github.com/je-suis-tm/web-scraping (cloned to `vendor/web-scraping/`)

## Relevant Scrapers

### CME1.py — CME Futures Settlement Data
- **What**: Scrapes CME daily settlement prices for futures
- **Dependencies**: selenium, beautifulsoup4
- **ES/NQ use**: Can fetch settlement/carry data for ES/NQ futures
- **Status**: Uses selenium — needs chromedriver. 7 years old, site may have changed.

### CME2.py — CME Options Chain
- **What**: Scrapes CME options chain data
- **Dependencies**: selenium, beautifulsoup4
- **ES/NQ use**: Options OI, volume, Greeks for ES/NQ options
- **Status**: Same as CME1 — selenium-based, may be broken.

### CME3.py — CME Options Settlement
- **What**: Options settlement prices from CME
- **Dependencies**: selenium, beautifulsoup4
- **Status**: Selenium-based.

### CFTC.py — Commitment of Traders
- **What**: Scrapes CFTC COT reports (legacy + disaggregated)
- **Dependencies**: beautifulsoup4, requests
- **ES/NQ use**: COT data for ES/NQ — commercial/speculative positioning
- **Status**: Uses requests + bs4. Most likely to still work.

### Macrotrends.py — Economic Data
- **What**: Scrapes Macrotrends for economic indicators
- **Dependencies**: pandas, requests
- **Status**: Should work with minor fixes.

## Implementation Decision

**CFTC scraper** is the only one worth integrating now. COT data complements our macro context. But the scraper is 5+ years old and CME/CFTC sites may have changed. Manual testing needed.

**CME scrapers** use selenium which is heavy. Our existing data pipeline (Yahoo v8 API + Polygonscan) covers what we need. Skip for now.

**Next step**: If we want COT data, write a fresh scraper using `requests` + `html.parser` targeting the CFTC's current website structure rather than porting the old one.
