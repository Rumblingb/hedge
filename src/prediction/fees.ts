import type { PredictionFeeConfig, PredictionMarketSnapshot } from "./types.js";

export const DEFAULT_PREDICTION_FEES: PredictionFeeConfig = {
  venueAFeePct: 0.5,
  venueBFeePct: 0.5,
  slippagePct: 0.5,
  minDisplayedSize: 100,
  watchThresholdPct: 0.25,
  useVenueFeeModel: true,
  polymarketDefaultTakerFeeRate: 0.05,
  kalshiTakerFeeMultiplier: 0.07,
  manifoldFeePct: 0
};

function readNumber(env: NodeJS.ProcessEnv, key: string, fallback: number): number {
  const raw = env[key];
  if (!raw) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function buildPredictionFeeConfigFromEnv(env: NodeJS.ProcessEnv = process.env): PredictionFeeConfig {
  return {
    venueAFeePct: readNumber(env, "BILL_PREDICTION_FEE_VENUE_A_PCT", DEFAULT_PREDICTION_FEES.venueAFeePct),
    venueBFeePct: readNumber(env, "BILL_PREDICTION_FEE_VENUE_B_PCT", DEFAULT_PREDICTION_FEES.venueBFeePct),
    slippagePct: readNumber(env, "BILL_PREDICTION_SLIPPAGE_PCT", DEFAULT_PREDICTION_FEES.slippagePct),
    minDisplayedSize: readNumber(env, "BILL_PREDICTION_MIN_DISPLAYED_SIZE", DEFAULT_PREDICTION_FEES.minDisplayedSize),
    watchThresholdPct: readNumber(env, "BILL_PREDICTION_WATCH_EDGE_PCT", DEFAULT_PREDICTION_FEES.watchThresholdPct),
    useVenueFeeModel: env.BILL_PREDICTION_USE_VENUE_FEE_MODEL !== "false",
    polymarketDefaultTakerFeeRate: readNumber(
      env,
      "BILL_PREDICTION_POLYMARKET_DEFAULT_TAKER_FEE_RATE",
      DEFAULT_PREDICTION_FEES.polymarketDefaultTakerFeeRate ?? 0.05
    ),
    kalshiTakerFeeMultiplier: readNumber(
      env,
      "BILL_PREDICTION_KALSHI_TAKER_FEE_MULTIPLIER",
      DEFAULT_PREDICTION_FEES.kalshiTakerFeeMultiplier ?? 0.07
    ),
    manifoldFeePct: readNumber(env, "BILL_PREDICTION_MANIFOLD_FEE_PCT", DEFAULT_PREDICTION_FEES.manifoldFeePct ?? 0)
  };
}

function clampPrice(price: number): number {
  return Math.min(Math.max(price, 0.01), 0.99);
}

function feeFromRatePct(price: number, rate: number): number {
  const p = clampPrice(price);
  return rate * p * (1 - p) * 100;
}

function marketText(market: PredictionMarketSnapshot): string {
  return `${market.eventTitle} ${market.marketQuestion} ${market.settlementText ?? ""}`.toLowerCase();
}

function polymarketFeeRate(market: PredictionMarketSnapshot, config: PredictionFeeConfig): number {
  const text = marketText(market);
  if (/\b(geopolitics?|world events?|war|ceasefire|iran|ukraine|russia|hormuz|peace deal|strike)\b/.test(text)) return 0;
  if (/\b(bitcoin|btc|ethereum|eth|crypto|solana|doge)\b/.test(text)) return 0.072;
  if (/\b(nba|nfl|mlb|nhl|fifa|world cup|sports?|match|game)\b/.test(text)) return 0.03;
  if (/\b(fed|rate|cpi|inflation|gdp|unemployment|recession|econom(y|ics)|weather|culture)\b/.test(text)) return 0.05;
  if (/\b(stock|stocks|spx|s&p|nasdaq|dow|oil|wti|gold|finance|politics|election|mention|openai|anthropic|tech)\b/.test(text)) return 0.04;
  return config.polymarketDefaultTakerFeeRate ?? 0.05;
}

export function estimatePredictionVenueFeePct(
  market: PredictionMarketSnapshot,
  config: PredictionFeeConfig
): number {
  switch (market.venue.toLowerCase()) {
    case "polymarket":
      return feeFromRatePct(market.price, polymarketFeeRate(market, config));
    case "kalshi":
      return feeFromRatePct(market.price, config.kalshiTakerFeeMultiplier ?? 0.07);
    case "manifold":
      return config.manifoldFeePct ?? 0;
    default:
      return 0;
  }
}

export function estimatePredictionFeeDragPct(args: {
  left: PredictionMarketSnapshot;
  right: PredictionMarketSnapshot;
  config: PredictionFeeConfig;
}): number {
  const { left, right, config } = args;
  const venueFeeDrag = config.useVenueFeeModel === false
    ? config.venueAFeePct + config.venueBFeePct
    : estimatePredictionVenueFeePct(left, config) + estimatePredictionVenueFeePct(right, config);
  return Number((venueFeeDrag + config.slippagePct).toFixed(2));
}
