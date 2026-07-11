import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { buildHermesIntegrationAudit } from "../src/engine/hermesIntegrationAudit.js";

describe("hermes integration audit", () => {
  it("keeps Hermes as observer/control-plane and identifies live-money blockers", async () => {
    const root = await mkdtemp(join(tmpdir(), "hermes-audit-"));
    const hermesRoot = join(root, "hermes");
    const hedgeRoot = join(root, "hedge");
    const outputPath = join(root, "state", "hermes-integration-audit.latest.json");
    const boardPath = join(root, "state", "cashflow-board.latest.json");

    await mkdir(join(hermesRoot), { recursive: true });
    await mkdir(join(hedgeRoot, "src", "engine"), { recursive: true });
    await mkdir(join(hedgeRoot, "scripts"), { recursive: true });
    await mkdir(join(root, "state"), { recursive: true });
    await writeFile(join(hermesRoot, "full_brain_dashboard.py"), "# dashboard\n", "utf8");
    await writeFile(join(hedgeRoot, "src", "engine", "strategyCorrelation.ts"), "export {}\n", "utf8");
    await writeFile(join(hedgeRoot, "scripts", "signal_decay_monitor.py"), "# decay\n", "utf8");
    await writeFile(boardPath, JSON.stringify({ status: "shadow-build" }), "utf8");

    const report = await buildHermesIntegrationAudit({
      outputPath,
      hermesRoot,
      hedgeRoot,
      cashflowBoardPath: boardPath,
      now: () => "2026-05-06T12:00:00.000Z"
    });

    expect(report.currentBoardStatus).toBe("shadow-build");
    expect(report.observedArchitecture.llmBoundary).toContain("do not size");
    expect(report.mergePlan.some((entry) => entry.priority === "merge-now" && entry.path.endsWith("strategyCorrelation.ts"))).toBe(true);
    expect(report.liveMoneyHoles.some((hole) => hole.area === "prediction settlement" && hole.severity === "critical")).toBe(true);
    expect(report.rejectedPatterns).toContain("Do not merge the dirty hedge tree wholesale.");

    const persisted = JSON.parse(await readFile(outputPath, "utf8"));
    expect(persisted.command).toBe("hermes-integration-audit");
  });
});
