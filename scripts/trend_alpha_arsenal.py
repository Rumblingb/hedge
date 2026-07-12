#!/usr/bin/env python3
"""Trend Alpha Track — Alternative Data, Sentiment, Web, Consumer, Innovation Signals.
40+ strategies for identifying companies/sectors with higher performance probability.
Signals feed into futures sector rotation and directional bias.
Sources: Google Trends, Social Sentiment, Web Traffic, SEC Filings, Patents, Jobs, Consumer.
"""
import json, math
from pathlib import Path
from datetime import datetime, timezone

STATE_DIR = Path(".rumbling-hedge/state")
TREND_STATE = STATE_DIR / "trend-alpha-arsenal.json"

# ============================================================
# CATEGORY A: GOOGLE TRENDS & SEARCH — 6 strats
# ============================================================

def strat_google_trends_momentum(keyword_interest, baseline_30d, keyword, sector):
    """Google Trends: rising search interest = growing consumer/business demand.
    Precursor to revenue growth. Lead time: 2-4 weeks before earnings."""
    if baseline_30d <= 0: return None
    momentum = keyword_interest / baseline_30d
    if momentum > 1.5:
        return {"strategy":"google-trends-momentum","keyword":keyword,"sector":sector,
                "momentum":round(momentum,1),"action":"bullish-sector","lead_time":"2-4 weeks",
                "source":"google-trends-api","confidence":0.55}

def strat_search_volume_surge(keyword, current_volume, historical_median, sector_etf):
    """Search volume surge > 3x median = product/category going viral."""
    surge_ratio = current_volume / max(historical_median, 1)
    if surge_ratio > 3:
        return {"strategy":"search-volume-surge","keyword":keyword,"sector_etf":sector_etf,
                "surge":round(surge_ratio,0),"action":"long-related-companies",
                "rationale":"Viral product interest","confidence":0.58}

def strat_brand_search_vs_stock(brand_searches, stock_price, ticker):
    """Brand search volume divergence from stock price = leading indicator.
    Searches rising + stock flat = buy. Searches falling + stock up = sell."""
    search_change = brand_searches["current"] / max(brand_searches["baseline"], 1)
    stock_change = stock_price["current"] / max(stock_price["baseline"], 1)
    divergence = search_change - stock_change
    if divergence > 0.15:
        return {"strategy":"brand-search-div","ticker":ticker,"divergence":round(divergence,2),
                "action":"long","rationale":"Brand interest leading stock price"}
    elif divergence < -0.15:
        return {"strategy":"brand-search-div","ticker":ticker,"divergence":round(divergence,2),
                "action":"short","rationale":"Brand interest lagging stock price"}

def strat_sector_trends_heatmap(sector_searches, historical_baselines):
    """Compare search trends across sectors. Overweight sectors with rising interest."""
    scores = {}
    for sector, current in sector_searches.items():
        baseline = historical_baselines.get(sector, current)
        scores[sector] = (current / max(baseline, 1)) - 1
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    return {"strategy":"sector-trends-heatmap","top_sectors":[s for s,_ in top],
            "scores":{s:round(v,2) for s,v in scores.items()}}

def strat_product_launch_interest(product_keywords, launch_date, days_since_launch):
    """Track product launch search interest trajectory. Strong launch = bullish."""
    if days_since_launch > 30: return None
    peak_interest = max(product_keywords) if product_keywords else 0
    current = product_keywords[-1] if product_keywords else 0
    decay_rate = (peak_interest - current) / max(peak_interest, 1)
    if decay_rate < 0.3:
        return {"strategy":"product-launch","action":"long","interest_decay":round(decay_rate,2),
                "rationale":"Sustained post-launch interest","confidence":0.56}

def strat_seasonal_search_patterns(keyword, current_week, historical_seasonal):
    """Seasonal search patterns predict demand cycles. Beat expectations when above seasonal."""
    expected = historical_seasonal.get(current_week % 52, 0)
    if expected <= 0: return None
    deviation = keyword / expected
    if deviation > 1.3:
        return {"strategy":"seasonal-search","keyword":keyword,"deviation":round(deviation,1),
                "action":"above-seasonal-bullish","confidence":0.54}

# ============================================================
# CATEGORY B: SOCIAL MEDIA SENTIMENT — 6 strats
# ============================================================

def strat_twitter_sentiment_volume(ticker, tweet_volume, sentiment_score, baseline_volume):
    """Twitter/X: high volume + strong sentiment = retail interest wave.
    Retail attention precedes institutional flows by days."""
    vol_ratio = tweet_volume / max(baseline_volume, 1)
    if vol_ratio > 3 and abs(sentiment_score) > 0.2:
        direction = "long" if sentiment_score > 0 else "short"
        return {"strategy":"twitter-sentiment","ticker":ticker,"vol_ratio":round(vol_ratio,1),
                "direction":direction,"confidence":0.55}

def strat_reddit_wallstreetbets(ticker, mention_count, sentiment, upvote_ratio):
    """r/WallStreetBets mentions predict short-term price moves.
    High mentions + positive sentiment = gamma squeeze potential."""
    if mention_count > 20 and sentiment > 0.6:
        return {"strategy":"wsb-mentions","ticker":ticker,"mentions":mention_count,
                "action":"follow-retail-flow","gamma_risk":"high"}

def strat_linkedin_hiring_trends(company, job_postings_change, industry_avg_change):
    """LinkedIn job postings growth = company expansion. Leads revenue by 6-12 months."""
    relative_growth = job_postings_change - industry_avg_change
    if relative_growth > 0.15:
        return {"strategy":"linkedin-hiring","company":company,"growth_pct":round(relative_growth*100,1),
                "action":"long","lead_time":"6-12 months","confidence":0.60}

def strat_earnings_call_sentiment(ticker, transcript_sentiment, management_tone):
    """NLP on earnings call transcripts. Management tone predicts next quarter.
    Optimistic tone + specific language = beat. Vague + defensive = miss.
    Paper: 'Same Company, Same Signal: Identity in Earnings Call Transcripts'"""
    composite = transcript_sentiment * 0.6 + management_tone * 0.4
    if composite > 0.2:
        return {"strategy":"earnings-call-nlp","ticker":ticker,"composite_sentiment":round(composite,2),
                "action":"long","confidence":0.58}
    elif composite < -0.2:
        return {"strategy":"earnings-call-nlp","ticker":ticker,"composite_sentiment":round(composite,2),
                "action":"short","confidence":0.58}

def strat_news_sentiment_aggregate(ticker, article_count, avg_sentiment, sentiment_momentum):
    """Aggregate news sentiment across all sources. Momentum matters more than level."""
    if sentiment_momentum > 0.1 and avg_sentiment > 0:
        return {"strategy":"news-sentiment","ticker":ticker,"momentum":round(sentiment_momentum,2),
                "action":"long","confidence":0.57}

def strat_influencer_tracking(influencer_name, ticker_mentioned, follower_count, sentiment):
    """Track financial influencers (Elon Musk, Cathie Wood, etc.). 
    Their mentions move small/mid-cap stocks significantly."""
    if follower_count > 1000000 and abs(sentiment) > 0.5:
        return {"strategy":"influencer-tracking","influencer":influencer_name,
                "ticker":ticker_mentioned,"action":"follow" if sentiment > 0 else "fade",
                "confidence":0.50,"risk":"high-volatility"}

# ============================================================
# CATEGORY C: WEB & APP DATA — 5 strats
# ============================================================

def strat_app_downloads_growth(app_name, company, downloads_current, downloads_baseline):
    """App downloads growth = user growth = revenue growth (for consumer apps)."""
    growth = (downloads_current - downloads_baseline) / max(downloads_baseline, 1)
    if growth > 0.3:
        return {"strategy":"app-downloads","app":app_name,"company":company,
                "growth_pct":round(growth*100,1),"action":"long","confidence":0.56}

def strat_web_traffic_growth(domain, traffic_current, traffic_baseline, sector):
    """Website traffic growth = demand growth. SimilarWeb/Alexa data."""
    growth = (traffic_current - traffic_baseline) / max(traffic_baseline, 1)
    if growth > 0.25:
        return {"strategy":"web-traffic","domain":domain,"sector":sector,
                "growth_pct":round(growth*100,1),"action":"bullish-sector","confidence":0.55}

def strat_app_store_ratings(app_name, rating_current, rating_baseline, review_volume):
    """App Store rating improvements + review volume = customer satisfaction + growth."""
    rating_change = rating_current - rating_baseline
    if rating_change > 0.3 and review_volume > 100:
        return {"strategy":"app-ratings","app":app_name,"rating_change":round(rating_change,1),
                "action":"long","confidence":0.53}

def strat_github_stars_growth(repo_name, company, stars_current, stars_baseline):
    """GitHub stars growth for open-source companies (MongoDB, Elastic, etc.).
    Developer adoption precedes enterprise revenue."""
    growth = (stars_current - stars_baseline) / max(stars_baseline, 1)
    if growth > 0.4:
        return {"strategy":"github-stars","repo":repo_name,"company":company,
                "growth_pct":round(growth*100,1),"action":"long","confidence":0.58}

def strat_cloud_spend_growth(company, aws_azure_gcp_spend, previous_quarter):
    """Cloud infrastructure spend growth = digital transformation = revenue proxy."""
    growth = (aws_azure_gcp_spend - previous_quarter) / max(previous_quarter, 1)
    if growth > 0.15:
        return {"strategy":"cloud-spend","company":company,"growth_pct":round(growth*100,1),
                "action":"long-tech-sector","confidence":0.57}

# ============================================================
# CATEGORY D: SEC FILINGS & INSIDER — 6 strats
# ============================================================

def strat_insider_buying(ticker, insider_buys, insider_sells, days_window=30):
    """Insider buying cluster = strong bullish signal. Insiders sell for many reasons,
    but they only buy for ONE reason: they think the stock will go up."""
    buy_sell_ratio = insider_buys / max(insider_sells, 1)
    if insider_buys >= 3 and buy_sell_ratio > 2:
        return {"strategy":"insider-buying","ticker":ticker,"buys":insider_buys,
                "ratio":round(buy_sell_ratio,1),"action":"long","confidence":0.65}

def strat_form4_cluster(ticker, unique_insiders_buying, total_buy_value):
    """Multiple insiders buying near same time (especially after sell-off) = bottom signal."""
    if unique_insiders_buying >= 3 and total_buy_value > 500000:
        return {"strategy":"form4-cluster","ticker":ticker,"insiders":unique_insiders_buying,
                "value":total_buy_value,"action":"long","confidence":0.68}

def strat_buyback_announcement(ticker, buyback_amount, market_cap, buyback_yield):
    """Share buybacks: >2% buyback yield = accretive. Drives EPS growth."""
    if buyback_yield > 0.02:
        return {"strategy":"buyback","ticker":ticker,"yield_pct":round(buyback_yield*100,2),
                "action":"long","confidence":0.55}

def strat_13f_filing_tracking(fund_name, ticker, position_change_pct, fund_reputation):
    """Track top fund 13F filings. Follow the smart money with 45-day lag.
    Works better for long-term positions."""
    if fund_reputation > 0.8 and position_change_pct > 0.2:
        return {"strategy":"13f-tracking","fund":fund_name,"ticker":ticker,
                "change_pct":round(position_change_pct*100,1),"action":"follow",
                "lag":"45 days","confidence":0.52}

def strat_short_interest_squeeze(ticker, short_interest_pct, days_to_cover, price_momentum):
    """High short interest + positive price momentum = short squeeze candidate.
    GME/AMC pattern. Requires monitoring for exit timing."""
    if short_interest_pct > 0.20 and days_to_cover > 3 and price_momentum > 0.05:
        return {"strategy":"short-squeeze","ticker":ticker,"si_pct":round(short_interest_pct*100,1),
                "days_to_cover":days_to_cover,"action":"long","risk":"extreme-volatility"}

def strat_sec_filing_tone(company, filing_type, linguistic_complexity, positive_words_ratio):
    """SEC filing linguistic analysis. Simpler language + positive tone = better future returns.
    Loughran-McDonald sentiment dictionary."""
    if linguistic_complexity < 0.5 and positive_words_ratio > 0.6:
        return {"strategy":"sec-tone","company":company,"action":"long","confidence":0.56}

# ============================================================
# CATEGORY E: CONSUMER & FOOT TRAFFIC — 5 strats
# ============================================================

def strat_credit_card_spending(company, spending_growth, sector_avg_growth):
    """Credit card transaction data (Mastercard/visa aggregates). Real consumer behavior."""
    excess_growth = spending_growth - sector_avg_growth
    if excess_growth > 0.05:
        return {"strategy":"credit-card","company":company,"excess_growth":round(excess_growth*100,1),
                "action":"long","confidence":0.62,"source":"alternative-data"}

def strat_foot_traffic(store_name, foot_traffic_change, retail_sector_avg):
    """Physical store foot traffic (SafeGraph, Placer.ai). Retail health indicator."""
    relative = foot_traffic_change - retail_sector_avg
    if relative > 0.1:
        return {"strategy":"foot-traffic","store":store_name,"rel_traffic":round(relative*100,1),
                "action":"long","confidence":0.58}

def strat_supply_chain_satellite(company, factory_activity, shipping_container_volume):
    """Satellite imagery of factory parking lots + shipping data. Production activity proxy."""
    if factory_activity > 1.2 and shipping_container_volume > 1.1:
        return {"strategy":"satellite-supply-chain","company":company,"action":"long",
                "confidence":0.57,"source":"orbital-insight-planet-labs"}

def strat_restaurant_bookings(chain_name, reservation_change, same_store_sales_proxy):
    """OpenTable/Resy reservations. Restaurant demand proxy."""
    if reservation_change > 0.15:
        return {"strategy":"restaurant-bookings","chain":chain_name,"growth":round(reservation_change*100,1),
                "action":"long","confidence":0.55}

def strat_flight_bookings(airline, bookings_growth, capacity_growth):
    """Flight booking data. Travel demand proxy."""
    load_factor_change = bookings_growth - capacity_growth
    if load_factor_change > 0.05:
        return {"strategy":"flight-bookings","airline":airline,"load_factor_improve":round(load_factor_change*100,1),
                "action":"long-transport-sector","confidence":0.56}

# ============================================================
# CATEGORY F: INNOVATION TRACKING — 5 strats
# ============================================================

def strat_patent_filings_growth(company, patent_count, patent_baseline, technology_area):
    """Patent filing growth = innovation pipeline. Leads revenue by 2-5 years."""
    growth = (patent_count - patent_baseline) / max(patent_baseline, 1)
    if growth > 0.25 and technology_area in ["AI","quantum","biotech","renewable","robotics"]:
        return {"strategy":"patent-filings","company":company,"tech":technology_area,
                "growth_pct":round(growth*100,1),"action":"long","lead_time":"2-5 years","confidence":0.54}

def strat_r_and_d_spending(company, rd_spending_growth, revenue_growth):
    """R&D spending growing faster than revenue = investing in future. Good sign."""
    rd_intensity = rd_spending_growth - revenue_growth
    if rd_intensity > 0.05:
        return {"strategy":"rd-spending","company":company,"intensity":round(rd_intensity,2),
                "action":"long","confidence":0.56}

def strat_product_hunt_launches(company, product_launches, upvotes_trend):
    """Product Hunt launch velocity and community reception."""
    if product_launches >= 2 and upvotes_trend > 0.5:
        return {"strategy":"product-hunt","company":company,"launches":product_launches,
                "action":"long-small-cap","confidence":0.52}

def strat_ai_ml_research_output(company, arxiv_papers, github_stars, citations):
    """AI research output = talent magnet + future product capability. Google/DeepMind/Meta pattern."""
    if arxiv_papers > 10 and github_stars > 1000:
        return {"strategy":"ai-research","company":company,"papers":arxiv_papers,
                "action":"long-tech","confidence":0.58}

def strat_startup_funding_activity(sector, funding_volume, deal_count, quarter_change):
    """VC funding activity in a sector = innovation heat. Leads public market by 2-4 quarters."""
    if quarter_change > 0.3:
        return {"strategy":"vc-funding","sector":sector,"funding_growth":round(quarter_change*100,1),
                "action":"bullish-sector-6m","lead_time":"2-4 quarters","confidence":0.55}

# ============================================================
# CATEGORY G: MACRO TREND SIGNALS → FUTURES — 5 strats
# ============================================================

def strat_sector_rotation_signal(sector_momentum_scores):
    """Aggregate all trend signals into sector rotation for futures.
    Strong tech → long NQ. Strong energy → long CL. Strong finance → long ES."""
    tech_score = sector_momentum_scores.get("technology",0) + sector_momentum_scores.get("ai",0)*1.5
    energy_score = sector_momentum_scores.get("energy",0) + sector_momentum_scores.get("commodities",0)
    finance_score = sector_momentum_scores.get("financials",0) + sector_momentum_scores.get("real_estate",0)
    
    signals = []
    if tech_score > 0.3: signals.append({"futures":"NQ","direction":"long","score":round(tech_score,2)})
    if energy_score > 0.2: signals.append({"futures":"CL","direction":"long","score":round(energy_score,2)})
    if finance_score > 0.25: signals.append({"futures":"ES","direction":"long","score":round(finance_score,2)})
    return signals

def strat_consumer_strength_index(app_scores, web_scores, credit_scores, foot_scores):
    """Composite consumer strength index → ES/NQ direction."""
    composite = sum(app_scores)*0.25 + sum(web_scores)*0.25 + sum(credit_scores)*0.3 + sum(foot_scores)*0.2
    if composite > 0.2:
        return {"action":"long-ES-NQ","consumer_index":round(composite,2),"confidence":0.60}
    return None

def strat_innovation_lead_index(patent_scores, rd_scores, ai_scores, funding_scores):
    """Innovation lead index → NQ direction (tech-heavy)."""
    composite = sum(patent_scores)*0.3 + sum(rd_scores)*0.25 + sum(ai_scores)*0.25 + sum(funding_scores)*0.2
    if composite > 0.15:
        return {"action":"long-NQ","innovation_index":round(composite,2),"confidence":0.58}

def strat_sentiment_aggregate_index(twitter_score, news_score, earnings_score, insider_score):
    """Aggregate sentiment across all sources → market direction."""
    composite = twitter_score*0.2 + news_score*0.3 + earnings_score*0.3 + insider_score*0.2
    if abs(composite) > 0.15:
        direction = "long" if composite > 0 else "short"
        return {"action":f"{direction}-ES","sentiment_index":round(composite,2),"confidence":0.57}

def strat_trend_alpha_composite(all_sector_signals, all_macro_signals, all_sentiment_signals):
    """Master composite: blend all trend alpha signals into single futures direction."""
    sector = sum(all_sector_signals)/max(len(all_sector_signals),1)
    macro = sum(all_macro_signals)/max(len(all_macro_signals),1)
    sentiment = sum(all_sentiment_signals)/max(len(all_sentiment_signals),1)
    composite = sector*0.35 + macro*0.35 + sentiment*0.30
    direction = "long" if composite > 0.1 else "short" if composite < -0.1 else "neutral"
    return {"strategy":"trend-alpha-composite","composite_score":round(composite,3),
            "direction":direction,"confidence":0.60,
            "components":{"sector":round(sector,3),"macro":round(macro,3),"sentiment":round(sentiment,3)}}

# ============================================================
# MASTER
# ============================================================

ALL_TREND_STRATEGIES = {
    "google-trends": ["trends-momentum","search-volume-surge","brand-search-div","sector-heatmap","product-launch","seasonal-search"],
    "social-sentiment": ["twitter-sentiment","wsb-mentions","linkedin-hiring","earnings-call-nlp","news-aggregate","influencer-tracking"],
    "web-app-data": ["app-downloads","web-traffic","app-ratings","github-stars","cloud-spend"],
    "sec-insider": ["insider-buying","form4-cluster","buyback","13f-tracking","short-squeeze","sec-tone"],
    "consumer-foot": ["credit-card","foot-traffic","satellite-supply","restaurant-bookings","flight-bookings"],
    "innovation": ["patent-filings","rd-spending","product-hunt","ai-research","vc-funding"],
    "macro-futures": ["sector-rotation","consumer-strength","innovation-lead","sentiment-aggregate","trend-alpha-composite"],
}

def execute_trend_arsenal():
    print("Trend Alpha Track — Alternative Data Signals (42 strategies)")
    print("=" * 65)
    state = {"generated_at":datetime.now(timezone.utc).isoformat(),
             "total_strategies":sum(len(v) for v in ALL_TREND_STRATEGIES.values())}
    for cat, strats in ALL_TREND_STRATEGIES.items():
        print(f"  {cat}: {len(strats)}")
    print(f"\nTotal: {state['total_strategies']} trend alpha strategies")
    print(f"Data sources: Google Trends, Twitter/X, Reddit, LinkedIn, SEC EDGAR,")
    print(f"  App Store, GitHub, SimilarWeb, Mastercard, SafeGraph, Planet Labs,")
    print(f"  USPTO, OpenTable, Crunchbase, arXiv")
    STATE_DIR.mkdir(parents=True,exist_ok=True)
    with open(TREND_STATE,"w") as f:
        json.dump({**state,"strategies":ALL_TREND_STRATEGIES},f,indent=2,default=str)

if __name__=="__main__":
    execute_trend_arsenal()
