import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchPolymarketLiveSnapshot } from "../src/prediction/adapters/polymarket.js";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("prediction collector", () => {
  it("normalizes polymarket gamma events into prediction snapshots", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ([
        {
          id: "event-1",
          title: "Will X happen?",
          endDate: "2026-11-03",
          markets: [
            {
              id: "market-1",
              question: "Will X happen?",
              description: "Resolves yes if X happens",
              outcomes: JSON.stringify(["Yes", "No"]),
              outcomePrices: JSON.stringify([0.42, 0.58]),
              liquidity: "1200"
            }
          ]
        }
      ])
    })));

    const rows = await fetchPolymarketLiveSnapshot(5);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({
      venue: "polymarket",
      externalId: "market-1",
      eventTitle: "Will X happen?",
      outcomeLabel: "Yes",
      price: 0.42,
      displayedSize: 1200
    });
  });
});
