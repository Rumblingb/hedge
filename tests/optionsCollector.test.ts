import { describe, expect, it } from "vitest";
import { parsePolygonOptionSnapshots } from "../src/research/options.js";

describe("polygon options parser", () => {
  it("normalizes polygon option snapshots", () => {
    const rows = parsePolygonOptionSnapshots({
      underlying: "SPY",
      payload: {
        results: [
          {
            details: {
              ticker: "O:SPY260619C00600000",
              contract_type: "call",
              expiration_date: "2026-06-19",
              strike_price: 600
            },
            implied_volatility: 0.24,
            open_interest: 1200,
            greeks: { delta: 0.32, gamma: 0.01 },
            last_quote: { bid: 4.1, ask: 4.3 }
          }
        ]
      }
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      underlying: "SPY",
      contract: "O:SPY260619C00600000",
      contractType: "call",
      strike: 600,
      impliedVolatility: 0.24,
      openInterest: 1200
    });
  });
});
