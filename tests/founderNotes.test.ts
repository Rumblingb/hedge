import { mkdtemp, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { buildFounderNotesIntake } from "../src/research/founderNotes.js";

describe("founder notes intake", () => {
  it("extracts structural strategy directives from notes text", async () => {
    const dir = await mkdtemp(join(tmpdir(), "founder-notes-"));
    const notePath = join(dir, "notes.txt");
    await writeFile(notePath, [
      "Tail Score = VIX backwardation plus COT leveraged fund shorts.",
      "Quarterly futures roll front month/back month spread.",
      "OPEX Friday gamma pin with max pain and zero-gamma.",
      "Post-news silence after 2.5x ATR spike."
    ].join("\n"), "utf8");

    const report = await buildFounderNotesIntake({
      sourcePaths: [notePath],
      outputPath: join(dir, "out.json"),
      now: () => "2026-05-06T15:30:00.000Z"
    });

    expect(report.directives.map((directive) => directive.id)).toContain("tail-score-risk-gate");
    expect(report.directives.map((directive) => directive.id)).toContain("quarterly-futures-roll-spread");
    expect(report.directives.map((directive) => directive.id)).toContain("opex-gamma-pin");
    expect(report.directives.map((directive) => directive.id)).toContain("post-news-settlement");
    expect(report.priorityOrder[0]).toBe("tail-score-risk-gate");
  });
});
