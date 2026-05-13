import { describe, expect, it } from "vitest";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveMarketDataPath, resolveRepoPathFromRoot, resolveRuntimeRepoRoot } from "../src/utils/runtimePaths.js";

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

  it("falls back to cold HDD data roots for missing hot CSV files", () => {
    const fallbackRoot = mkdtempSync(join(tmpdir(), "bill-data-free-"));
    const fileName = "ALL-6MARKETS-1m-90d-normalized.csv";
    const fallbackPath = join(fallbackRoot, fileName);
    writeFileSync(fallbackPath, "symbol,ts,open,high,low,close,volume\n", "utf8");

    try {
      const hotPath = resolve(dirname(fileURLToPath(import.meta.url)), "..", "data/free", fileName);
      if (existsSync(hotPath)) {
        throw new Error(`Test fixture unexpectedly exists at ${hotPath}`);
      }

      const resolvedPath = resolveMarketDataPath({
        importMetaUrl: import.meta.url,
        cwd: "/tmp/nonexistent-bill-cwd",
        path: `data/free/${fileName}`,
        env: {
          BILL_DATA_FREE_FALLBACK_DIR: fallbackRoot
        } as NodeJS.ProcessEnv
      });

      expect(resolvedPath).toBe(fallbackPath);
    } finally {
      rmSync(fallbackRoot, { recursive: true, force: true });
    }
  });
});
