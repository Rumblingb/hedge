import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchFreeBars, parseDatabentoOhlcvJsonLines, parseStooqDailyCsv, parseYahooChartPayload, toCsvContent } from "../src/data/freeSources.js";

const realFetch = globalThis.fetch;
const originalDatabentoKey = process.env.DATABENTO_API_KEY;

afterEach(() => {
  globalThis.fetch = realFetch;
  vi.restoreAllMocks();
  if (originalDatabentoKey === undefined) {
    delete process.env.DATABENTO_API_KEY;
  } else {
    process.env.DATABENTO_API_KEY = originalDatabentoKey;
  }
});

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

  it("parses Databento OHLCV json lines into normalized bars", () => {
    const text = [
      "{\"hd\":{\"ts_event\":\"2026-04-16T00:00:00.000000000Z\"},\"open\":\"7069.000000000\",\"high\":\"7069.500000000\",\"low\":\"7068.000000000\",\"close\":\"7068.500000000\",\"volume\":\"308\",\"symbol\":\"ES.v.0\"}",
      "{\"hd\":{\"ts_event\":\"2026-04-16T00:01:00.000000000Z\"},\"open\":\"7068.500000000\",\"high\":\"7070.000000000\",\"low\":\"7068.500000000\",\"close\":\"7069.750000000\",\"volume\":\"115\",\"symbol\":\"ES.v.0\"}"
    ].join("\n");

    const bars = parseDatabentoOhlcvJsonLines({ text, fallbackSymbol: "ES" });
    expect(bars).toHaveLength(2);
    expect(bars[0]).toMatchObject({
      ts: "2026-04-16T00:00:00.000Z",
      symbol: "ES",
      open: 7069,
      close: 7068.5,
      volume: 308
    });
    expect(bars[1]?.high).toBe(7070);
  });

  it("retries Databento at the provider-reported available_end boundary", async () => {
    process.env.DATABENTO_API_KEY = "test-key";
    const bodies: string[] = [];
    globalThis.fetch = vi.fn(async (_url: string | URL, init?: RequestInit) => {
      const body = String(init?.body ?? "");
      bodies.push(body);
      if (bodies.length === 1) {
        return new Response(JSON.stringify({
          detail: {
            message: "Part or all of your request requires a subscription and/or license to access.",
            payload: {
              available_end: "2026-04-17T16:56:43.968923000Z"
            }
          }
        }), {
          status: 422,
          headers: { "Content-Type": "application/json" }
        });
      }

      return new Response(
        "{\"hd\":{\"ts_event\":\"2026-04-16T00:00:00.000000000Z\"},\"open\":\"7069.000000000\",\"high\":\"7069.500000000\",\"low\":\"7068.000000000\",\"close\":\"7068.500000000\",\"volume\":\"308\",\"symbol\":\"NQ.v.0\"}\n",
        { status: 200 }
      );
    }) as unknown as typeof fetch;

    const result = await fetchFreeBars({
      symbol: "NQ",
      interval: "1m",
      range: "10d",
      provider: "databento",
      timeoutMs: 1000
    });

    expect(result.providerUsed).toBe("databento");
    expect(result.bars).toHaveLength(1);
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toContain("end=2026-04-17T16%3A56%3A43.968923000Z");
    expect(result.warnings.some((warning) => warning.includes("2026-04-17T16:56:43.968923000Z"))).toBe(true);
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
