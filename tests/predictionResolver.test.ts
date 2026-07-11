import { describe, expect, it, vi, afterEach } from "vitest";
import {
  parseCandidateId,
  buildCalibrationReport,
  resolvePolymarketMarket,
  type ResolvedJournalRow
} from "../src/prediction/resolver.js";

describe("parseCandidateId", () => {
  it("parses two-venue ids", () => {
    const r = parseCandidateId("polymarket:1919425__manifold:ghI9lZO0CP");
    expect(r).toEqual({ venueA: "polymarket", externalIdA: "1919425", venueB: "manifold", externalIdB: "ghI9lZO0CP" });
  });
  it("returns null on malformed input", () => {
    expect(parseCandidateId("polymarket-only")).toBeNull();
    expect(parseCandidateId("a__b__c")).toBeNull();
    expect(parseCandidateId(":foo__bar:baz")).toBeNull();
  });
});

function fixtureRow(partial: Partial<ResolvedJournalRow>): ResolvedJournalRow {
  return {
    ts: "2026-04-15T19:00:00.000Z",
    candidateId: partial.candidateId ?? "polymarket:X__manifold:Y",
    venueA: "polymarket",
    venueB: "manifold",
    marketType: "binary",
    normalizedEventKey: "",
    normalizedQuestionKey: "",
    normalizedOutcomeKey: "yes",
    eventTitleA: "",
    eventTitleB: "",
    outcomeA: "Yes",
    outcomeB: "Yes",
    settlementCompatible: true,
    matchScore: 0.8,
    entityOverlap: 0.5,
    questionOverlap: 0.7,
    grossEdgePct: 3,
    netEdgePct: 1.5,
    feeDragPct: 1.5,
    sizeVerdict: "ok",
    verdict: "watch",
    reasons: [],
    resolvedAt: "2026-04-16T00:00:00.000Z",
    settlementMismatch: false,
    realizedGrossEdgePct: 0,
    realizedNetEdgePct: 0,
    calibrationBucket: "0-2",
    ...partial
  };
}

describe("buildCalibrationReport", () => {
  it("returns empty on no rows", () => {
    const r = buildCalibrationReport([]);
    expect(r.totalResolved).toBe(0);
    expect(r.buckets).toEqual([]);
  });
  it("buckets by predicted netEdgePct and counts mismatches", () => {
    const rows: ResolvedJournalRow[] = [
      fixtureRow({ netEdgePct: 1, realizedNetEdgePct: 0.5, calibrationBucket: "0-2" }),
      fixtureRow({ netEdgePct: 1.5, realizedNetEdgePct: -0.2, calibrationBucket: "0-2" }),
      fixtureRow({ netEdgePct: 3, realizedNetEdgePct: 2, calibrationBucket: "2-5" }),
      fixtureRow({ netEdgePct: 6, realizedNetEdgePct: -1, calibrationBucket: "5+", settlementMismatch: true })
    ];
    const r = buildCalibrationReport(rows);
    expect(r.totalResolved).toBe(4);
    expect(r.settlementMismatches).toBe(1);
    const b02 = r.buckets.find((b) => b.predictedEdgeBucket === "0-2");
    expect(b02?.n).toBe(2);
    expect(b02?.realizedEdgePctMean).toBeCloseTo(0.15, 5);
    expect(r.hitRatePct).toBeCloseTo(50, 5); // 2 of 4 positive realized net
  });
});

describe("resolvePolymarketMarket", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("returns resolved=false when not closed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ closed: false }]
    }));
    const r = await resolvePolymarketMarket("123");
    expect(r.resolved).toBe(false);
  });
  it("returns resolved=true with winning outcome label", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{
        closed: true,
        outcomePrices: JSON.stringify(["0.92", "0.08"]),
        outcomes: JSON.stringify(["Yes", "No"]),
        closedTime: "2026-04-15T20:00:00Z"
      }]
    }));
    const r = await resolvePolymarketMarket("123");
    expect(r.resolved).toBe(true);
    expect(r.outcome).toBe("Yes");
    expect(r.closedAt).toBe("2026-04-15T20:00:00Z");
  });
  it("handles non-ok fetch", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => null }));
    const r = await resolvePolymarketMarket("123");
    expect(r.resolved).toBe(false);
  });
});
