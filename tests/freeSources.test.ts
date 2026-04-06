import { describe, expect, it } from "vitest";
import { parseStooqDailyCsv, parseYahooChartPayload, toCsvContent } from "../src/data/freeSources.js";

describe("freeSources parsers", () => {
  it("parses Yahoo chart payload into normalized bars", () => {
    const payload = {
      chart: {
        result: [
          {
            timestamp: [1712188800, 1712188860],
            indicators: {
              quote: [
                {
                  open: [100, 101],
                  high: [101, 102],
                  low: [99.5, 100.5],
                  close: [100.8, 101.7],
                  volume: [1200, 1300]
                }
              ]
            }
          }
        ],
        error: null
      }
    };

    const bars = parseYahooChartPayload({ payload, symbol: "NQ" });
    expect(bars).toHaveLength(2);
    expect(bars[0]?.symbol).toBe("NQ");
    expect(bars[0]?.open).toBe(100);
    expect(bars[1]?.close).toBe(101.7);
  });

  it("parses Stooq daily CSV into bars", () => {
    const csv = [
      "Date,Open,High,Low,Close,Volume",
      "2026-04-01,5034.5,5060.25,5012.75,5055.25,120304",
      "2026-04-02,5055.25,5070.00,5042.00,5062.75,110000"
    ].join("\n");

    const bars = parseStooqDailyCsv({ csv, symbol: "ES" });
    expect(bars).toHaveLength(2);
    expect(bars[0]?.symbol).toBe("ES");
    expect(bars[0]?.open).toBe(5034.5);
    expect(bars[1]?.volume).toBe(110000);
  });

  it("formats bars into headered CSV", () => {
    const csv = toCsvContent([
      {
        ts: "2026-04-01T13:31:00.000Z",
        symbol: "NQ",
        open: 18200,
        high: 18205,
        low: 18198,
        close: 18203,
        volume: 900
      },
      {
        ts: "2026-04-01T13:30:00.000Z",
        symbol: "NQ",
        open: 18195,
        high: 18201,
        low: 18192,
        close: 18199,
        volume: 850
      }
    ]);

    expect(csv.startsWith("ts,symbol,open,high,low,close,volume\n")).toBe(true);
    expect(csv).toContain("2026-04-01T13:30:00.000Z,NQ,18195,18201,18192,18199,850");
  });
});
