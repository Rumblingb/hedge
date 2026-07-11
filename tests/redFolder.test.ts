import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadRedFolderEvents } from "../src/news/redFolder.js";

describe("loadRedFolderEvents", () => {
  it("loads compact red-folder JSON events for strategy lab news gates", async () => {
    const dir = await mkdtemp(join(tmpdir(), "red-folder-"));
    const path = join(dir, "events.json");
    await writeFile(path, JSON.stringify({
      events: [
        {
          symbol: "nq",
          ts: "2026-04-30T14:00:00.000Z",
          direction: "short",
          probability: 0.82,
          impact: "high",
          headline: "FOMC red-folder release"
        },
        { symbol: "", ts: "bad", headline: "" }
      ]
    }));

    const loaded = await loadRedFolderEvents(path);

    expect(loaded.events).toHaveLength(1);
    expect(loaded.events[0]).toMatchObject({
      symbol: "NQ",
      direction: "short",
      impact: "high"
    });
    expect(loaded.warnings[0]).toContain("ignored 1 malformed");
  });
});
