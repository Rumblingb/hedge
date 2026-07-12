import { describe, expect, it } from "vitest";
import { writeFile, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { aggregateCounterfactual, buildCounterfactualReport, summarizeCounterfactual } from "../src/prediction/counterfactual.js";
import type { PredictionCandidate } from "../src/prediction/types.js";

function row(partial: Partial<PredictionCandidate>): PredictionCandidate {
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
    netEdgePct: -1,
    feeDragPct: 4,
    sizeVerdict: "ok",
    verdict: "reject",
    reasons: ["negative-net-edge", "cost-drag-exceeds-edge"],
    ...partial
  };
}

describe("aggregateCounterfactual", () => {
  it("counts total/accepted/rejected and buckets reasons", () => {
    const now = new Date("2026-04-15T20:00:00Z");
    const rows: PredictionCandidate[] = [
      row({ verdict: "watch", reasons: [] }),
      row({ verdict: "reject", reasons: ["negative-net-edge"] }),
      row({ verdict: "reject", reasons: ["negative-net-edge", "cost-drag-exceeds-edge"] }),
      row({ verdict: "reject", reasons: ["thin-size"] })
    ];
    const r = aggregateCounterfactual(rows, 24, now);
    expect(r.totalCandidates).toBe(4);
    expect(r.acceptedCount).toBe(1);
    expect(r.rejectedCount).toBe(3);
    const negNet = r.rejectionReasons.find((b) => b.reason === "negative-net-edge");
    expect(negNet?.count).toBe(2);
    expect(negNet?.nearMissCount).toBe(1);
    const thin = r.rejectionReasons.find((b) => b.reason === "thin-size");
    expect(thin?.nearMissCount).toBe(1);
  });

  it("filters by window", () => {
    const now = new Date("2026-04-15T20:00:00Z");
    const rows: PredictionCandidate[] = [
      row({ ts: "2026-04-15T19:00:00.000Z" }),
      row({ ts: "2026-04-10T00:00:00.000Z" })
    ];
    const r = aggregateCounterfactual(rows, 24, now);
    expect(r.totalCandidates).toBe(1);
  });

  it("ranks near-misses by gross edge desc", () => {
    const now = new Date("2026-04-15T20:00:00Z");
    const rows: PredictionCandidate[] = [
      row({ candidateId: "A", grossEdgePct: 1, reasons: ["subscale-edge"] }),
      row({ candidateId: "B", grossEdgePct: 4, reasons: ["subscale-edge"] }),
      row({ candidateId: "C", grossEdgePct: 2, reasons: ["subscale-edge"] })
    ];
    const r = aggregateCounterfactual(rows, 24, now);
    expect(r.nearMisses.map((m) => m.candidateId)).toEqual(["B", "C", "A"]);
  });

  it("triggers cost-drag suggestion", () => {
    const now = new Date("2026-04-15T20:00:00Z");
    const rows: PredictionCandidate[] = Array.from({ length: 10 }, () =>
      row({ verdict: "reject", reasons: ["cost-drag-exceeds-edge"], grossEdgePct: 3, netEdgePct: -1, feeDragPct: 4 })
    );
    const r = aggregateCounterfactual(rows, 24, now);
    expect(r.suggestions.some((s) => s.includes("cost-drag"))).toBe(true);
  });
});

describe("buildCounterfactualReport (from disk)", () => {
  it("reads jsonl fixture and aggregates", async () => {
    const dir = await mkdtemp(join(tmpdir(), "cf-"));
    const path = join(dir, "journal.jsonl");
    const now = new Date("2026-04-15T20:00:00Z");
    const rows = [
      row({ ts: "2026-04-15T19:00:00.000Z", verdict: "watch", reasons: [] }),
      row({ ts: "2026-04-15T19:10:00.000Z", verdict: "reject", reasons: ["weak-match"] })
    ];
    await writeFile(path, rows.map((r) => JSON.stringify(r)).join("\n"), "utf8");
    const r = await buildCounterfactualReport({ journalPath: path, now });
    expect(r.totalCandidates).toBe(2);
    const summary = summarizeCounterfactual(r);
    expect(summary).toContain("Counterfactual");
    expect(summary).toContain("weak-match");
  });
});
