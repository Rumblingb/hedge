import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchKalshiLiveSnapshot, fetchKalshiLiveSnapshotWithDiagnostics } from "../src/prediction/adapters/kalshi.js";

process.env.BILL_PREDICTION_KALSHI_PACING_MS = "0";
process.env.BILL_PREDICTION_KALSHI_SERIES_ALLOWLIST = "KXWORLDCUP";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("kalshi collector", () => {
  it("normalizes kalshi markets into prediction snapshots", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const href = typeof input === "string" ? input : input.toString();
      if (href.includes("/series")) {
        return {
          ok: true,
          json: async () => ({
            series: [
              { ticker: "KXWORLDCUP", title: "World Cup", category: "Politics" }
            ]
          })
        };
      }

      return {
        ok: true,
        json: async () => ({
          markets: [
            {
              ticker: "KXCOMBO-IGNORE",
              title: "yes Charlotte,yes Diana Shnaider",
              yes_sub_title: "yes Charlotte,yes Diana Shnaider",
              close_time: "2026-04-28T23:30:00Z",
              last_price_dollars: "0",
              volume_24h_fp: "0",
              rules_primary: "Combo market."
            },
            {
              ticker: "KXWORLDCUP-BRAZIL",
              title: "Will Brazil win the 2026 FIFA World Cup?",
              yes_sub_title: "Yes",
              close_time: "2026-07-20T00:00:00Z",
              last_price_dollars: "0.22",
              volume_24h_fp: "50",
              rules_primary: "Resolves yes if Brazil wins the tournament."
            },
            {
              ticker: "KXWORLDCUP-SPAIN",
              title: "Will Spain win the 2026 FIFA World Cup?",
              yes_sub_title: "Yes",
              close_time: "2026-07-20T00:00:00Z",
              last_price_dollars: "0.36",
              volume_24h_fp: "500",
              rules_primary: "Resolves yes if Spain wins the tournament."
            }
          ]
        })
      };
    }));

    const rows = await fetchKalshiLiveSnapshot(1);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      venue: "kalshi",
      externalId: "KXWORLDCUP-SPAIN",
      eventTitle: "Will Spain win the 2026 FIFA World Cup?",
      outcomeLabel: "Yes",
      price: 0.36,
      displayedSize: 500
    });
  });

  it("surfaces diagnostics when the series endpoint 429s so silent-zero failure is visible", async () => {
    const warn = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const href = typeof input === "string" ? input : input.toString();
        if (href.includes("/series")) {
          return { ok: false, status: 429, statusText: "Too Many Requests", json: async () => ({}) };
        }
        return { ok: false, status: 429, statusText: "Too Many Requests", json: async () => ({}) };
      })
    );

    const { snapshots, diagnostics } = await fetchKalshiLiveSnapshotWithDiagnostics(5);
    expect(snapshots).toHaveLength(0);
    expect(diagnostics.seriesConsidered).toBeGreaterThan(0);
    expect(diagnostics.seriesFetchErrors).toBe(diagnostics.seriesConsidered);
    expect(diagnostics.marketsAccepted).toBe(0);
    expect(warn).toHaveBeenCalled();
    const combined = warn.mock.calls.map((call) => String(call[0])).join(" ");
    expect(combined).toMatch(/kalshi-adapter/);
  });
});
