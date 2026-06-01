import { describe, expect, it } from "vitest";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

type SelectedAsset = {
  tokenId: string;
  manual?: boolean;
  reason?: string;
  question?: string;
  eventTitle?: string;
  outcomeLabel?: string;
};

type Selection = {
  assets: SelectedAsset[];
  diagnostics: {
    acceptedAutomaticCount: number;
    rejectedAutomaticCount: number;
    rejectionCounts: Record<string, number>;
  };
};

type SelectorOpts = {
  terms: string[];
  excludeTerms: string[];
  minPrice: number;
  maxPrice: number;
  maxSpread: number;
  maxDaysToExpiry: number;
  minTopBookDepth: number;
  requireExpiry: boolean;
  requireSnapshotBook: boolean;
  tokenIds: string[];
  maxAssets: number;
  nowMs: number;
};

type RecorderModule = {
  buildSummary: (args: {
    reason: string;
    startedAt: string;
    endedAt: string;
    opts: SelectorOpts & {
      durationSec: number;
      snapshot: string;
      outDir: string;
      statePath: string;
    };
    outPath: string;
    assets: unknown[];
    selectionDiagnostics: Record<string, unknown>;
    storageSafety: Record<string, unknown>;
    initialOutputBytes: number;
    latestBookState: unknown[];
    messages: number;
    counts: Record<string, number>;
  }) => Record<string, unknown>;
  selectAssetsWithDiagnostics: (rows: unknown[], opts: SelectorOpts) => Selection;
  normalizeEvent: (message: Record<string, unknown>) => Record<string, unknown>;
  storageSafetyDiagnostics: (outDir: string, opts: SelectorOpts & { maxOutputMb: number; minFreeGb: number }) => Promise<{
    safeToStart: boolean;
    maxOutputBytes: number;
    maxOutputMb: number;
    minFreeGb: number;
    freeGb: number;
  }>;
  updateBookState: (bookState: Map<string, Record<string, unknown>>, record: Record<string, unknown>) => void;
  liveQualityDiagnostics: (selectedAssets: unknown[], latestBookState: unknown[], opts: SelectorOpts) => {
    fillableLiveBookCount: number;
    observedLiveBookCount: number;
    statusCounts: Record<string, number>;
    readyForPaperEvidence: boolean;
  };
};

// The recorder is an executable ESM script; it intentionally has no TS declarations.
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
const { buildSummary, liveQualityDiagnostics, normalizeEvent, selectAssetsWithDiagnostics, storageSafetyDiagnostics, updateBookState } = (await import("../scripts/polymarket_clob_recorder.mjs")) as RecorderModule;

const baseOpts: SelectorOpts = {
  terms: ["fed", "iran", "trump", "bitcoin"],
  excludeTerms: ["world cup", "2028", "presidential election", "presidential nomination"],
  minPrice: 0.01,
  maxPrice: 0.99,
  maxSpread: 0.12,
  maxDaysToExpiry: 45,
  minTopBookDepth: 1_000,
  requireExpiry: true,
  requireSnapshotBook: true,
  tokenIds: [],
  maxAssets: 10,
  nowMs: Date.parse("2026-05-30T12:00:00Z")
};

describe("polymarket CLOB recorder selection", () => {
  it("prefers fillable near-term standing-term markets over stale or noisy loose matches", () => {
    const rows = [
      {
        clobTokenId: "world-cup-iran",
        eventTitle: "World Cup Winner",
        marketQuestion: "Will Iran win the 2026 FIFA World Cup?",
        expiry: "2026-07-20T00:00:00Z",
        price: 0.0015,
        bestBid: 0.001,
        bestAsk: 0.002,
        topBookDepth: 1_000_000,
        displayedSize: 9_000_000
      },
      {
        clobTokenId: "stale-ceasefire",
        eventTitle: "Iran ceasefire continues through...?",
        marketQuestion: "Will the Iran ceasefire continue through May 24?",
        price: 0.9985,
        bestBid: 0.998,
        bestAsk: 0.999,
        topBookDepth: 1_000_000,
        displayedSize: 6_000_000
      },
      {
        clobTokenId: "long-dated-trump",
        eventTitle: "Presidential Election Winner 2028",
        marketQuestion: "Will Eric Trump win the 2028 US Presidential Election?",
        expiry: "2028-11-07T00:00:00Z",
        price: 0.05,
        topBookDepth: 2_000_000,
        displayedSize: 2_000_000
      },
      {
        clobTokenId: "fed-no-change",
        eventTitle: "Fed decision after June 2026 meeting",
        marketQuestion: "Will there be no change in Fed interest rates after the June 2026 meeting?",
        expiry: "2026-06-18T00:00:00Z",
        price: 0.72,
        bestBid: 0.71,
        bestAsk: 0.73,
        topBookDepth: 140_000,
        displayedSize: 200_000
      },
      {
        clobTokenId: "iran-peace",
        eventTitle: "US x Iran permanent peace deal by May 31, 2026?",
        marketQuestion: "US x Iran permanent peace deal by May 31, 2026?",
        expiry: "2026-06-01T00:00:00Z",
        price: 0.135,
        bestBid: 0.13,
        bestAsk: 0.15,
        topBookDepth: 80_000,
        displayedSize: 100_000
      }
    ];

    const selection = selectAssetsWithDiagnostics(rows, baseOpts);
    const selectedIds = selection.assets.map((asset) => asset.tokenId);

    expect(selectedIds).toEqual(["fed-no-change", "iran-peace"]);
    expect(selection.diagnostics.rejectionCounts["excluded-term"]).toBe(2);
    expect(selection.diagnostics.rejectionCounts["above-max-price"]).toBe(1);
  });

  it("keeps manually requested token ids even when automatic filters would reject them", () => {
    const selection = selectAssetsWithDiagnostics([], {
      ...baseOpts,
      tokenIds: ["manual-token"],
      maxAssets: 1
    });

    expect(selection.assets).toEqual([
      expect.objectContaining({
        tokenId: "manual-token",
        manual: true,
        reason: "manual"
      })
    ]);
    expect(selection.diagnostics.rejectedAutomaticCount).toBe(0);
  });

  it("enriches manually requested token ids from snapshot rows even when terms do not match", () => {
    const selection = selectAssetsWithDiagnostics(
      [
        {
          clobTokenId: "manual-token",
          eventTitle: "Championship Winner",
          marketQuestion: "Will a team win the championship?",
          outcomeLabel: "Yes",
          expiry: "2026-06-18T00:00:00Z",
          price: 0.42,
          bestBid: 0.41,
          bestAsk: 0.43,
          topBookDepth: 10_000,
          displayedSize: 10_000
        }
      ],
      {
        ...baseOpts,
        tokenIds: ["manual-token"],
        maxAssets: 1
      }
    );

    expect(selection.assets).toEqual([
      expect.objectContaining({
        tokenId: "manual-token",
        manual: true,
        reason: "manual+snapshot-match",
        question: "Will a team win the championship?",
        eventTitle: "Championship Winner",
        outcomeLabel: "Yes"
      })
    ]);
    expect(selection.diagnostics.acceptedAutomaticCount).toBe(0);
    expect(selection.diagnostics.rejectedAutomaticCount).toBe(0);
  });

  it("keeps manual token id placeholders when the snapshot has no matching row", () => {
    const selection = selectAssetsWithDiagnostics(
      [
        {
          clobTokenId: "other-token",
          eventTitle: "Fed decision after June 2026 meeting",
          marketQuestion: "Will there be no change in Fed interest rates after the June 2026 meeting?",
          expiry: "2026-06-18T00:00:00Z",
          price: 0.72,
          bestBid: 0.71,
          bestAsk: 0.73,
          topBookDepth: 140_000,
          displayedSize: 200_000
        }
      ],
      {
        ...baseOpts,
        tokenIds: ["manual-token"],
        maxAssets: 2
      }
    );

    expect(selection.assets).toEqual([
      expect.objectContaining({
        tokenId: "manual-token",
        manual: true,
        reason: "manual",
        question: "manual token id"
      }),
      expect.objectContaining({
        tokenId: "other-token",
        manual: false,
        reason: "snapshot-term-match"
      })
    ]);
  });

  it("summarizes live fillability separately from snapshot selection", () => {
    const diagnostics = liveQualityDiagnostics(
      [
        { tokenId: "tight", question: "tight book" },
        { tokenId: "wide", question: "wide book" },
        { tokenId: "missing", question: "missing book" }
      ],
      [
        { assetId: "tight", bestBid: 0.48, bestAsk: 0.5, spread: 0.02, bidSize: 700, askSize: 600 },
        { assetId: "wide", bestBid: 0.08, bestAsk: 0.91, spread: 0.83, bidSize: 5_000, askSize: 5_000 }
      ],
      baseOpts
    );

    expect(diagnostics.fillableLiveBookCount).toBe(1);
    expect(diagnostics.observedLiveBookCount).toBe(2);
    expect(diagnostics.statusCounts["fillable-live-book"]).toBe(1);
    expect(diagnostics.statusCounts["live-spread-too-wide"]).toBe(1);
    expect(diagnostics.statusCounts["missing-live-book"]).toBe(1);
    expect(diagnostics.readyForPaperEvidence).toBe(false);
  });

  it("normalizes unsorted book snapshots before truncating top levels", () => {
    const record = normalizeEvent({
      event_type: "book",
      asset_id: "asset-a",
      timestamp: "1766789469958",
      bids: [
        { price: "0.01", size: "1000" },
        { price: "0.02", size: "1000" },
        { price: "0.03", size: "1000" },
        { price: "0.04", size: "1000" },
        { price: "0.05", size: "1000" },
        { price: "0.06", size: "1000" },
        { price: "0.07", size: "1000" },
        { price: "0.08", size: "1000" },
        { price: "0.69", size: "700" },
      ],
      asks: [
        { price: "0.99", size: "1000" },
        { price: "0.98", size: "1000" },
        { price: "0.97", size: "1000" },
        { price: "0.96", size: "1000" },
        { price: "0.95", size: "1000" },
        { price: "0.94", size: "1000" },
        { price: "0.93", size: "1000" },
        { price: "0.92", size: "1000" },
        { price: "0.70", size: "800" },
      ],
    });
    const bookState = new Map<string, Record<string, unknown>>();

    updateBookState(bookState, record);

    expect((record.bids as Array<Record<string, string>>)[0].price).toBe("0.69");
    expect((record.asks as Array<Record<string, string>>)[0].price).toBe("0.7");
    expect(bookState.get("asset-a")).toEqual(expect.objectContaining({
      bestBid: 0.69,
      bestAsk: 0.7,
      bidSize: 700,
      askSize: 800,
      spread: 0.01,
    }));
  });

  it("reports storage limits before long public capture runs", async () => {
    const tmp = await fs.mkdtemp(path.join(os.tmpdir(), "clob-recorder-"));
    const diagnostics = await storageSafetyDiagnostics(tmp, {
      ...baseOpts,
      maxOutputMb: 12.5,
      minFreeGb: 0,
    });

    expect(diagnostics.safeToStart).toBe(true);
    expect(diagnostics.maxOutputMb).toBe(12.5);
    expect(diagnostics.maxOutputBytes).toBe(Math.floor(12.5 * 1_048_576));
    expect(diagnostics.minFreeGb).toBe(0);
    expect(diagnostics.freeGb).toBeGreaterThanOrEqual(0);
  });

  it("marks recorder summaries as research-only and not broker touching", () => {
    const summary = buildSummary({
      reason: "duration_elapsed",
      startedAt: "2026-05-30T12:00:00.000Z",
      endedAt: "2026-05-30T12:02:00.000Z",
      opts: {
        ...baseOpts,
        durationSec: 120,
        snapshot: "/tmp/snapshot.json",
        outDir: "/tmp",
        statePath: "/tmp/state.json",
      },
      outPath: "/tmp/market-channel.jsonl",
      assets: [],
      selectionDiagnostics: {},
      storageSafety: { maxOutputBytes: 1024 },
      initialOutputBytes: 0,
      latestBookState: [],
      messages: 12,
      counts: { book: 1 },
    });

    expect(summary.status).toBe("ok");
    expect(summary.researchOnly).toBe(true);
    expect(summary.writesOrders).toBe(false);
    expect(summary.touchesBroker).toBe(false);
    expect(summary.readyForPaper).toBe(false);
    expect(summary.readyForExecution).toBe(false);
    expect(summary.outputFiles).toEqual(["/tmp/market-channel.jsonl"]);
  });

  it("uses max output bytes as a per-run cap input", async () => {
    const tmp = await fs.mkdtemp(path.join(os.tmpdir(), "clob-recorder-cap-"));
    const existingFile = path.join(tmp, "2026-05-30-market-channel.jsonl");
    await fs.writeFile(existingFile, "x".repeat(1024), "utf8");
    const diagnostics = await storageSafetyDiagnostics(tmp, {
      ...baseOpts,
      maxOutputMb: 1,
      minFreeGb: 0,
    });

    expect(diagnostics.maxOutputBytes).toBe(1_048_576);
    expect(diagnostics.safeToStart).toBe(true);
  });
});
