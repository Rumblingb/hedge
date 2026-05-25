import { describe, expect, it } from "vitest";
import { categorizeWorktreePath, parseGitWorktreeList } from "../src/engine/worktreeConsolidation.js";

describe("worktree consolidation", () => {
  it("parses git worktree porcelain output", () => {
    const parsed = parseGitWorktreeList([
      "worktree /Users/brain/hedge",
      "HEAD abc123",
      "branch refs/heads/master",
      "",
      "worktree /Users/brain/worktrees/hedge-goal-live",
      "HEAD def456",
      "branch refs/heads/codex/goal-live-market-readiness"
    ].join("\n"));

    expect(parsed).toEqual([
      { path: "/Users/brain/hedge", head: "abc123", branch: "master" },
      { path: "/Users/brain/worktrees/hedge-goal-live", head: "def456", branch: "codex/goal-live-market-readiness" }
    ]);
  });

  it("classifies dirty files into intake lanes", () => {
    expect(categorizeWorktreePath("src/engine/riskPolicyGuard.ts")).toBe("governance-risk");
    expect(categorizeWorktreePath("src/strategies/openingRangeReversal.ts")).toBe("strategy-research");
    expect(categorizeWorktreePath("data/free/ALL-6MARKETS-1m-30d.csv")).toBe("data");
    expect(categorizeWorktreePath("src/live/demoExecution.ts")).toBe("execution-live");
    expect(categorizeWorktreePath("external/qlib/README.md")).toBe("external-vendor");
    expect(categorizeWorktreePath("package-lock.json")).toBe("dependencies");
  });
});
