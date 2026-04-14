import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchManifoldLiveSnapshot } from "../src/prediction/adapters/manifold.js";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("manifold collector", () => {
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
});
