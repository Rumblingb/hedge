import { mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as freeSources from "../src/data/freeSources.js";
import { assessFuturesDatasetStatus, buildFuturesLoopRefreshConfigFromEnv, prepareFuturesLoopDataset } from "../src/live/futuresPreflight.js";

const tempDirs: string[] = [];

async function writeCsv(filePath: string, rows: string[]): Promise<void> {
  await writeFile(filePath, `ts,symbol,open,high,low,close,volume\n${rows.join("\n")}\n`, "utf8");
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("futures preflight", () => {
  it("marks stale and short datasets for refresh", async () => {
    const dir = await mkdtemp(path.join(os.tmpdir(), "bill-futures-preflight-"));
    tempDirs.push(dir);
    const csvPath = path.join(dir, "stale.csv");
    await writeCsv(csvPath, [
      "2026-04-01T13:30:00.000Z,NQ,1,2,0.5,1.5,100",
      "2026-04-01T13:30:00.000Z,ES,1,2,0.5,1.5,100"
    ]);

    const status = await assessFuturesDatasetStatus({
      csvPath,
      now: new Date("2026-04-18T00:00:00.000Z"),
      maxStaleHours: 6,
      minDistinctDays: 7
    });

    expect(status.shouldRefresh).toBe(true);
    expect(status.reasons.some((reason) => reason.includes("distinct day"))).toBe(true);
    expect(status.reasons.some((reason) => reason.includes("old"))).toBe(true);
  });

  it("builds refresh config from env", () => {
    const config = buildFuturesLoopRefreshConfigFromEnv({
      BILL_FUTURES_LOOP_REFRESH_ENABLED: "true",
      BILL_FUTURES_LOOP_REFRESH_INTERVAL: "5m",
      BILL_FUTURES_LOOP_REFRESH_RANGE: "12d",
      BILL_FUTURES_LOOP_REFRESH_PROVIDER: "polygon",
      BILL_FUTURES_LOOP_REFRESH_MAX_STALE_HOURS: "4",
      BILL_FUTURES_LOOP_MIN_DISTINCT_DAYS: "9",
      BILL_FUTURES_SYMBOLS: "NQ,ES,CL"
    });

    expect(config.interval).toBe("5m");
    expect(config.range).toBe("12d");
    expect(config.provider).toBe("polygon");
    expect(config.maxStaleHours).toBe(4);
    expect(config.minDistinctDays).toBe(9);
    expect(config.symbols).toEqual(["NQ", "ES", "CL"]);
  });

  it("falls back to the existing dataset if refresh is disabled", async () => {
    const dir = await mkdtemp(path.join(os.tmpdir(), "bill-futures-preflight-"));
    tempDirs.push(dir);
    const csvPath = path.join(dir, "existing.csv");
    await writeCsv(csvPath, [
      "2026-04-17T13:30:00.000Z,NQ,1,2,0.5,1.5,100",
      "2026-04-17T13:30:00.000Z,ES,1,2,0.5,1.5,100",
      "2026-04-18T13:30:00.000Z,NQ,1,2,0.5,1.5,100",
      "2026-04-18T13:30:00.000Z,ES,1,2,0.5,1.5,100"
    ]);

    const prepared = await prepareFuturesLoopDataset({
      csvPath,
      env: {
        BILL_FUTURES_LOOP_REFRESH_ENABLED: "false"
      } as NodeJS.ProcessEnv,
      now: new Date("2026-04-18T14:00:00.000Z")
    });

    expect(prepared.selectedPath).toBe(csvPath);
    expect(prepared.refreshed).toBe(false);
  });

  it("falls back to the freshest normalized dataset on disk when refresh fails", async () => {
    const dir = await mkdtemp(path.join(os.tmpdir(), "bill-futures-preflight-"));
    tempDirs.push(dir);
    const requestedPath = path.join(dir, "ALL-6MARKETS-1m-5d-normalized.csv");
    const fresherPath = path.join(dir, "ALL-6MARKETS-1m-10d-normalized.csv");
    await writeCsv(requestedPath, [
      "2026-04-01T13:30:00.000Z,NQ,1,2,0.5,1.5,100",
      "2026-04-01T13:30:00.000Z,ES,1,2,0.5,1.5,100"
    ]);
    await writeCsv(fresherPath, [
      "2026-04-08T13:30:00.000Z,NQ,1,2,0.5,1.5,100",
      "2026-04-08T13:30:00.000Z,ES,1,2,0.5,1.5,100",
      "2026-04-16T13:30:00.000Z,NQ,1,2,0.5,1.5,100",
      "2026-04-16T13:30:00.000Z,ES,1,2,0.5,1.5,100",
      "2026-04-17T13:30:00.000Z,NQ,1,2,0.5,1.5,100",
      "2026-04-17T13:30:00.000Z,ES,1,2,0.5,1.5,100"
    ]);

    const prepared = await prepareFuturesLoopDataset({
      csvPath: requestedPath,
      env: {
        BILL_FUTURES_LOOP_REFRESH_ENABLED: "true",
        BILL_FUTURES_LOOP_REFRESH_PROVIDER: "polygon"
      } as NodeJS.ProcessEnv,
      now: new Date("2026-04-18T14:00:00.000Z")
    });

    expect(prepared.refreshed).toBe(false);
    expect(prepared.selectedPath).toBe(fresherPath);
    expect(prepared.warnings.some((warning) => warning.includes("freshest existing normalized dataset"))).toBe(true);
  });

  it("merges partial refresh output with the last good bars for failed symbols", async () => {
    const dir = await mkdtemp(path.join(os.tmpdir(), "bill-futures-preflight-"));
    tempDirs.push(dir);
    const requestedPath = path.join(dir, "ALL-2MARKETS-1m-90d-normalized.csv");
    await writeCsv(requestedPath, [
      "2026-04-23T13:30:00.000Z,NQ,1,2,0.5,1.5,100",
      "2026-04-23T13:30:00.000Z,ES,1,2,0.5,1.5,100",
      "2026-04-24T13:30:00.000Z,NQ,1,2,0.5,1.5,100",
      "2026-04-24T13:30:00.000Z,ES,1,2,0.5,1.5,100"
    ]);

    vi.spyOn(freeSources, "fetchFreeBars").mockImplementation(async ({ symbol }) => {
      if (symbol === "NQ") {
        throw new Error("provider timeout");
      }
      return {
        providerUsed: "databento",
        providerSymbol: "ES.v.0",
        warnings: [],
        bars: [
          {
            ts: "2026-04-24T13:30:00.000Z",
            symbol: "ES",
            open: 10,
            high: 12,
            low: 9,
            close: 11,
            volume: 100
          }
        ]
      };
    });

    const prepared = await prepareFuturesLoopDataset({
      csvPath: requestedPath,
      env: {
        BILL_FUTURES_LOOP_REFRESH_ENABLED: "true",
        BILL_FUTURES_LOOP_REFRESH_PROVIDER: "databento",
        BILL_FUTURES_SYMBOLS: "NQ,ES"
      } as NodeJS.ProcessEnv,
      now: new Date("2026-04-24T15:00:00.000Z")
    });

    expect(prepared.refreshed).toBe(true);
    expect(prepared.selectedPath).toBe(path.join(dir, "ALL-2MARKETS-1m-10d-normalized.csv"));
    expect(prepared.status.inspection?.symbols).toEqual(["ES", "NQ"]);
    expect(prepared.warnings.some((warning) => warning.includes("merged the last good bars for NQ"))).toBe(true);
  });

  it("routes stale failed symbols out of the active dataset instead of dragging the refresh backward", async () => {
    const dir = await mkdtemp(path.join(os.tmpdir(), "bill-futures-preflight-"));
    tempDirs.push(dir);
    const requestedPath = path.join(dir, "ALL-2MARKETS-1m-90d-normalized.csv");
    await writeCsv(requestedPath, [
      "2026-04-20T13:30:00.000Z,NQ,1,2,0.5,1.5,100",
      "2026-04-20T13:30:00.000Z,ES,1,2,0.5,1.5,100"
    ]);

    vi.spyOn(freeSources, "fetchFreeBars").mockImplementation(async ({ symbol }) => {
      if (symbol === "ES") {
        throw new Error("provider timeout");
      }
      return {
        providerUsed: "databento",
        providerSymbol: "NQ.v.0",
        warnings: [],
        bars: [
          {
            ts: "2026-04-24T13:30:00.000Z",
            symbol: "NQ",
            open: 10,
            high: 12,
            low: 9,
            close: 11,
            volume: 100
          },
          {
            ts: "2026-04-24T13:31:00.000Z",
            symbol: "NQ",
            open: 11,
            high: 13,
            low: 10,
            close: 12,
            volume: 110
          }
        ]
      };
    });

    const prepared = await prepareFuturesLoopDataset({
      csvPath: requestedPath,
      env: {
        BILL_FUTURES_LOOP_REFRESH_ENABLED: "true",
        BILL_FUTURES_LOOP_REFRESH_PROVIDER: "databento",
        BILL_FUTURES_SYMBOLS: "NQ,ES",
        BILL_FUTURES_LOOP_REFRESH_MAX_STALE_HOURS: "6",
        BILL_FUTURES_LOOP_MIN_DISTINCT_DAYS: "1"
      } as NodeJS.ProcessEnv,
      now: new Date("2026-04-24T15:00:00.000Z")
    });

    expect(prepared.refreshed).toBe(true);
    expect(prepared.selectedPath).toBe(path.join(dir, "ALL-2MARKETS-1m-10d-normalized.csv"));
    expect(prepared.status.inspection?.symbols).toEqual(["NQ"]);
    expect(prepared.status.shouldRefresh).toBe(false);
    expect(prepared.warnings.some((warning) => warning.includes("routing around degraded symbols"))).toBe(true);
    expect(prepared.warnings.some((warning) => warning.includes("routed ES out of the active dataset"))).toBe(true);
  });

  it("reports the refreshed dataset status after a full successful refresh", async () => {
    const dir = await mkdtemp(path.join(os.tmpdir(), "bill-futures-preflight-"));
    tempDirs.push(dir);
    const requestedPath = path.join(dir, "ALL-2MARKETS-1m-5d-normalized.csv");
    await writeCsv(requestedPath, [
      "2026-04-20T13:30:00.000Z,NQ,1,2,0.5,1.5,100",
      "2026-04-20T13:30:00.000Z,ES,1,2,0.5,1.5,100"
    ]);

    vi.spyOn(freeSources, "fetchFreeBars").mockImplementation(async ({ symbol }) => ({
      providerUsed: "databento",
      providerSymbol: `${symbol}.v.0`,
      warnings: [],
      bars: [
        {
          ts: "2026-04-24T13:30:00.000Z",
          symbol,
          open: 10,
          high: 12,
          low: 9,
          close: 11,
          volume: 100
        },
        {
          ts: "2026-04-24T13:31:00.000Z",
          symbol,
          open: 11,
          high: 13,
          low: 10,
          close: 12,
          volume: 110
        }
      ]
    }));

    const prepared = await prepareFuturesLoopDataset({
      csvPath: requestedPath,
      env: {
        BILL_FUTURES_LOOP_REFRESH_ENABLED: "true",
        BILL_FUTURES_LOOP_REFRESH_PROVIDER: "databento",
        BILL_FUTURES_SYMBOLS: "NQ,ES",
        BILL_FUTURES_LOOP_REFRESH_RANGE: "10d",
        BILL_FUTURES_LOOP_REFRESH_MAX_STALE_HOURS: "6",
        BILL_FUTURES_LOOP_MIN_DISTINCT_DAYS: "1"
      } as NodeJS.ProcessEnv,
      now: new Date("2026-04-24T15:00:00.000Z")
    });

    expect(prepared.refreshed).toBe(true);
    expect(prepared.selectedPath).toBe(path.join(dir, "ALL-2MARKETS-1m-10d-normalized.csv"));
    expect(prepared.status.path).toBe(prepared.selectedPath);
    expect(prepared.status.shouldRefresh).toBe(false);
    expect(prepared.status.inspection?.symbols).toEqual(["ES", "NQ"]);
  });
});
