import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadTraderIntuition } from "../src/research/traderIntuition.js";

describe("loadTraderIntuition", () => {
  it("distills founder/trader intuition into machine-usable strategy hints", async () => {
    const dir = await mkdtemp(join(tmpdir(), "trader-intuition-"));
    const path = join(dir, "intuition.md");
    await writeFile(path, [
      "# Trader Intuition",
      "- Prefer NQ trend day continuation and session momentum after an open drive.",
      "- Keep paper/demo guardrails strict around drawdown and red-folder blackout windows."
    ].join("\n"));

    const intuition = await loadTraderIntuition({ paths: [path] });

    expect(intuition.loadedPaths).toHaveLength(1);
    expect(intuition.preferredStrategies).toContain("session-momentum");
    expect(intuition.preferredSymbols).toContain("NQ");
    expect(intuition.riskNotes.join(" ")).toMatch(/guardrails/i);
  });

  it("captures structural-flow notes without bypassing gates", async () => {
    const dir = await mkdtemp(join(tmpdir(), "trader-intuition-"));
    const path = join(dir, "founder-notes.md");
    await writeFile(path, [
      "# Founder Strategy Notes",
      "- Study expiry flow, dealer gamma pinning, and COT leveraged fund positioning.",
      "- Keep deflated Sharpe, PBO, drawdown, and longer OOS windows as promotion guardrails.",
      "- Use capitulation tail score and structural flows as research directives, not live permission."
    ].join("\n"));

    const intuition = await loadTraderIntuition({ paths: [path] });

    expect(intuition.preferredStrategies).toEqual(expect.arrayContaining([
      "expiry-flow",
      "gamma-pin",
      "cot-positioning",
      "structural-flows",
      "capitulation-score"
    ]));
    expect(intuition.riskNotes.join(" ")).toMatch(/guardrails/i);
  });
});
