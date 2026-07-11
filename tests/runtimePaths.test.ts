import { describe, expect, it } from "vitest";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveRepoPathFromRoot, resolveRuntimeRepoRoot } from "../src/utils/runtimePaths.js";

describe("runtime path resolution", () => {
  it("falls back to the module repo root when cwd is outside the repo", () => {
    const expectedRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
    const resolvedRoot = resolveRuntimeRepoRoot({
      importMetaUrl: import.meta.url,
      cwd: "/tmp/nonexistent-bill-cwd"
    });

    expect(resolvedRoot).toBe(expectedRoot);
  });

  it("resolves repo-relative artifacts against the detected repo root", () => {
    const expectedPath = resolve(dirname(fileURLToPath(import.meta.url)), "..", ".rumbling-hedge/state/prediction-review.latest.json");
    const resolvedPath = resolveRepoPathFromRoot({
      importMetaUrl: import.meta.url,
      cwd: "/tmp/nonexistent-bill-cwd",
      path: ".rumbling-hedge/state/prediction-review.latest.json"
    });

    expect(resolvedPath).toBe(expectedPath);
  });
});
