import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { inspectTimesFmReadiness, renderTimesFmMarkdown } from "../src/research/timesfm.js";

describe("TimesFM readiness", () => {
  it("keeps TimesFM missing when Python packages and local weights are unavailable", async () => {
    const report = await inspectTimesFmReadiness({
      env: {
        HF_HOME: join(process.cwd(), ".tmp-missing-hf")
      },
      python: "python3",
      ts: "2026-04-22T00:00:00.000Z"
    });

    expect(report.command).toBe("timesfm-status");
    expect(report.role).toBe("research-only");
    expect(report.status === "missing" || report.status === "blocked").toBe(true);
    expect(report.blockers.some((blocker) => blocker.includes("timesfm"))).toBe(true);
    expect(report.blockers.some((blocker) => blocker.includes("torch"))).toBe(true);
    expect(report.blockers.some((blocker) => blocker.includes("model weights"))).toBe(true);

    const markdown = renderTimesFmMarkdown(report);
    expect(markdown).toContain("TimesFM Readiness");
    expect(markdown).toContain("Hermes may monitor this report");
  });

  it("fails closed when the Python executable is unavailable", async () => {
    const report = await inspectTimesFmReadiness({
      env: {},
      python: "python3-not-real",
      ts: "2026-04-22T00:00:00.000Z"
    });

    expect(report.status).toBe("missing");
    expect(report.runtime.python.ok).toBe(false);
    expect(report.blockers).toContain("python3 is not available for TimesFM checks");
  });
});
