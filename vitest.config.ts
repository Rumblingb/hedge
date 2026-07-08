import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    fileParallelism: false,
    exclude: [
      "**/node_modules/**",
      "**/node_modules.broken/**",
      "**/.git/**",
      "**/.rumbling-hedge/**",
      "**/rumbling-hedge-cold/**",
      "**/research-repos/**",
      "**/dist/**",
      // kanban t_b9133e83 (2026-07-07): skip abandoned agent/Codex worktrees
      // so orphaned worktree tests (e.g. .claude/worktrees/agent-*/tests/research.test.ts)
      // do not poison the main `npm test` / clearance-evidence suite.
      "**/.claude/**",
      "**/.codex/**"
    ]
  }
});
