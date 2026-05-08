import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { buildPredictionEdgeIntakeReport } from "../src/prediction/edgeIntake.js";

describe("prediction edge intake", () => {
  it("promotes structural edges to paper-watch and quarantines liquidity traps", async () => {
    const dir = join(tmpdir(), `edge-intake-${Date.now()}`);
    await mkdir(dir, { recursive: true });
    const inputPath = join(dir, "edges.json");
    await writeFile(inputPath, JSON.stringify({
      edges: {
        mispriced_probabilities: [
          {
            id: "edge-1",
            category: "crypto",
            title: "Base Token Launch - Temporal Discontinuity",
            confidence: "high",
            markets: [
              { slug: "will-base-launch-a-token-by-june-30-2026", spread: 0.001, liquidity: 53357 }
            ],
            edge_direction: "LONG June YES"
          }
        ],
        thin_liquidity_anomalies: [
          {
            id: "thin-1",
            category: "crypto",
            title: "Pump.fun Airdrop - Extreme Spread / Micro Liquidity",
            confidence: "medium",
            market: { slug: "pump-fun-airdrop", spread: 0.26, liquidity: 493 },
            edge_type: "Avoid - broken market"
          }
        ]
      }
    }));

    const report = await buildPredictionEdgeIntakeReport({
      inputPath,
      now: () => "2026-05-08T00:00:00.000Z"
    });

    expect(report.counts["paper-watch"]).toBe(1);
    expect(report.counts.avoid).toBe(1);
    expect(report.topEdges[0]?.id).toBe("edge-1");
    expect(report.avoidEdges[0]?.blockers).toContain("liquidity-trap");
  });
});
