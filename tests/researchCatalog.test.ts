import { describe, expect, it } from "vitest";
import type { ResearchCatalog } from "../src/research/collector.js";
import { buildResearchCatalogReport } from "../src/research/collector.js";

describe("research catalog report", () => {
  it("summarizes keep/discard counts", () => {
    const catalog: ResearchCatalog = {
      command: "research-agent-collect",
      timestamp: "2026-04-15T00:00:00.000Z",
      catalogPath: "/tmp/catalog.json",
      items: [
        {
          id: "paper:arxiv:one",
          kind: "paper",
          source: "arxiv",
          title: "One",
          location: "/tmp/one",
          fetchedAt: "2026-04-15T00:00:00.000Z",
          status: "keep",
          reason: "relevant",
          tags: ["paper"],
          summary: "summary",
          metadata: {}
        },
        {
          id: "local:bill-runtime:two",
          kind: "local-artifact",
          source: "bill-runtime",
          title: "Two",
          location: "/tmp/two",
          fetchedAt: "2026-04-15T00:00:00.000Z",
          status: "discard",
          reason: "placeholder",
          tags: ["bill"],
          summary: "summary",
          metadata: {}
        }
      ]
    };

    const report = buildResearchCatalogReport(catalog);
    expect(report.total).toBe(2);
    expect(report.byStatus.keep).toBe(1);
    expect(report.byStatus.discard).toBe(1);
    expect(report.byKind.paper).toBe(1);
    expect(report.byKind["local-artifact"]).toBe(1);
    expect(report.keptTop10).toHaveLength(1);
  });
});
