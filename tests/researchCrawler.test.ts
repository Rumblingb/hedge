import { afterEach, describe, expect, it, vi } from "vitest";
import { firecrawlHealthy } from "../src/research/crawler.js";

const realFetch = globalThis.fetch;

describe("research crawler", () => {
  afterEach(() => {
    globalThis.fetch = realFetch;
    vi.restoreAllMocks();
  });

  it("falls back to the plain health endpoint when the authenticated probe fails", async () => {
    globalThis.fetch = vi.fn(async (url: string | URL) => {
      if (String(url) === "https://firecrawl.test/v1/team/credit-usage") {
        return new Response("forbidden", { status: 403 });
      }
      if (String(url) === "https://firecrawl.test/health") {
        return new Response("ok", { status: 200 });
      }
      throw new Error(`unexpected url ${String(url)}`);
    }) as unknown as typeof fetch;

    await expect(firecrawlHealthy({
      firecrawlBaseUrl: "https://firecrawl.test",
      firecrawlApiKey: "test-key",
      userAgent: "test-agent",
      timeoutMs: 1000
    })).resolves.toBe(true);
  });
});
