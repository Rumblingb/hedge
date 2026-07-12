import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { assessLatestOperatorIntent } from "../src/engine/operatorIntent.js";

describe("assessLatestOperatorIntent", () => {
  it("treats normal voice suggestions as advisory research focus", async () => {
    const dir = await mkdtemp(join(tmpdir(), "operator-intent-"));
    const path = join(dir, "intent.json");
    await writeFile(path, JSON.stringify({
      source: "voice",
      text: "Focus NQ session momentum and opening range ideas today."
    }));

    const assessment = await assessLatestOperatorIntent({ path });

    expect(assessment.status).toBe("advisory");
    expect(assessment.preferredSymbols).toContain("NQ");
    expect(assessment.preferredStrategies).toEqual(expect.arrayContaining(["session-momentum", "opening-range-reversal"]));
    expect(assessment.executionBlockers).toHaveLength(0);
  });

  it("blocks execution widening when voice asks to override risk gates", async () => {
    const dir = await mkdtemp(join(tmpdir(), "operator-intent-risk-"));
    const path = join(dir, "intent.json");
    await writeFile(path, JSON.stringify({
      source: "voice",
      requestedActions: ["Enable live routing and ignore OOS today."]
    }));

    const assessment = await assessLatestOperatorIntent({ path });

    expect(assessment.status).toBe("requires-approval");
    expect(assessment.executionBlockers.join(" ")).toMatch(/requires explicit approval/i);
    expect(assessment.warnings.length).toBeGreaterThan(0);
  });
});
