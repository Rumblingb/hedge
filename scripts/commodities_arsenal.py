#!/usr/bin/env python3
"""Commodities Trading — Complete Strategy Arsenal (48 strategies)
Energy, Metals, Agriculture, Livestock, Softs.
Carry, Seasonality, Spreads, COT, Weather, Supply Chain, Super-Cycle.
"""
import json, math, sys
from pathlib import Path
from datetime import datetime, timezone

STATE_DIR = Path(".rumbling-hedge/state")
CMD_ARsenal = STATE_DIR / "commodities-complete-arsenal.json"

# ============================================================
# CATEGORY A: ENERGY (Crude, NG, Gasoline, Heating Oil) — 10
# ============================================================

def strat_cl_eia_crude(actual_change, forecast_change):
    """EIA weekly inventory: larger-than-expected draw = bullish, build = bearish."""
    surprise = actual_change - forecast_change
    if abs(surprise) < 1: return None  # million barrels
    return {"strategy":"eia-inventory","commodity":"CL","surprise_mb":round(surprise,1),
            "direction":"long" if surprise < 0 else "short","confidence":0.65}

def strat_ng_storage(natgas_storage, five_yr_avg, season):
    """Natural gas storage vs 5-year average. Below avg = bullish winter."""
    deficit_pct = (five_yr_avg - natgas_storage) / five_yr_avg * 100
    if deficit_pct > 10 and season in ["winter","pre-winter"]:
        return {"strategy":"ng-storage","commodity":"NG","deficit_pct":round(deficit_pct,1),
                "action":"long","rationale":"Below-avg storage heading into winter","confidence":0.60}

def strat_crack_spread(crude_price, gasoline_price, heating_oil_price):
    """3-2-1 crack spread: 3 crude → 2 gas + 1 HO. Wide spread = strong refining margin."""
    spread = (2*gasoline_price + heating_oil_price)/3 - crude_price
    z = spread / crude_price * 100
    return {"strategy":"crack-spread","spread":round(spread,2),"spread_pct":round(z,1),
            "action":"long-crack" if z > 15 else "short-crack" if z < 5 else "neutral"}

def strat_cl_seasonality(month):
    """Crude oil seasonal patterns: Spring driving season = bullish, Fall maintenance = bearish."""
    seasonal_bias = {3:0.6,4:0.65,5:0.60,6:0.55,9:0.45,10:0.40,11:0.45}
    return seasonal_bias.get(month,0.5)

def strat_ng_seasonality(month):
    """Natural gas: Nov-Feb bullish (heating), Mar-Apr bearish (injection), May-Oct neutral."""
    if month in [11,12,1,2]: return 0.65
    elif month in [3,4]: return 0.35
    return 0.50

def strat_rb_driving_season(month, inventory_level, days_to_memorial):
    """Gasoline: Memorial Day to Labor Day bullish if inventories low."""
    if 5 <= month <= 8 and inventory_level < 0.9:
        return {"strategy":"gasoline-driving","commodity":"RB","action":"long","confidence":0.58}

def strat_ho_winter(month, heating_degree_days, inventory):
    """Heating oil: cold winter + low inventory = bullish."""
    if month in [11,12,1,2] and heating_degree_days > 1.1:
        return {"strategy":"heating-oil-winter","commodity":"HO","action":"long","confidence":0.60}

def strat_cl_opec(days_to_opec, current_quota, rumored_change):
    """OPEC meeting: production cut = bullish, increase = bearish."""
    if days_to_opec > 7: return None
    return {"strategy":"opec-meeting","commodity":"CL","action":"long" if rumored_change < 0 else "short",
            "confidence":0.55}

def strat_cl_geopolitical(region, supply_at_risk_mbd):
    """Geopolitical supply disruption: Middle East, Venezuela, Russia."""
    if supply_at_risk_mbd > 0.5:
        return {"strategy":"geopolitical-supply","commodity":"CL","region":region,
                "action":"long","barrels_at_risk":supply_at_risk_mbd,"confidence":0.62}

def strat_energy_sector_rotation(cl_position, ng_position, economic_cycle):
    """Rotate between crude and natgas based on economic cycle."""
    if economic_cycle == "expansion": return {"overweight":"CL","underweight":"NG"}
    elif economic_cycle == "winter": return {"overweight":"NG","underweight":"CL"}
    return {"equal_weight":True}

# ============================================================
# CATEGORY B: PRECIOUS METALS (Gold, Silver, Platinum) — 8
# ============================================================

def strat_gold_silver_ratio(ratio, z_score):
    """Gold/Silver ratio mean-reversion. >90 = silver undervalued, <50 = silver overvalued."""
    if z_score > 2: return {"strategy":"gsr-mean-rev","action":"long-silver-short-gold",
            "ratio":round(ratio,1),"z_score":round(z_score,2),"confidence":0.65}
    if z_score < -2: return {"strategy":"gsr-mean-rev","action":"long-gold-short-silver",
            "ratio":round(ratio,1),"z_score":round(z_score,2),"confidence":0.60}

def strat_gold_real_yields(real_yield_change, gold_price_change):
    """Gold inversely correlated with real yields. Yields up = gold down."""
    if real_yield_change > 0.2 and gold_price_change > 0:
        return {"strategy":"gold-real-yields","action":"fade-gold-rally","confidence":0.60}
    return None

def strat_gold_inflation_hedge(cpi_surprise):
    """Gold rises on inflation surprises. Buy on CPI beat."""
    if cpi_surprise > 0.2:
        return {"strategy":"gold-inflation","action":"long-gold","rationale":"CPI beat","confidence":0.58}

def strat_gold_geopolitical(vix_spike, geopolitical_index):
    """Gold safe haven. Buy on geopolitical crises."""
    if vix_spike > 5 or geopolitical_index > 0.7:
        return {"strategy":"gold-safe-haven","action":"long-gold","confidence":0.65}

def strat_platinum_palladium(ratio, auto_sales_trend):
    """Platinum/Palladium ratio driven by auto catalyst demand. Pd for gas, Pt for diesel."""
    return {"strategy":"pt-pd-ratio","ratio":round(ratio,2),"auto_trend":auto_sales_trend}

def strat_gold_central_bank(central_bank_buying_tonnes, price):
    """Central bank gold buying = structural bid. Follow the buyers."""
    if central_bank_buying_tonnes > 50:
        return {"strategy":"central-bank-gold","action":"long","tonnes":central_bank_buying_tonnes}

def strat_silver_industrial(manufacturing_pmi, solar_demand_growth):
    """Silver: industrial demand (solar panels) + precious metal. PMI > 50 = bullish."""
    if manufacturing_pmi > 50 and solar_demand_growth > 0.1:
        return {"strategy":"silver-industrial","action":"long","pmi":manufacturing_pmi}

def strat_gold_seasonality(month):
    """Gold seasonality: Sep-Nov strong (Indian wedding season, Diwali), Jun-Jul weak."""
    if month in [9,10,11]: return 0.62
    if month in [6,7]: return 0.42
    return 0.50

# ============================================================
# CATEGORY C: BASE METALS (Copper, Aluminum, Zinc) — 6
# ============================================================

def strat_copper_gold_ratio(ratio):
    """'Dr. Copper' — copper/gold ratio predicts economic activity. Falling = recession."""
    if ratio < 0.00015: return {"strategy":"copper-gold","signal":"recession-warning","action":"defensive"}

def strat_copper_china(china_pmi, copper_inventory_shfe):
    """China drives 50%+ of copper demand. PMI > 50 + low inventory = bullish."""
    if china_pmi > 50 and copper_inventory_shfe < 0.8:
        return {"strategy":"copper-china","action":"long-copper","confidence":0.62}

def strat_copper_electrification(ev_sales_growth, grid_investment_growth):
    """Electrification super-cycle: EVs + grid = copper demand boom."""
    if ev_sales_growth > 0.2 and grid_investment_growth > 0.1:
        return {"strategy":"copper-super-cycle","action":"structural-long","confidence":0.55}

def strat_aluminum_energy(energy_cost_pct, aluminum_price):
    """Aluminum = solidified electricity. Energy costs > 40% of production."""
    if energy_cost_pct > 0.45:
        return {"strategy":"aluminum-energy","action":"long","rationale":"Energy cost floor"}

def strat_metal_supply_chain(warehouse_inventory, shipment_delays, country):
    """Supply chain disruption in metals = price spike."""
    if shipment_delays > 1.5 and warehouse_inventory < 0.7:
        return {"strategy":"metal-supply-shock","action":"long","country":country}

def strat_base_metal_index_rotation(manufacturing_cycle_phase):
    """Rotate between base metals based on manufacturing cycle."""
    phases = {"early":"long-copper","mid":"long-aluminum","late":"long-zinc","recession":"flat"}
    return {"strategy":"metal-rotation","phase":manufacturing_cycle_phase,
            "action":phases.get(manufacturing_cycle_phase,"neutral")}

# ============================================================
# CATEGORY D: AGRICULTURE (Grains, Softs) — 10
# ============================================================

def strat_bean_crush(soybean_price, meal_price, oil_price):
    """Soybean crush spread: beans → meal + oil. Processing margin."""
    crush = (0.8*meal_price + 0.18*oil_price) - soybean_price
    return {"strategy":"soybean-crush","crush_margin":round(crush,2)}

def strat_grain_seasonality(month, grain):
    """Grains: planting (Apr-May) = uncertainty premium, harvest (Sep-Oct) = price pressure."""
    planting = [4,5]; harvest = [9,10]
    if month in planting: return {"action":"buy-uncertainty","grain":grain,"confidence":0.55}
    if month in harvest: return {"action":"sell-harvest-pressure","grain":grain,"confidence":0.58}
    return None

def strat_weather_premium(crop, weather_event, days_to_impact, severity):
    """Weather events: drought, frost, flood → crop damage → price spike."""
    if severity > 0.7 and days_to_impact < 14:
        return {"strategy":"weather-premium","crop":crop,"event":weather_event,
                "action":"long","confidence":0.60+severity*0.1}

def strat_wasde_report(crop, actual_yield, expected_yield, actual_ending_stocks, expected_stocks):
    """USDA WASDE monthly report: yield surprises move grains 3-5%."""
    yield_surprise = (actual_yield - expected_yield) / expected_yield
    stock_surprise = (actual_ending_stocks - expected_stocks) / expected_stocks
    direction = "short" if yield_surprise > 0 else "long"
    return {"strategy":"wasde-report","crop":crop,"direction":direction,
            "yield_surprise_pct":round(yield_surprise*100,1)}

def strat_grain_spread(wheat_price, corn_price, historical_ratio):
    """Wheat/corn spread: substitution effect. Wide spread favors corn feeding."""
    ratio = wheat_price / corn_price
    if ratio > historical_ratio * 1.2:
        return {"strategy":"wheat-corn-spread","action":"short-wheat-long-corn"}
    return None

def strat_coffee_frost(days_to_brazil_winter, current_premium):
    """Brazil frost risk in Jun-Aug. Buy coffee ahead of winter."""
    if 5 <= days_to_brazil_winter <= 30:
        return {"strategy":"coffee-frost-risk","action":"buy-call-options","confidence":0.55}

def strat_sugar_ethanol(brazil_ethanol_price, sugar_price, crush_spread):
    """Brazil sugar/ethanol flex: mills switch based on relative price."""
    if brazil_ethanol_price > sugar_price * 1.1:
        return {"strategy":"sugar-ethanol","action":"long-sugar","rationale":"Mills favor ethanol"}
    return None

def strat_cotton_demand(global_gdp_growth, inventory_to_use_ratio):
    """Cotton: clothing demand = GDP-driven. Low inventory = bullish."""
    if global_gdp_growth > 0.03 and inventory_to_use_ratio < 0.5:
        return {"strategy":"cotton-demand","action":"long","gdp_growth":global_gdp_growth}

def strat_cattle_cycle(herd_size_change, feed_cost_change, months_to_supply_response):
    """Cattle cycle: 8-12 year cycle. Herd expansion = lower prices in 2-3 years."""
    if herd_size_change < -0.02:
        return {"strategy":"cattle-cycle","action":"long","phase":"contraction","confidence":0.60}

def strat_hog_seasonality(month):
    """Hog seasonality: summer grilling = demand. Dec holidays = peak."""
    if month in [5,6,7]: return {"action":"long","rationale":"grilling-season"}
    return None

# ============================================================
# CATEGORY E: SPREADS & CARRY — 8
# ============================================================

def strat_commodity_carry(front_price, second_price, storage_cost, interest_rate):
    """Commodity carry: contango (front<back) = negative carry, backwardation = positive."""
    roll_yield = (front_price - second_price) / front_price
    annualized = roll_yield * (365/30)  # Monthly contract
    return {"strategy":"commodity-carry","roll_yield_pct":round(roll_yield*100,2),
            "annualized_pct":round(annualized*100,1),
            "action":"long" if roll_yield > 0.02 else "short" if roll_yield < -0.02 else "neutral"}

def strat_calendar_spread_commodity(near_contract, far_contract, spread, season):
    """Calendar spread: same commodity, different months. Seasonality-based."""
    normal_spread = far_contract - near_contract
    return {"strategy":"calendar-spread","spread":round(normal_spread,2),
            "season":season,"action":"buy-spread" if normal_spread < 0 else "sell-spread"}

def strat_inter_commodity_spread(commodity_a, commodity_b, ratio, z_score):
    """Related commodities: WTI/Brent, gold/platinum, corn/wheat."""
    if abs(z_score) > 2:
        return {"strategy":"inter-commodity","pair":f"{commodity_a}/{commodity_b}",
                "action":"long-underperformer","z_score":round(z_score,2)}

def strat_location_spread(wti_price, brent_price, transport_cost):
    """WTI-Brent spread: transport bottleneck = wide spread."""
    spread = brent_price - wti_price
    return {"strategy":"wti-brent","spread":round(spread,2),
            "action":"long-spread" if spread < transport_cost else "short-spread"}

def strat_processing_spread(spread_type, input_price, output_basket):
    """Generic processing spread for any commodity."""
    margin = output_basket - input_price
    return {"strategy":spread_type,"margin":round(margin,2)}

def strat_commodity_curve_slope(front, month6, month12):
    """Term structure slope: steep contango = oversupply, backwardation = shortage."""
    slope_6m = (month6 - front) / front
    slope_12m = (month12 - front) / front
    regime = "backwardation" if slope_6m < -0.02 else "contango" if slope_6m > 0.03 else "flat"
    return {"strategy":"curve-slope","regime":regime,"slope_6m":round(slope_6m*100,1)}

def strat_roll_yield_harvest(front, next_month, days_to_roll):
    """Harvest roll yield by rolling position before expiry."""
    roll_yield = (next_month - front) / front
    if abs(roll_yield) > 0.005:
        return {"strategy":"roll-harvest","roll_yield_pct":round(roll_yield*100,2),
                "action":"roll-early" if roll_yield < 0 else "hold-to-expiry"}

def strat_commodity_index_rebalance(index_weights, rebalance_date, days_away):
    """Commodity index rebalancing (S&P GSCI, Bloomberg Commodity). Front-run flows."""
    if days_away <= 5:
        return {"strategy":"index-rebalance","action":"front-run-inflows","confidence":0.55}

# ============================================================
# CATEGORY F: COT & POSITIONING — 6
# ============================================================

def strat_cot_extreme(net_long_pct, historical_percentile):
    """COT extreme positioning = contrarian. Specs too long = sell, too short = buy."""
    if historical_percentile > 90:
        return {"strategy":"cot-extreme","action":"fade-specs-short","percentile":historical_percentile,"confidence":0.62}
    if historical_percentile < 10:
        return {"strategy":"cot-extreme","action":"fade-specs-long","percentile":historical_percentile,"confidence":0.62}

def strat_cot_commercials(commercial_net, speculator_net, open_interest):
    """Commercials (hedgers) are usually right at extremes. Follow commercials."""
    commercial_pct = commercial_net / open_interest
    if commercial_pct > 0.15:
        return {"strategy":"follow-commercials","action":"long","confidence":0.60}
    if commercial_pct < -0.15:
        return {"strategy":"follow-commercials","action":"short","confidence":0.60}

def strat_cot_momentum(weekly_change_net_long, price_change):
    """COT momentum: accelerating long/short = follow trend. Decelerating = fade."""
    if weekly_change_net_long > 0.1 and price_change > 0:
        return {"strategy":"cot-momentum","action":"follow","confidence":0.55}

def strat_open_interest_analysis(oi_change_pct, price_change_pct):
    """OI + price: OI up + price up = new longs (bullish). OI up + price down = new shorts (bearish)."""
    if oi_change_pct > 0.05:
        direction = "long" if price_change_pct > 0 else "short"
        return {"strategy":"open-interest","action":direction,"oi_change":round(oi_change_pct*100,1)}

def strat_speculator_sentiment(net_long_all_commodities, vix):
    """Aggregate speculator positioning across all commodities."""
    if net_long_all_commodities > 0.8 and vix < 15:
        return {"strategy":"spec-sentiment","action":"reduce-risk","signal":"euphoria","confidence":0.55}

def strat_managed_money_flow(managed_money_net_change, commodity, total_oi):
    """Managed money (CTAs, hedge funds) flow following."""
    flow_pct = managed_money_net_change / total_oi
    if abs(flow_pct) > 0.05:
        return {"strategy":"managed-money","commodity":commodity,
                "action":"follow" if flow_pct > 0 else "fade","flow_pct":round(flow_pct*100,1)}

# ============================================================
# CATEGORY G: SUPER-CYCLE & MACRO — 4 last
# ============================================================

def strat_super_cycle(commodity, years_into_cycle, capex_trend, demand_growth):
    """Commodity super-cycle: 15-25 year cycles driven by industrialization."""
    if years_into_cycle < 5 and capex_trend < 0 and demand_growth > 0.03:
        return {"strategy":"super-cycle","commodity":commodity,"phase":"early-cycle",
                "action":"accumulate","confidence":0.55,"horizon":"years"}

def strat_inflation_regime_rotation(cpi_level, ppi_level, commodity_index_level):
    """Rotate into commodities when inflation accelerates."""
    if cpi_level > 3 and ppi_level > 4:
        return {"strategy":"inflation-rotation","action":"overweight-commodities",
                "favored":["energy","metals","agriculture"]}

def strat_dollar_commodity_link(dxy_change, commodity_basket_change):
    """Strong dollar = commodity headwind. Weak dollar = commodity tailwind."""
    if dxy_change > 2 and commodity_basket_change > -2:
        return {"strategy":"dollar-commodity","action":"fade-commodity-strength"}

def strat_energy_transition(fossil_fuel_capex, renewable_capex, transition_phase):
    """Energy transition: underinvestment in fossil + growing demand = supply crunch.""" 
    if fossil_fuel_capex < renewable_capex * 0.5:
        return {"strategy":"energy-transition","action":"long-energy","phase":"underinvestment",
                "rationale":"Fossil fuel underinvestment = future supply crunch","confidence":0.55}

# ============================================================
# MASTER ARSENAL
# ============================================================

ALL_COMMODITY_STRATEGIES = {
    "energy": ["eia-inventory","ng-storage","crack-spread","cl-seasonality","ng-seasonality",
        "gasoline-driving","heating-oil-winter","opec-meeting","geopolitical-supply","energy-rotation"],
    "precious-metals": ["gold-silver-ratio","gold-real-yields","gold-inflation","gold-geopolitical",
        "pt-pd-ratio","central-bank-gold","silver-industrial","gold-seasonality"],
    "base-metals": ["copper-gold-ratio","copper-china","copper-electrification","aluminum-energy",
        "metal-supply-chain","metal-rotation"],
    "agriculture": ["soybean-crush","grain-seasonality","weather-premium","wasde-report",
        "grain-spread","coffee-frost","sugar-ethanol","cotton-demand","cattle-cycle","hog-seasonality"],
    "spreads-carry": ["commodity-carry","calendar-spread","inter-commodity","location-spread",
        "processing-spread","curve-slope","roll-harvest","index-rebalance"],
    "cot-positioning": ["cot-extreme","follow-commercials","cot-momentum","open-interest",
        "spec-sentiment","managed-money"],
    "super-cycle-macro": ["super-cycle","inflation-rotation","dollar-commodity","energy-transition"],
}

def execute_commodities_arsenal():
    print("Commodities Trading — Complete Arsenal (50 strategies)")
    print("=" * 65)
    state = {"generated_at":datetime.now(timezone.utc).isoformat(),"strategies":ALL_COMMODITY_STRATEGIES,
             "total_strategies":sum(len(v) for v in ALL_COMMODITY_STRATEGIES.values())}
    total = state["total_strategies"]
    for cat, strats in ALL_COMMODITY_STRATEGIES.items():
        print(f"  {cat}: {len(strats)}")
    print(f"\nTotal: {total} strategies across 7 categories")
    STATE_DIR.mkdir(parents=True,exist_ok=True)
    with open(CMD_ARsenal,"w") as f:
        json.dump(state,f,indent=2,default=str)
    print(f"Arsenal: {CMD_ARsenal}")

if __name__=="__main__":
    execute_commodities_arsenal()
