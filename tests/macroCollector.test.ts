import { describe, expect, it } from "vitest";
import { parseFredObservations } from "../src/research/macro.js";

describe("parseFredObservations", () => {
  it("parses numeric values and ignores blank placeholders", () => {
    const observations = parseFredObservations({
      observations: [
        { date: "2026-04-10", value: "4.33" },
        { date: "2026-04-11", value: "." },
        { date: "2026-04-12", value: 19.2 }
      ]
    });

    expect(observations).toEqual([
      { date: "2026-04-10", value: 4.33 },
      { date: "2026-04-11", value: undefined },
      { date: "2026-04-12", value: 19.2 }
    ]);
  });
});
