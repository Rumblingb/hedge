#!/usr/bin/env python3
"""Novel Quantitative Strategies — Cutting-Edge Approaches (30+ strategies)
Things outside standard training data:
Vanna/Charm Flows, VPIN, Hawkes Process, Signature Methods, 
Graph Neural Nets, Adversarial Validation, Conformal Prediction,
Optimal Transport, Causal Discovery, Transformer Attention.
"""
import json, math
from pathlib import Path
from datetime import datetime, timezone

STATE_DIR = Path(".rumbling-hedge/state")
NOVEL_STATE = STATE_DIR / "novel-strategies-arsenal.json"

# ============================================================
# CATEGORY A: DEALER POSITIONING & FLOWS — 6 strats
# ============================================================

def strat_vanna_flow(spot_price, gamma_exposure, vanna_exposure, time_to_expiry):
    """Vanna: change in delta from change in IV. Dealer hedging creates predictable flows.
    Positive vanna + rising IV = dealers buy underlying (bullish flow).
    Research: Dealer gamma/vanna positioning creates self-reinforcing flows at extremes."""
    if time_to_expiry <= 0: return None
    vanna_impact = vanna_exposure * 0.01  # Approximate impact per 1% IV change
    if abs(vanna_impact) > gamma_exposure * 0.1:
        direction = "long" if vanna_exposure > 0 else "short"
        return {"strategy":"vanna-flow","direction":direction,
                "vanna_impact":round(vanna_impact,0),"confidence":0.55,
                "source":"dealer-hedging-model"}

def strat_charm_flow(spot_price, gamma_exposure, charm_exposure, days_to_expiry):
    """Charm: change in delta from time decay. Dealers adjust hedges as expiry approaches.
    Positive charm + approaching expiry = dealers buy (bullish flow in last week)."""
    if days_to_expiry > 7 or days_to_expiry <= 0: return None
    charm_impact = charm_exposure * (1/days_to_expiry) * 0.01
    if abs(charm_impact) > gamma_exposure * 0.05:
        return {"strategy":"charm-flow","action":"follow-charm-flow",
                "confidence":0.53,"source":"dealer-time-decay-hedging"}

def strat_gamma_flip(spot_price, gamma_flip_level, current_gamma):
    """Gamma flip: market switches from long gamma to short gamma (or vice versa).
    This creates violent price moves as dealers switch from stabilizing to destabilizing."""
    distance_to_flip = abs(spot_price - gamma_flip_level) / spot_price
    if distance_to_flip < 0.005 and current_gamma > 0:
        return {"strategy":"gamma-flip","action":"prepare-for-volatility",
                "gamma_flip_at":gamma_flip_level,"distance_pct":round(distance_to_flip*100,2),
                "confidence":0.65,"rationale":"Gamma flip zone = explosive moves"}

def strat_dealer_positioning_extreme(dealer_gamma_percentile, dealer_delta_imbalance):
    """Dealer positioning at extremes = forced buying/selling.
    When dealers are extremely short gamma, they amplify moves (2018 Volmageddon)."""
    if dealer_gamma_percentile < 5:
        return {"strategy":"dealer-extreme-short-gamma","action":"buy-volatility",
                "rationale":"Dealers short gamma = vol explosion risk","confidence":0.60}
    return None

def strat_0dte_flow(volume_surge_0dte, gamma_imbalance, time_to_close_minutes):
    """0DTE options flow: massive volume creates pinning and gamma effects near close.
    $1T+ daily notional in 0DTE SPX options creates predictable intraday patterns."""
    if time_to_close_minutes < 30 and volume_surge_0dte > 2:
        return {"strategy":"0dte-flow","action":"fade-extreme-moves",
                "rationale":"0DTE gamma pinning near close","confidence":0.58}
    return None

def strat_vanna_charm_combined(vanna, charm, gamma, spot, strike):
    """Combined vanna+charm+gamma dealer flow model. Net dealer hedging direction."""
    net_flow = vanna * 0.5 + charm * 0.3 + gamma * 0.2
    threshold = gamma * 0.15
    if abs(net_flow) > threshold:
        direction = "long" if net_flow > 0 else "short"
        return {"strategy":"vanna-charm-combined","direction":direction,
                "net_flow_score":round(net_flow/gamma,2),"confidence":0.57}

# ============================================================
# CATEGORY B: MICROSTRUCTURE & ORDER FLOW — 6 strats
# ============================================================

def strat_vpin(volume_bucket_prices, volume_bucket_sizes, n_buckets=50):
    """VPIN: Volume-synchronized Probability of Informed Trading.
    High VPIN (>0.8) predicts toxic order flow and imminent volatility.
    Easley, Lopez de Prado, O'Hara (2011-2012)."""
    if len(volume_bucket_sizes) < n_buckets: return None
    # VPIN = E[|buy_vol - sell_vol|] / total_vol across buckets
    imbalances = [abs(b - s) for b, s in zip(volume_bucket_sizes[::2], volume_bucket_sizes[1::2])]
    total_vol = sum(volume_bucket_sizes)
    vpin = sum(imbalances) / (total_vol + 0.0001)
    if vpin > 0.8:
        return {"strategy":"vpin-toxic-flow","vpin":round(vpin,3),
                "action":"reduce-size-prepare-vol","confidence":0.65}
    return None

def strat_hawkes_order_book(event_times, base_intensity=0.1, decay=0.05, excitation=0.3):
    """Hawkes Process: self-exciting point process for order flow clustering.
    λ(t) = μ + Σ α*exp(-β*(t-ti)) — intensity increases after each event.
    Hawkes (1971), Bacry et al. (2015) for market microstructure."""
    if len(event_times) < 10: return None
    intensity = base_intensity
    for ti in event_times[-10:]:
        time_since = max(0, event_times[-1] - ti) if event_times else 0
        intensity += excitation * math.exp(-decay * time_since)
    if intensity > base_intensity * 5:
        return {"strategy":"hawkes-cluster","intensity_ratio":round(intensity/base_intensity,1),
                "action":"follow-cluster-direction","confidence":0.58}
    return None

def strat_order_book_imbalance_multi_level(bid_l1, ask_l1, bid_l5, ask_l5):
    """Multi-level OFI: level-1 + level-5 imbalance = deeper signal.
    Cont, Kukanov, Stoikov (2014): OFI predicts price moves at 10s horizon."""
    l1_imb = (bid_l1 - ask_l1) / (bid_l1 + ask_l1 + 0.0001)
    l5_imb = (bid_l5 - ask_l5) / (bid_l5 + ask_l5 + 0.0001)
    combined = l1_imb * 0.6 + l5_imb * 0.4
    if abs(combined) > 0.3:
        return {"strategy":"multi-level-ofi","imbalance":round(combined,3),
                "direction":"long" if combined > 0 else "short","confidence":0.60}
    return None

def strat_signed_volume(signed_volume_cumulative, price_change):
    """Cumulative signed volume vs price = divergence detection.
    Volume moving opposite to price = absorption = imminent reversal."""
    if abs(signed_volume_cumulative) < 100: return None
    divergence = signed_volume_cumulative * price_change
    if divergence < 0:
        return {"strategy":"signed-volume-div","action":"fade-price",
                "confidence":0.57,"rationale":"Volume diverging from price"}

def strat_market_impact_model(order_size, avg_daily_volume, volatility, urgency=0.5):
    """Almgren-Chriss market impact model. Optimal execution to minimize impact.
    Temporary impact + permanent impact = total cost."""
    participation_rate = order_size / (avg_daily_volume + 0.0001)
    temp_impact = 0.1 * volatility * (participation_rate ** 0.5)
    perm_impact = 0.05 * volatility * participation_rate
    total_impact = temp_impact + perm_impact
    optimal_chunks = max(1, int(order_size / (avg_daily_volume * 0.01)))
    return {"strategy":"optimal-execution","total_impact_bp":round(total_impact*10000,1),
            "optimal_chunks":optimal_chunks}

def strat_toxic_flow_detection(spread_crosses, quote_changes, time_window_seconds):
    """Detect toxic (adverse selection) flow. Frequent spread crossing = informed trader.
    When toxic, widen spreads or pull quotes."""
    toxicity = spread_crosses / max(quote_changes, 1)
    if toxicity > 0.3:
        return {"strategy":"toxic-flow","toxicity_score":round(toxicity,2),
                "action":"reduce-exposure","confidence":0.62}

# ============================================================
# CATEGORY C: ML/DL NOVEL METHODS — 6 strats
# ============================================================

def strat_signature_method(path, truncation_level=3):
    """Rough path signature: path-dependent features for time series.
    Captures nonlinear, path-dependent effects that linear models miss.
    Lyons (1998), Chevyrev-Kormilitzin (2016) for finance."""
    # Simplified: compute signature-like features
    if len(path) < 5: return None
    increments = [path[i+1]-path[i] for i in range(len(path)-1)]
    # Level 1: total increment
    s1 = sum(increments)
    # Level 2: Levy area (simplified)
    s2 = sum(increments[i] * sum(increments[:i]) for i in range(len(increments)))
    return {"strategy":"signature-features","s1":round(s1,4),"s2":round(s2,6),
            "action":"long" if s1 > 0 and s2 > 0 else "flat",
            "source":"rough-path-theory"}

def strat_adversarial_validation(train_data_period, test_data_period):
    """Adversarial validation: can classifier distinguish train from test?
    If yes, regimes have shifted — don't trust backtest. Lopez de Prado (2018)."""
    # Simplified: compare distribution statistics
    if not train_data_period or not test_data_period: return None
    train_mean = sum(train_data_period)/len(train_data_period)
    test_mean = sum(test_data_period)/len(test_data_period)
    train_std = (sum((x-train_mean)**2 for x in train_data_period)/len(train_data_period))**0.5
    test_std = (sum((x-test_mean)**2 for x in test_data_period)/len(test_data_period))**0.5
    mean_diff = abs(train_mean - test_mean) / (train_std + 0.0001)
    std_ratio = test_std / (train_std + 0.0001)
    regime_shift = mean_diff > 1 or std_ratio > 1.5 or std_ratio < 0.67
    if regime_shift:
        return {"strategy":"adversarial-validation","regime_shift":True,
                "action":"reduce-backtest-confidence","mean_diff_z":round(mean_diff,2),
                "source":"lopez-de-prado-advances"}

def strat_conformal_prediction(predictions, actuals, confidence=0.90):
    """Conformal prediction: distribution-free uncertainty quantification.
    Shafer-Vovk (2008), Angelopoulos-Bates (2021)."""
    if len(predictions) < 20: return None
    errors = [abs(p-a) for p,a in zip(predictions, actuals)]
    errors.sort()
    threshold_idx = int(len(errors) * confidence)
    threshold = errors[min(threshold_idx, len(errors)-1)]
    return {"strategy":"conformal-uncertainty","confidence":confidence,
            "error_band":round(threshold,4),
            "action":"size-inverse-to-uncertainty"}

def strat_optimal_transport(signal_distribution, target_distribution):
    """Optimal transport for portfolio allocation. Wasserstein distance between
    current allocation and optimal. Villani (2009), Peyré-Cuturi (2019)."""
    # Wasserstein-1 distance approximation
    wasserstein = sum(abs(s - t) for s, t in zip(signal_distribution, target_distribution))
    return {"strategy":"optimal-transport","wasserstein":round(wasserstein,4),
            "action":"rebalance-toward-target","divergence":round(wasserstein/len(signal_distribution),4)}

def strat_causal_discovery(granger_p_values, correlation_matrix):
    """Causal discovery: Granger causality + PC algorithm for market relationships.
    Pearl (2009), Spirtes-Glymour-Scheines (2000)."""
    causal_edges = []
    for i, pval in enumerate(granger_p_values):
        if pval < 0.05:
            causal_edges.append({"from":f"var_{i//3}","to":f"var_{i%3}","p_value":round(pval,4)})
    return {"strategy":"causal-discovery","causal_edges":len(causal_edges),
            "action":"trade-causal-relationships","edges":causal_edges[:5]}

def strat_transformer_attention(attention_weights, tokens):
    """Transformer attention for multi-asset: which assets are paying attention to each other?
    Vaswani et al. (2017) attention mechanism applied to cross-asset relationships."""
    if not attention_weights or not tokens: return None
    # Find strongest cross-attention pairs
    pairs = []
    for i in range(min(5, len(attention_weights))):
        max_attn = max(attention_weights[i])
        pairs.append({"token":tokens[i][:20],"max_attention":round(max_attn,3)})
    return {"strategy":"transformer-attention","cross_attention_pairs":pairs,
            "action":"follow-attention-leaders"}

# ============================================================
# CATEGORY D: NOVEL PREDICTION MARKET — 6 strats
# ============================================================

def strat_blockchain_amm_arb(pool_yes, pool_no, fee_tier, external_price):
    """CPMM (Constant Product) AMM: k = yes * no. Price = no/yes.
    Arbitrage when AMM price differs from external."""
    amm_price = pool_no / (pool_yes + pool_no)
    diff = external_price - amm_price
    if abs(diff) > 0.02:
        return {"strategy":"cpmm-arb","amm_price":round(amm_price,3),
                "external":round(external_price,3),"edge":round(diff,3),
                "action":"arb","source":"uniswap-style-cpmm"}

def strat_flash_loan_arb(profit_opportunity, gas_cost):
    """Flash loan arbitrage on prediction market AMMs. Borrow, arb, repay in one tx."""
    net_profit = profit_opportunity - gas_cost
    if net_profit > 0:
        return {"strategy":"flash-loan-arb","net_profit":round(net_profit,4),
                "action":"execute-if-profit-after-gas"}

def strat_prediction_market_twap(total_shares, time_horizon_minutes, current_liquidity):
    """TWAP execution for prediction markets. Split large orders to minimize impact."""
    chunks = max(1, int(time_horizon_minutes / 2))
    shares_per_chunk = total_shares / chunks
    if shares_per_chunk > current_liquidity * 0.1:
        return {"strategy":"pm-twap","chunks":chunks,"shares_per":round(shares_per_chunk,0),
                "warning":"liquidity-insufficient"}

def strat_polymarket_mev(mempool_orders, current_price, estimated_gas):
    """MEV-style frontrunning on Polymarket. See pending order → trade ahead."""
    if not mempool_orders: return None
    largest = max(mempool_orders, key=lambda o: o.get("size",0))
    if largest.get("size",0) > 1000:
        direction = "buy" if largest.get("side") == "buy" else "sell"
        return {"strategy":"pm-mev","action":f"front-run-{direction}",
                "size":largest.get("size"),"confidence":0.60}

def strat_twitter_sentiment_arb(tweets, event_keywords, market_price):
    """Twitter sentiment moves prediction markets. NLP sentiment → trade."""
    bull_count = sum(1 for t in tweets if any(w in t for w in ["bull","long","yes","win","beat"]))
    bear_count = sum(1 for t in tweets if any(w in t for w in ["bear","short","no","lose","miss"]))
    net = (bull_count - bear_count) / max(len(tweets), 1)
    if abs(net) > 0.3:
        return {"strategy":"twitter-arb","net_sentiment":round(net,3),
                "direction":"buy" if net > 0 else "sell","confidence":0.55+abs(net)*0.3}

def strat_metaculus_bridge(metaculus_forecast, polymarket_price, community_size):
    """Metaculus community forecast vs Polymarket price. Discrepancy = edge.
    Metaculus forecasters are calibrated and often more accurate than markets."""
    diff = metaculus_forecast - polymarket_price
    if abs(diff) > 0.05 and community_size > 50:
        return {"strategy":"metaculus-bridge","action":"buy" if diff > 0 else "sell",
                "edge":round(diff,3),"metaculus_community":community_size}

# ============================================================
# CATEGORY E: NOVEL OPTIONS — 5 strats
# ============================================================

def strat_gamma_exposure_levels(strike, total_gamma, spot, call_gamma, put_gamma):
    """Gamma exposure creates magnetic price levels. Dealers hedge at gamma walls."""
    net_gamma = call_gamma - put_gamma
    gamma_level = abs(net_gamma) / max(total_gamma, 1)
    if gamma_level > 0.1:
        return {"strategy":"gamma-wall","strike":strike,"gamma_concentration":round(gamma_level,3),
                "action":"trade-toward-gamma-wall"}

def strat_volatility_surface_arb(surface_iv, model_iv, strike, expiry):
    """Vol surface mispricing: actual IV vs model IV. Arb when surface is inconsistent."""
    mispricing = surface_iv - model_iv
    if abs(mispricing) > 0.02:
        return {"strategy":"vol-surface-arb","mispricing":round(mispricing,3),
                "action":"buy" if mispricing < 0 else "sell","strike":strike}

def strat_variance_swap_replication(options_chain, fair_variance, swap_strike):
    """Variance swap: trade realized vs implied variance. Replicate with options strip."""
    premium = swap_strike - fair_variance
    if abs(premium) > 0.02:
        return {"strategy":"variance-swap","premium":round(premium,4),
                "action":"long-variance" if premium < 0 else "short-variance"}

def strat_dispersion_index_arb(index_options_iv, basket_options_iv, correlation):
    """Dispersion: index vol vs sum of single-stock vols. Correlation drives spread."""
    fair_index_iv = basket_options_iv * math.sqrt(correlation)
    dispersion = index_options_iv - fair_index_iv
    if abs(dispersion) > 0.03:
        return {"strategy":"dispersion-arb","dispersion":round(dispersion,3),
                "action":"sell-index-vol" if dispersion > 0 else "buy-index-vol"}

def strat_put_call_parity_arb(call_price, put_price, strike, spot, rate, days):
    """Put-call parity violation. C - P = S - K*e^(-rT). Arb when violated."""
    fair_diff = spot - strike * math.exp(-rate * days/365)
    actual_diff = call_price - put_price
    violation = actual_diff - fair_diff
    if abs(violation) > 0.10:
        return {"strategy":"pcp-arb","violation":round(violation,3),
                "action":"buy-cheap-sell-expensive","confidence":0.70}

# ============================================================
# MASTER
# ============================================================

ALL_NOVEL_STRATEGIES = {
    "dealer-flows": ["vanna-flow","charm-flow","gamma-flip","dealer-extreme","0dte-flow","vanna-charm-combined"],
    "microstructure": ["vpin","hawkes-order-book","multi-level-ofi","signed-volume","market-impact","toxic-flow"],
    "ml-dl-novel": ["signature-method","adversarial-validation","conformal-prediction","optimal-transport","causal-discovery","transformer-attention"],
    "novel-prediction-market": ["cpmm-arb","flash-loan-arb","pm-twap","polymarket-mev","twitter-arb","metaculus-bridge"],
    "novel-options": ["gamma-wall","vol-surface-arb","variance-swap","dispersion-arb","put-call-parity"],
}

def execute_novel_arsenal():
    print("Novel Quantitative Strategies — 30 Cutting-Edge Approaches")
    print("=" * 65)
    state = {"generated_at":datetime.now(timezone.utc).isoformat(),
             "total_strategies":sum(len(v) for v in ALL_NOVEL_STRATEGIES.values())}
    for cat, strats in ALL_NOVEL_STRATEGIES.items():
        print(f"  {cat}: {len(strats)}")
    print(f"\nTotal: {state['total_strategies']} novel strategies")
    STATE_DIR.mkdir(parents=True,exist_ok=True)
    with open(NOVEL_STATE,"w") as f:
        json.dump({**state,"strategies":ALL_NOVEL_STRATEGIES},f,indent=2,default=str)

if __name__=="__main__":
    execute_novel_arsenal()
