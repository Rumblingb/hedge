import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { Bar } from "../src/domain.js";
import { buildAlphaLabReport, buildFuturesFeatureStore, rankAlphaCandidates } from "../src/engine/alphaLab.js";

function engineeredMomentumBars(symbol = "NQ", count = 220): Bar[] {
  const bars: Bar[] = [];
  let close = 100;
  let priorImpulse = 0.08;

  for (let index = 0; index < count; index += 1) {
    const impulse = index % 18 < 9 ? 0.08 : -0.08;
    const drift = priorImpulse * 0.72 + impulse * 0.28;
    const open = close;
    close = close * (1 + drift / 100);
    priorImpulse = drift;
    bars.push({
      ts: new Date(Date.UTC(2026, 0, 1, 14, index)).toISOString(),
      symbol,
      open,
      high: Math.max(open, close) * 1.0003,
      low: Math.min(open, close) * 0.9997,
      close,
      volume: 1000 + Math.abs(drift) * 5000 + (index % 7) * 10
    });
  }

  return bars;
}

describe("alpha lab", () => {
  it("builds point-in-time feature rows with forward returns separated", () => {
    const rows = buildFuturesFeatureStore(engineeredMomentumBars(), [5]);

    expect(rows.length).toBeGreaterThan(100);
    expect(rows[0]?.features.ret_1).toBeTypeOf("number");
    expect(rows[0]?.forwardReturns.fwd_ret_5).toBeTypeOf("number");
    expect(Object.keys(rows[0]?.features ?? {})).not.toContain("fwd_ret_5");
  });

  it("ranks stable train/test alpha candidates after cost stress", () => {
    const rows = buildFuturesFeatureStore(engineeredMomentumBars(), [5]);
    const candidates = rankAlphaCandidates({
      rows,
      horizonsBars: [5],
      costStressPct: 0.001,
      maxCandidates: 10
    });

    expect(candidates[0]?.verdict).not.toBe("reject");
    expect(Math.abs(candidates[0]?.testIc ?? 0)).toBeGreaterThan(0.03);
    expect(candidates[0]?.netEdgePct ?? 0).toBeGreaterThan(0);
    expect(candidates[0]?.purgedWalkforward.length).toBeGreaterThanOrEqual(3);
    expect(candidates[0]?.regimeValidation.length).toBe(3);
  });

  it("writes feature store and candidate artifacts", async () => {
    const dir = await mkdtemp(join(tmpdir(), "alpha-lab-"));
    const featureStorePath = join(dir, "features.jsonl");
    const candidatePath = join(dir, "alpha.json");
    const report = await buildAlphaLabReport({
      bars: engineeredMomentumBars(),
      csvPath: "synthetic.csv",
      featureStorePath,
      candidatePath,
      horizonsBars: [5],
      costStressPct: 0.001,
      now: () => "2026-05-08T00:00:00.000Z"
    });

    expect(report.command).toBe("alpha-lab");
    expect(report.featureVersion).toMatch(/^[a-f0-9]{16}$/);
    expect(report.purgeBars).toBe(5);
    expect(report.featureRows).toBeGreaterThan(100);
    expect((await readFile(featureStorePath, "utf8")).split("\n")[0]).toContain("\"features\"");
    expect(JSON.parse(await readFile(candidatePath, "utf8")).command).toBe("alpha-lab");
  });
});
