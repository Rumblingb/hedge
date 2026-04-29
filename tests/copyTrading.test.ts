import { describe, expect, it } from "vitest";
import { classifyPredictionDomain, isFounderApprovedPredictionDomain } from "../src/prediction/copyTrading.js";

describe("prediction copy trading domain filters", () => {
  it("treats presidential nomination markets as politics", () => {
    expect(classifyPredictionDomain({
      title: "Who will win the 2028 Republican presidential nomination?",
      slug: "2028-republican-presidential-nomination"
    })).toBe("politics");
  });

  it("keeps presidential nomination markets inside the founder-approved filter", () => {
    expect(isFounderApprovedPredictionDomain(
      "Who will win the 2028 Republican presidential nomination?",
      "2028-republican-presidential-nomination"
    )).toBe(true);
  });
});
