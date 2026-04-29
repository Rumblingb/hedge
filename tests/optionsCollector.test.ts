import { describe, expect, it } from "vitest";
import { buildOneDayToExpiryOptionReport, fetchAlpacaOptionSnapshots, parsePolygonOptionSnapshots } from "../src/research/options.js";

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

  it("builds a 1DTE-style summary from normalized snapshots", () => {
    const report = buildOneDayToExpiryOptionReport({
      underlying: "SPY",
      source: "alpaca",
      underlyingPrice: 600.4,
      selectedExpirationDate: "2026-06-19",
      snapshots: [
        {
          contract: "C600",
          underlying: "SPY",
          strike: 600,
          expirationDate: "2026-06-19",
          contractType: "call",
          impliedVolatility: 0.22,
          openInterest: 1000,
          ask: 4.2,
          source: "alpaca"
        },
        {
          contract: "P600",
          underlying: "SPY",
          strike: 600,
          expirationDate: "2026-06-19",
          contractType: "put",
          impliedVolatility: 0.24,
          openInterest: 900,
          ask: 3.8,
          source: "alpaca"
        },
        {
          contract: "C610-next",
          underlying: "SPY",
          strike: 610,
          expirationDate: "2026-06-20",
          contractType: "call",
          impliedVolatility: 0.4,
          openInterest: 50,
          ask: 1.1,
          source: "alpaca"
        }
      ],
      now: new Date("2026-06-18T12:00:00.000Z")
    });

    expect(report.contractCount).toBe(2);
    expect(report.atmStrike).toBe(600);
    expect(report.atmStraddleAsk).toBe(8);
    expect(report.callCount).toBe(1);
    expect(report.putCount).toBe(1);
  });

  it("normalizes Alpaca option snapshots from OCC-style contract symbols", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => new Response(JSON.stringify({
      snapshots: {
        SPY260619C00600000: {
          greeks: { delta: 0.32, gamma: 0.01, iv: 0.24 },
          latestQuote: { bp: 4.1, ap: 4.3 },
          latestTrade: { p: 4.2 },
          openInterest: 1200
        }
      }
    }), { status: 200, headers: { "content-type": "application/json" } });

    try {
      const result = await fetchAlpacaOptionSnapshots({
        underlying: "SPY",
        apiKey: "key",
        secretKey: "secret"
      });
      expect(result.snapshots).toHaveLength(1);
      expect(result.snapshots[0]).toMatchObject({
        contract: "SPY260619C00600000",
        underlying: "SPY",
        strike: 600,
        expirationDate: "2026-06-19",
        contractType: "call",
        impliedVolatility: 0.24,
        openInterest: 1200,
        source: "alpaca"
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
