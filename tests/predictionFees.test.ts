import { describe, expect, it } from "vitest";
import {
  DEFAULT_PREDICTION_FEES,
  estimatePredictionFeeDragPct,
  estimatePredictionVenueFeePct
} from "../src/prediction/fees.js";
import type { PredictionMarketSnapshot } from "../src/prediction/types.js";

function market(overrides: Partial<PredictionMarketSnapshot>): PredictionMarketSnapshot {
  return {
    venue: "polymarket",
    externalId: "m1",
    eventTitle: "Bitcoin above 100k?",
    marketQuestion: "Will Bitcoin be above 100k?",
    outcomeLabel: "Yes",
    side: "yes",
    price: 0.5,
    displayedSize: 10_000,
    ...overrides
  };
}

describe("prediction fee model", () => {
  it("uses official-style price/category fee curves instead of a flat venue drag", () => {
    const polymarketCrypto = market({ venue: "polymarket", price: 0.5 });
    const kalshiMostMarkets = market({
      venue: "kalshi",
      externalId: "k1",
      eventTitle: "Bitcoin above 100k?",
      marketQuestion: "Will Bitcoin be above 100k?",
      price: 0.5
    });

    expect(estimatePredictionVenueFeePct(polymarketCrypto, DEFAULT_PREDICTION_FEES)).toBeCloseTo(1.8, 2);
    expect(estimatePredictionVenueFeePct(kalshiMostMarkets, DEFAULT_PREDICTION_FEES)).toBeCloseTo(1.75, 2);
    expect(estimatePredictionFeeDragPct({
      left: polymarketCrypto,
      right: kalshiMostMarkets,
      config: DEFAULT_PREDICTION_FEES
    })).toBeCloseTo(4.05, 2);
  });

  it("treats geopolitics Polymarket candidates as fee-free before slippage", () => {
    const polymarketGeo = market({
      venue: "polymarket",
      eventTitle: "US Iran peace deal",
      marketQuestion: "Will the US and Iran reach a peace deal?",
      settlementText: "Geopolitics market",
      price: 0.5
    });
    const manifoldMirror = market({
      venue: "manifold",
      externalId: "manifold-1",
      eventTitle: "US Iran peace deal",
      marketQuestion: "Will the US and Iran reach a peace deal?",
      price: 0.52
    });

    expect(estimatePredictionVenueFeePct(polymarketGeo, DEFAULT_PREDICTION_FEES)).toBe(0);
    expect(estimatePredictionFeeDragPct({
      left: polymarketGeo,
      right: manifoldMirror,
      config: DEFAULT_PREDICTION_FEES
    })).toBe(DEFAULT_PREDICTION_FEES.slippagePct);
  });
});
