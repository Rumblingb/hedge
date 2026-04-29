import { afterEach, describe, expect, it, vi } from "vitest";
import { buildManifoldSearchTerms, fetchManifoldLiveSnapshot } from "../src/prediction/adapters/manifold.js";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("manifold collector", () => {
  it("builds de-duplicated overlap search terms from the highest-signal seed markets", () => {
    const terms = buildManifoldSearchTerms([
      {
        venue: "polymarket",
        externalId: "sports-noise",
        eventTitle: "World Cup",
        marketQuestion: "Will Panama win the 2026 FIFA World Cup?",
        outcomeLabel: "Yes",
        side: "yes",
        price: 0.02,
        displayedSize: 900000
      },
      {
        venue: "polymarket",
        externalId: "poly-1",
        eventTitle: "Iran peace deal",
        marketQuestion: "US x Iran permanent peace deal by May 31? [Polymarket]",
        outcomeLabel: "Yes",
        side: "yes",
        price: 0.41,
        displayedSize: 5000
      },
      {
        venue: "kalshi",
        externalId: "kalshi-1",
        eventTitle: "OpenAI v Anthropic IPO",
        marketQuestion: "Will OpenAI or Anthropic IPO first?",
        outcomeLabel: "OpenAI",
        side: "yes",
        price: 0.52,
        displayedSize: 2000
      },
      {
        venue: "polymarket",
        externalId: "poly-dup",
        eventTitle: "Iran peace deal",
        marketQuestion: "US x Iran permanent peace deal by May 31?",
        outcomeLabel: "Yes",
        side: "yes",
        price: 0.4,
        displayedSize: 1500
      },
      {
        venue: "manifold",
        externalId: "manifold-1",
        eventTitle: "Should be ignored",
        marketQuestion: "US x Iran permanent peace deal by May 31? [Polymarket]",
        outcomeLabel: "Yes",
        side: "yes",
        price: 0.53,
        displayedSize: 800
      }
    ], 5);

    expect(terms).toEqual([
      "Will OpenAI or Anthropic IPO first",
      "US x Iran permanent peace deal by May 31"
    ]);
  });

  it("normalizes manifold markets into prediction snapshots", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ([
        {
          id: "ignore-multi",
          question: "Which asset wins?",
          outcomeType: "MULTIPLE_CHOICE",
          probability: null,
          closeTime: 1780000000000,
          volume: 500,
          isResolved: false
        },
        {
          id: "market-1",
          question: "Will ETH be above $4k by year end?",
          outcomeType: "BINARY",
          probability: 0.44,
          closeTime: 1780000000000,
          volume: 1250,
          isResolved: false
        }
      ])
    })));

    const rows = await fetchManifoldLiveSnapshot(5);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      venue: "manifold",
      externalId: "market-1",
      outcomeLabel: "Yes",
      price: 0.44,
      displayedSize: 1250
    });
  });

  it("keeps only seed-aligned manifold markets when seed markets are supplied", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL) => {
      const url = String(input);
      if (url.includes("/v0/search-markets")) {
        return {
          ok: true,
          json: async () => ([
            {
              id: "search-hit",
              question: "US x Iran permanent peace deal by May 31? [Polymarket]",
              outcomeType: "BINARY",
              probability: 0.53,
              closeTime: 1780000000000,
              volume: 4000,
              isResolved: false
            }
          ])
        };
      }
      return {
        ok: true,
        json: async () => ([
          {
            id: "base-market",
            question: "Generic unrelated market",
            outcomeType: "BINARY",
            probability: 0.44,
            closeTime: 1780000000000,
            volume: 1250,
            isResolved: false
          }
        ])
      };
    }));

    const rows = await fetchManifoldLiveSnapshot(2, {
      seedMarkets: [
        {
          venue: "polymarket",
          externalId: "poly-1",
          eventTitle: "Iran peace deal",
          marketQuestion: "US x Iran permanent peace deal by May 31? [Polymarket]",
          outcomeLabel: "Yes",
          side: "yes",
          price: 0.41,
          displayedSize: 5000
        }
      ]
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      externalId: "search-hit",
      marketQuestion: "US x Iran permanent peace deal by May 31? [Polymarket]"
    });
  });

  it("filters search results that share topic words but not the actual contract family", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL) => {
      const url = String(input);
      if (url.includes("/v0/search-markets")) {
        return {
          ok: true,
          json: async () => ([
            {
              id: "bad-search-hit",
              question: "Will Bitcoin transaction count increase in 24h?",
              outcomeType: "BINARY",
              probability: 0.6,
              closeTime: 1777068071437,
              volume: 4000,
              isResolved: false
            },
            {
              id: "good-search-hit",
              question: "Will Bitcoin hit $120k in April? [Polymarket]",
              outcomeType: "BINARY",
              probability: 0.18,
              closeTime: 1777656000000,
              volume: 800,
              isResolved: false
            }
          ])
        };
      }
      return {
        ok: true,
        json: async () => ([
          {
            id: "base-market",
            question: "Generic unrelated market",
            outcomeType: "BINARY",
            probability: 0.44,
            closeTime: 1780000000000,
            volume: 1250,
            isResolved: false
          }
        ])
      };
    }));

    const rows = await fetchManifoldLiveSnapshot(3, {
      seedMarkets: [
        {
          venue: "polymarket",
          externalId: "btc-price-hit",
          eventTitle: "What price will Bitcoin hit in April?",
          marketQuestion: "Will Bitcoin hit $120k in April?",
          outcomeLabel: "Yes",
          side: "yes",
          expiry: "2026-05-01T04:00:00Z",
          settlementText: "Resolves yes if Bitcoin hits 120k at any point in April 2026.",
          price: 0.0005,
          displayedSize: 5000
        }
      ]
    });

    expect(rows.map((row) => row.externalId)).toContain("good-search-hit");
    expect(rows.map((row) => row.externalId)).not.toContain("bad-search-hit");
  });
});
