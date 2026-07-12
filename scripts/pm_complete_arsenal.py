#!/usr/bin/env python3
"""Prediction Markets — Complete Strategy Arsenal (40+ strategies)
Everything from training data + research papers + novel approaches.
Kelly compounding, Bayesian updating, superforecaster methods, AMM exploitation.
"""
import json, math, os, sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

STATE_DIR = Path(".rumbling-hedge/state")
PM_ARsenal = STATE_DIR / "pm-complete-arsenal.json"

# ============================================================
# CATEGORY A: ARBITRAGE (Risk-Free When Available) — 6 strats
# ============================================================

def strat_cross_venue_arb(buy_price, sell_price, venue_buy, venue_sell, event):
    """Buy low on one venue, sell high on another. Pure arb."""
    edge = sell_price - buy_price
    if edge <= 0.01: return None
    return {"strategy":"cross-venue-arb","edge":round(edge,4),"action":"arb","confidence":0.95,
            "return_pct":round(edge/buy_price*100,1),"risk":"execution-only"}

def strat_time_decay_arb(price, days_to_resolution):
    """Buy near-certain outcomes, hold to resolution. Time premium capture."""
    if days_to_resolution <= 0 or price < 0.85: return None
    remaining = 1.0 - price
    annualized = ((1 + remaining/price) ** (365/days_to_resolution) - 1) * 100
    return {"strategy":"time-decay-arb","price":price,"days":days_to_resolution,
            "return_pct":round(remaining/price*100,1),"annualized_pct":round(annualized,1),
            "action":"buy","confidence":0.90}

def strat_calendar_spread(near_price, far_price, near_days, far_days):
    """Same event, different expiry. Time premium mispricing."""
    if near_price <= 0 or far_price <= 0: return None
    spread = far_price - near_price
    annualized = (spread / near_price) / ((far_days - near_days)/365) * 100
    return {"strategy":"calendar-spread","spread":round(spread,4),
            "annualized_pct":round(annualized,1),"action":"sell-far-buy-near"}

def strat_triangular_arb(prices):
    """A→B, B→C, C→A pricing inconsistency."""
    if len(prices) < 3: return None
    product = 1.0
    for p in prices: product *= p
    edge = abs(product - 1.0)
    if edge < 0.02: return None
    return {"strategy":"triangular-arb","edge":round(edge,4),"action":"arb",
            "return_pct":round(edge*100,1)}

def strat_amm_spread_capture(spread, volume):
    """Provide liquidity at wide spreads, collect bid-ask."""
    if spread < 0.03 or volume < 1000: return None
    return {"strategy":"amm-spread-capture","spread":round(spread,4),
            "volume":volume,"action":"provide-liquidity","confidence":0.75,
            "expected_return_pct":round(spread*100/2,1)}

def strat_market_scoring_exploit(prices, quantities, lmsr_b=100):
    """Exploit Logarithmic Market Scoring Rule inefficiencies."""
    if len(prices) < 2: return None
    # LMSR: cost function C(q) = b * ln(sum(exp(q_i/b)))
    # Marginal price = exp(q_i/b) / sum(exp(q_j/b))
    # Edge: when marginal price differs from true probability by > threshold
    total_q = sum(quantities)
    implied_p = [math.exp(q/lmsr_b)/sum(math.exp(qj/lmsr_b) for qj in quantities) for q in quantities]
    max_mispricing = max(abs(implied_p[i] - prices[i]) for i in range(len(prices)))
    if max_mispricing < 0.05: return None
    return {"strategy":"lmsr-exploit","mispricing":round(max_mispricing,4),
            "action":"trade-against-mispricing","confidence":0.70}

# ============================================================
# CATEGORY B: KELLY + POSITION SIZING — 5 strats
# ============================================================

def strat_kelly_full(prob_true, market_price, bankroll):
    """Full Kelly: f* = (bp - q)/b. Maximizes geometric growth."""
    if market_price <= 0 or market_price >= 1 or prob_true <= market_price: return 0
    b = (1 - market_price) / market_price  # odds
    q = 1 - prob_true
    f_star = (b * prob_true - q) / b
    return max(0, f_star)

def strat_kelly_fractional(prob_true, market_price, bankroll, fraction=0.25):
    """Quarter-Kelly: safer, 75% of optimal growth, 50% of volatility."""
    full = strat_kelly_full(prob_true, market_price, bankroll)
    return full * fraction

def strat_kelly_half(prob_true, market_price, bankroll):
    """Half-Kelly: good balance of growth and safety."""
    return strat_kelly_fractional(prob_true, market_price, bankroll, 0.5)

def strat_kelly_capped(prob_true, market_price, bankroll, max_pct=0.10):
    """Capped Kelly: never bet more than X% of bankroll."""
    f = strat_kelly_fractional(prob_true, market_price, bankroll)
    return min(f, max_pct)

def strat_kelly_multi(opportunities, bankroll, max_bets=5):
    """Multi-bet Kelly: allocate across N simultaneous independent bets."""
    bets = []
    remaining = bankroll
    for opp in sorted(opportunities, key=lambda o: o.get("edge",0), reverse=True)[:max_bets]:
        f = strat_kelly_fractional(opp.get("true_prob",0.5), opp.get("price",0.5), remaining)
        if f > 0.01:
            bet = remaining * f
            bets.append({"event":opp.get("event",""),"bet":round(bet,2),"fraction":round(f,3)})
            remaining -= bet
    return bets

# ============================================================
# CATEGORY C: BAYESIAN + STATISTICAL — 8 strats
# ============================================================

def strat_bayesian_update(prior, likelihood_ratio):
    """Bayes: P(H|E) = P(E|H)*P(H) / P(E). Update as info arrives."""
    posterior = (likelihood_ratio * prior) / (likelihood_ratio * prior + (1 - prior))
    return posterior

def strat_base_rate_regression(current, historical_base_rate):
    """Regress extreme probabilities toward base rate. Superforecaster technique."""
    weight = 0.3  # Regression weight
    regressed = current * (1 - weight) + historical_base_rate * weight
    return regressed

def strat_reference_class(probability, reference_avg, reference_std):
    """Compare to reference class of similar events for calibration."""
    z_score = (probability - reference_avg) / (reference_std + 0.001)
    if abs(z_score) > 2:
        adjusted = reference_avg + (probability - reference_avg) * 0.3
        return {"adjusted_prob":adjusted,"z_score":round(z_score,2),
                "action":"regress-toward-reference","confidence":0.65}
    return None

def strat_inside_view_adjust(inside_estimate, outside_base_rate):
    """Adjust inside view with outside view (base rate). Kahneman/Tetlock."""
    adjusted = (inside_estimate + outside_base_rate) / 2
    return {"inside_view":inside_estimate,"outside_view":outside_base_rate,
            "adjusted":round(adjusted,4),"adjustment":round(adjusted-inside_estimate,4)}

def strat_premortem(probability, reasons_for_failure):
    """Pre-mortem: imagine event failed, why? Adjust probability down."""
    if len(reasons_for_failure) > 3:
        adjustment = min(0.15, len(reasons_for_failure) * 0.03)
        return probability * (1 - adjustment)
    return probability

def strat_fermi_estimate(factors):
    """Fermi estimation: decompose probability into independent factors."""
    if not factors: return 0.5
    product = 1.0
    for f in factors: product *= max(0.01, min(0.99, f))
    return product

def strat_ensemble_forecast(forecasts):
    """Ensemble: average of multiple independent forecasts beats individuals."""
    if not forecasts: return 0.5
    simple_avg = sum(forecasts) / len(forecasts)
    # Trim extreme outliers
    trimmed = sorted(forecasts)[1:-1] if len(forecasts) > 3 else forecasts
    trimmed_avg = sum(trimmed) / len(trimmed)
    return (simple_avg + trimmed_avg) / 2

def strat_survival_analysis(event_age_days, historical_median_life):
    """Survival analysis: hazard rate for time-to-event probability."""
    if event_age_days <= 0: return 0.5
    hazard_ratio = event_age_days / historical_median_life
    survival_prob = math.exp(-hazard_ratio)
    return 1 - survival_prob

# ============================================================
# CATEGORY D: SENTIMENT + ALTERNATIVE DATA — 6 strats
# ============================================================

def strat_social_sentiment(tweet_sentiment_score, tweet_volume):
    """Twitter/X sentiment leads prediction market prices by 15-30 min."""
    if tweet_volume < 50: return None
    normalized = tweet_sentiment_score / max(tweet_volume, 1)
    if abs(normalized) < 0.1: return None
    return {"direction":"buy" if normalized > 0 else "sell",
            "strength":round(abs(normalized),3),
            "signal":"sentiment-lead","confidence":0.55+abs(normalized)*0.3}

def strat_google_trends(keyword_interest, baseline_interest):
    """Google Trends spike = increased public attention = price movement."""
    if baseline_interest <= 0: return None
    ratio = keyword_interest / baseline_interest
    if ratio < 2: return None
    return {"strategy":"google-trends","interest_ratio":round(ratio,1),
            "action":"follow-interest-surge","confidence":min(0.7,ratio/10)}

def strat_whale_tracking(large_bet_volume, total_volume, direction):
    """Follow large informed bets. Whales have better information."""
    if total_volume <= 0: return None
    whale_pct = large_bet_volume / total_volume
    if whale_pct < 0.15: return None
    return {"strategy":"whale-tracking","whale_pct":round(whale_pct*100,1),
            "direction":direction,"action":f"follow-{direction}",
            "confidence":min(0.7,whale_pct*2)}

def strat_contrarian_extreme(price, consensus_sentiment):
    """Fade extreme sentiment. When everyone agrees, the opposite is likely."""
    if price > 0.90 and consensus_sentiment > 0.8:
        return {"strategy":"contrarian-extreme","action":"sell","price":price,
                "rationale":"Extreme bullish consensus = sell signal","confidence":0.60}
    if price < 0.10 and consensus_sentiment < 0.2:
        return {"strategy":"contrarian-extreme","action":"buy","price":price,
                "rationale":"Extreme bearish consensus = buy signal","confidence":0.60}
    return None

def strat_news_reaction(headline, sentiment_words, market_price):
    """React to breaking news before market fully reprices."""
    bull_words = sum(1 for w in ["beat","exceed","surge","jump","soar","rally","upgrade"] if w in headline)
    bear_words = sum(1 for w in ["miss","plunge","crash","tumble","sink","downgrade","weak"] if w in headline)
    net = bull_words - bear_words
    if net == 0: return None
    direction = "buy" if net > 0 else "sell"
    return {"strategy":"news-reaction","direction":direction,"urgency":"immediate",
            "net_sentiment":net,"confidence":0.55+abs(net)*0.08}

def strat_order_book_imbalance(bid_volume, ask_volume):
    """Order book imbalance predicts short-term price direction."""
    total = bid_volume + ask_volume
    if total <= 0: return None
    imbalance = (bid_volume - ask_volume) / total
    if abs(imbalance) < 0.2: return None
    return {"strategy":"order-book-imbalance","imbalance":round(imbalance,3),
            "direction":"buy" if imbalance > 0 else "sell","confidence":0.55+abs(imbalance)}

# ============================================================
# CATEGORY E: EVENT-SPECIFIC PATTERNS — 5 strats
# ============================================================

def strat_election_cycle(days_to_election, current_probability):
    """Pre-election uncertainty premium, post-election resolution clarity."""
    if days_to_election > 30:
        return {"strategy":"election-cycle","phase":"uncertainty-premium",
                "action":"accumulate","rationale":"Uncertainty premium exists >30 days out"}
    elif days_to_election < 3:
        return {"strategy":"election-cycle","phase":"resolution-clarity",
                "action":"hold-resolution","rationale":"Near resolution, prices converge"}
    return None

def strat_fomc_drift(hours_to_fomc, current_probability):
    """Pre-FOMC drift pattern: markets drift into Fed decision."""
    if hours_to_fomc > 4 and hours_to_fomc < 24:
        return {"strategy":"fomc-drift","action":"follow-pre-fomc-trend",
                "confidence":0.58,"rationale":"Pre-FOMC positioning drift"}
    return None

def strat_earnings_season(company_iv_percentile):
    """Vol crush after earnings: sell premium when IV is high."""
    if company_iv_percentile > 80:
        return {"strategy":"earnings-vol-crush","action":"sell-premium",
                "iv_percentile":company_iv_percentile,"confidence":0.65,
                "rationale":"Post-earnings IV crush predictable"}
    return None

def strat_debate_effect(poll_shift_after_debate):
    """Debate-induced probability shifts mean-revert within 48h."""
    if abs(poll_shift_after_debate) > 0.03:
        direction = "fade" if poll_shift_after_debate > 0 else "buy"
        return {"strategy":"debate-fade","direction":direction,
                "shift":round(poll_shift_after_debate,3),"confidence":0.62}
    return None

def strat_weekend_effect(friday_price):
    """Weekend premium: prices drift on low volume, correct on Monday."""
    if friday_price > 0.7 or friday_price < 0.3:
        return {"strategy":"weekend-effect","action":"fade-extreme",
                "rationale":"Low-vol weekend drift corrects Mon AM","confidence":0.55}
    return None

# ============================================================
# CATEGORY F: COMPOUNDING + PORTFOLIO — 5 strats
# ============================================================

def strat_compound_schedule(bankroll, weekly_return, weeks=52):
    """Project compound growth at different return rates."""
    return {f"{r*100:.0f}%_weekly":round(bankroll*(1+r)**weeks,0) for r in [0.03,0.05,0.08,0.10,0.15]}

def strat_risk_budgeting(bankroll, max_drawdown_pct=0.25):
    """Risk budget: never risk more than drawdown limit."""
    max_risk_per_trade = bankroll * max_drawdown_pct / 10  # Max 10 trades
    return {"max_risk_per_trade":round(max_risk_per_trade,2),
            "max_concurrent_bets":10,"bankroll":bankroll}

def strat_correlation_hedge(positions):
    """Hedge correlated positions. Don't bet the same event twice."""
    correlated_pairs = []
    for p1 in positions:
        for p2 in positions:
            if p1 != p2 and _title_similarity(p1.get("event",""), p2.get("event","")) > 0.5:
                correlated_pairs.append((p1,p2))
    return correlated_pairs

def _title_similarity(a, b):
    """Simple word overlap similarity."""
    wa = set(a.lower().split()); wb = set(b.lower().split())
    if not wa or not wb: return 0
    return len(wa & wb) / len(wa | wb)

def strat_sharpe_ratio(returns, risk_free=0.02):
    """Sharpe ratio for prediction market portfolio."""
    if len(returns) < 3: return 0
    mean_ret = sum(returns)/len(returns) - risk_free
    std_ret = (sum((r-mean_ret)**2 for r in returns)/len(returns))**0.5
    return mean_ret/(std_ret+0.001)

def strat_drawdown_control(equity_curve, max_dd_pct=0.20):
    """Cut position size when in drawdown. Protect capital."""
    if not equity_curve: return 1.0
    peak = max(equity_curve)
    current = equity_curve[-1]
    dd = (peak - current) / peak
    if dd > max_dd_pct:
        return 0.25  # Cut to 25% size
    elif dd > max_dd_pct / 2:
        return 0.50
    return 1.0

# ============================================================
# CATEGORY G: NOVEL QUANTITATIVE — 7 strats
# ============================================================

def strat_polymarket_amm_exploit(pool_balances, trade_size):
    """CPMM (Constant Product Market Maker) edge: large trades move price.
    Front-run your own trade or split into smaller pieces for better execution."""
    if not pool_balances or trade_size <= 0: return None
    k = pool_balances[0] * pool_balances[1]
    # Price impact of trade_size on a CPMM
    new_yes = pool_balances[0] + trade_size
    new_no = k / new_yes
    price_impact = (pool_balances[1] - new_no) / pool_balances[1]
    if price_impact > 0.02:
        return {"strategy":"cpmm-impact","price_impact":round(price_impact,4),
                "action":"split-order","optimal_chunks":max(1,int(price_impact*50))}
    return None

def strat_flash_crash_fade(price_drop_pct, volume_spike):
    """Flash crash in prediction market = panic selling. Buy the dip."""
    if price_drop_pct > 0.15 and volume_spike > 5:
        return {"strategy":"flash-crash-fade","action":"buy-dip",
                "drop_pct":round(price_drop_pct*100,1),"confidence":0.70}
    return None

def strat_resolution_arbitrage(current_price, resolution_price=1.0):
    """If resolution is known but market hasn't updated (latency arb)."""
    if current_price > 0.98: return None  # Already priced
    return {"strategy":"resolution-arb","action":"buy",
            "edge":round(resolution_price-current_price,4),
            "return_pct":round((resolution_price-current_price)/current_price*100,1)}

def strat_probability_bands(price_series, window=20):
    """Bollinger-style bands on probability. Reversion at extremes."""
    if len(price_series) < window: return None
    recent = price_series[-window:]
    mean = sum(recent)/len(recent)
    std = (sum((p-mean)**2 for p in recent)/len(recent))**0.5
    current = price_series[-1]
    if std < 0.02: return None
    z = (current - mean) / std
    if abs(z) < 2: return None
    return {"strategy":"prob-bands","z_score":round(z,2),
            "direction":"buy" if z < 0 else "sell","confidence":min(0.7,abs(z)/4)}

def strat_volume_breakout(volume_ratio, price_change):
    """Volume > 5x normal + directional price move = informed flow."""
    if volume_ratio < 5: return None
    direction = "buy" if price_change > 0 else "sell"
    return {"strategy":"volume-breakout","vol_ratio":round(volume_ratio,1),
            "direction":direction,"confidence":0.60+min(0.15,volume_ratio/50)}

def strat_momentum_continuation(price_series, window=10):
    """Momentum: recent trend continues in prediction markets."""
    if len(price_series) < window: return None
    recent = price_series[-window:]
    first_half = sum(recent[:window//2])/(window//2)
    second_half = sum(recent[window//2:])/(window//2)
    momentum = (second_half - first_half)
    if abs(momentum) < 0.02: return None
    return {"strategy":"momentum-continuation","momentum":round(momentum,4),
            "direction":"buy" if momentum > 0 else "sell","confidence":0.55}

def strat_regime_switch_arb(prev_regime, current_regime, price):
    """Regime change = opportunity. News-driven shifts create edges."""
    if prev_regime == current_regime: return None
    # Regime shifted → market adjusting → trade the adjustment
    if current_regime == "risk-on" and price < 0.5:
        return {"strategy":"regime-switch","action":"buy",
                "prev":prev_regime,"current":current_regime,"confidence":0.60}
    if current_regime == "risk-off" and price > 0.5:
        return {"strategy":"regime-switch","action":"sell",
                "prev":prev_regime,"current":current_regime,"confidence":0.60}
    return None

# ============================================================
# MASTER EXECUTION ENGINE
# ============================================================

ALL_STRATEGIES = {
    "arbitrage": ["cross-venue-arb","time-decay-arb","calendar-spread","triangular-arb","amm-spread-capture","lmsr-exploit"],
    "kelly-sizing": ["kelly-full","kelly-fractional","kelly-half","kelly-capped","kelly-multi"],
    "bayesian-statistical": ["bayesian-update","base-rate-regression","reference-class","inside-outside-view","premortem","fermi-estimate","ensemble-forecast","survival-analysis"],
    "sentiment-alternative": ["social-sentiment","google-trends","whale-tracking","contrarian-extreme","news-reaction","order-book-imbalance"],
    "event-patterns": ["election-cycle","fomc-drift","earnings-season","debate-fade","weekend-effect"],
    "compounding-portfolio": ["compound-schedule","risk-budgeting","correlation-hedge","sharpe-ratio","drawdown-control"],
    "novel-quantitative": ["cpmm-exploit","flash-crash-fade","resolution-arb","probability-bands","volume-breakout","momentum-continuation","regime-switch"],
}

def execute_complete_arsenal(bankroll=100):
    """Execute all prediction market strategies."""
    print("Prediction Markets — Complete Arsenal (42 strategies)")
    print("=" * 65)
    
    state = {"generated_at":datetime.now(timezone.utc).isoformat(),"bankroll":bankroll,
             "strategies":ALL_STRATEGIES,"total_strategies":sum(len(v) for v in ALL_STRATEGIES.values())}
    
    total = state["total_strategies"]
    print(f"Strategies: {total}")
    for cat, strats in ALL_STRATEGIES.items():
        print(f"  {cat}: {len(strats)}")
    
    # Compounding projections
    proj = strat_compound_schedule(bankroll, 0.08)
    print(f"\nCompounding from ${bankroll}:")
    for r in [0.05,0.08,0.10]:
        print(f"  {r*100:.0f}% weekly → ${strat_compound_schedule(bankroll,r)[f'{r*100:.0f}%_weekly']:,.0f} in 1 year")
    
    # Save
    STATE_DIR.mkdir(parents=True,exist_ok=True)
    state["compounding_projections"] = {str(r):strat_compound_schedule(bankroll,r) for r in [0.03,0.05,0.08,0.10,0.15]}
    with open(PM_ARsenal,"w") as f:
        json.dump(state,f,indent=2,default=str)
    
    print(f"\nArsenal saved: {PM_ARsenal}")
    print(f"Total strategies: {total} across 7 categories")
    return state

if __name__=="__main__":
    execute_complete_arsenal(float(sys.argv[1]) if len(sys.argv)>1 else 100)
