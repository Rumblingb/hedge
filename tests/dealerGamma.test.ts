import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchDealerGamma } from "../src/research/dealerGamma.js";

const realFetch = globalThis.fetch;

describe("dealer gamma", () => {
  afterEach(() => {
    globalThis.fetch = realFetch;
    vi.restoreAllMocks();
  });

  it("falls back to Yahoo approximation when configured Polygon access is forbidden", async () => {
    const fakeFetch = vi.fn(async (url: string | URL) => {
      const text = String(url);
      if (text.includes("api.polygon.io")) {
        return new Response("forbidden", { status: 403, statusText: "Forbidden" });
      }
      if (text.includes("query2.finance.yahoo.com")) {
        return new Response(JSON.stringify({
          optionChain: {
            result: [
              {
                quote: { regularMarketPrice: 500 },
                options: [
                  {
                    calls: [
                      {
                        contractSymbol: "SPY300119C00500000",
                        strike: 500,
                        expiration: Date.parse("2030-01-19T00:00:00Z") / 1000,
                        impliedVolatility: 0.2,
                        openInterest: 1000
                      }
                    ],
                    puts: [
                      {
                        contractSymbol: "SPY300119P00500000",
                        strike: 500,
                        expiration: Date.parse("2030-01-19T00:00:00Z") / 1000,
                        impliedVolatility: 0.25,
                        openInterest: 800
                      }
                    ]
                  }
                ]
              }
            ]
          }
        }), {
          status: 200,
          headers: { "content-type": "application/json" }
        });
      }
      throw new Error(`unexpected url ${text}`);
    }) as unknown as typeof fetch;
    globalThis.fetch = fakeFetch;

    const report = await fetchDealerGamma({
      underlying: "SPY",
      polygonApiKey: "no-options-access"
    });

    expect(report.source).toBe("yahoo");
    expect(report.contractsWithGamma).toBe(2);
    expect(report.contractsTotal).toBe(2);
    expect(report.underlyingPrice).toBe(500);
  });
});
