import { writeFileSync } from "node:fs";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockYoutubeCreate, mockExtractStrategies, mockExecFile } = vi.hoisted(() => ({
  mockYoutubeCreate: vi.fn(),
  mockExtractStrategies: vi.fn(),
  mockExecFile: vi.fn()
}));

vi.mock("youtubei.js", () => ({
  Innertube: {
    create: mockYoutubeCreate
  }
}));

vi.mock("@playzone/youtube-transcript/dist/enhanced-api/index.js", () => ({
  EnhancedYouTubeTranscriptApi: class {
    async fetch(): Promise<never> {
      throw new Error("free transcript provider unavailable in test");
    }
  }
}));

vi.mock("node:child_process", () => ({
  execFile: mockExecFile
}));

vi.mock("../src/research/strategyHypotheses.js", async () => {
  const actual = await vi.importActual<typeof import("../src/research/strategyHypotheses.js")>("../src/research/strategyHypotheses.js");
  return {
    ...actual,
    extractStrategyHypothesesFromTranscript: mockExtractStrategies
  };
});

import {
  loadPolicy,
  loadTargets,
  readLatestResearcherRunReport,
  resolveResearcherWorkspacePaths,
  runResearcherPipeline
} from "../src/research/pipeline.js";
import { resolveCorpusPaths } from "../src/research/corpus.js";

const realFetch = globalThis.fetch;
const originalEnv = {
  YOUTUBE_TRANSCRIPT_DEV_API_KEY: process.env.YOUTUBE_TRANSCRIPT_DEV_API_KEY,
  GEMINI_API_KEY: process.env.GEMINI_API_KEY,
  BILL_YT_DLP_PATH: process.env.BILL_YT_DLP_PATH,
  BILL_YOUTUBE_TRANSCRIPT_MODEL: process.env.BILL_YOUTUBE_TRANSCRIPT_MODEL,
  BILL_YOUTUBE_TRANSCRIPT_PROVIDER_TIMEOUT_MS: process.env.BILL_YOUTUBE_TRANSCRIPT_PROVIDER_TIMEOUT_MS,
  BILL_YOUTUBE_TRANSCRIPT_SKIP_FREE: process.env.BILL_YOUTUBE_TRANSCRIPT_SKIP_FREE
};

describe("researcher pipeline", () => {
  afterEach(() => {
    globalThis.fetch = realFetch;
    vi.restoreAllMocks();
    mockYoutubeCreate.mockReset();
    mockExtractStrategies.mockReset();
    mockExecFile.mockReset();
    if (originalEnv.YOUTUBE_TRANSCRIPT_DEV_API_KEY === undefined) {
      delete process.env.YOUTUBE_TRANSCRIPT_DEV_API_KEY;
    } else {
      process.env.YOUTUBE_TRANSCRIPT_DEV_API_KEY = originalEnv.YOUTUBE_TRANSCRIPT_DEV_API_KEY;
    }
    if (originalEnv.GEMINI_API_KEY === undefined) {
      delete process.env.GEMINI_API_KEY;
    } else {
      process.env.GEMINI_API_KEY = originalEnv.GEMINI_API_KEY;
    }
    if (originalEnv.BILL_YT_DLP_PATH === undefined) {
      delete process.env.BILL_YT_DLP_PATH;
    } else {
      process.env.BILL_YT_DLP_PATH = originalEnv.BILL_YT_DLP_PATH;
    }
    if (originalEnv.BILL_YOUTUBE_TRANSCRIPT_MODEL === undefined) {
      delete process.env.BILL_YOUTUBE_TRANSCRIPT_MODEL;
    } else {
      process.env.BILL_YOUTUBE_TRANSCRIPT_MODEL = originalEnv.BILL_YOUTUBE_TRANSCRIPT_MODEL;
    }
    if (originalEnv.BILL_YOUTUBE_TRANSCRIPT_PROVIDER_TIMEOUT_MS === undefined) {
      delete process.env.BILL_YOUTUBE_TRANSCRIPT_PROVIDER_TIMEOUT_MS;
    } else {
      process.env.BILL_YOUTUBE_TRANSCRIPT_PROVIDER_TIMEOUT_MS = originalEnv.BILL_YOUTUBE_TRANSCRIPT_PROVIDER_TIMEOUT_MS;
    }
    if (originalEnv.BILL_YOUTUBE_TRANSCRIPT_SKIP_FREE === undefined) {
      delete process.env.BILL_YOUTUBE_TRANSCRIPT_SKIP_FREE;
    } else {
      process.env.BILL_YOUTUBE_TRANSCRIPT_SKIP_FREE = originalEnv.BILL_YOUTUBE_TRANSCRIPT_SKIP_FREE;
    }
  });

  it("normalizes legacy policy quality keys", async () => {
    const dir = await mkdtemp(join(tmpdir(), "researcher-policy-"));
    const policyPath = join(dir, "policy.json");
    await writeFile(
      policyPath,
      JSON.stringify({
        version: 1,
        budgets: {
          dailyCrawlBudget: 120,
          maxCorpusGb: 2,
          maxConcurrentBrowsers: 3,
          heartbeatMinutes: 30
        },
        quality: {
          minChunkChars: 321,
          maxChunkChars: 1234,
          minhashThreshold: 0.75,
          classifierMinScore: 4,
          judgeTopFraction: 0.1
        },
        allowedDomains: ["docs.firecrawl.dev"],
        llm: {
          generateModel: "qwen2.5-coder:14b",
          embedModel: "nomic-embed-text:latest",
          judgeModel: "qwen2.5-coder:14b",
          baseUrl: "http://localhost:11434"
        },
        eval: {
          evalThreshold: 100,
          goldenPromptsPath: "/tmp/golden-prompts.jsonl"
        }
      }),
      "utf8"
    );

    const policy = await loadPolicy(policyPath);
    expect(policy.quality.minChars).toBe(321);
    expect(policy.quality.maxChars).toBe(1234);
    expect(policy.quality.classifierMinScore).toBe(4);
  });

  it("runs a web collection pass, persists reports, and updates the workspace outbox", async () => {
    const dir = await mkdtemp(join(tmpdir(), "researcher-run-"));
    const workspaceRoot = join(dir, "workspace");
    const policyPath = join(dir, "policy.json");
    const targetsPath = join(dir, "targets.json");
    const latestReportPath = join(dir, "latest-run.json");
    const reportRunsDir = join(dir, "runs");
    const corpusPaths = resolveCorpusPaths(join(dir, "corpus"));
    const html = `
      <html>
        <head><title>Firecrawl Docs</title></head>
        <body>
          <main>
            <h1>Firecrawl Deep Dive</h1>
            <p>${"Prediction market research agents need durable crawling notes. ".repeat(18)}</p>
            <p>${"This page explains how to extract structured markdown from documentation and preserve provenance. ".repeat(14)}</p>
          </main>
        </body>
      </html>
    `;

    await writeFile(
      policyPath,
      JSON.stringify({
        version: 1,
        budgets: {
          dailyCrawlBudget: 10,
          maxCorpusGb: 2,
          maxConcurrentBrowsers: 2,
          heartbeatMinutes: 60
        },
        quality: {
          minChunkChars: 250,
          maxChunkChars: 800,
          minhashThreshold: 0.8,
          classifierMinScore: 3,
          judgeTopFraction: 0.05,
          classifierSample: 400
        },
        allowedDomains: ["docs.firecrawl.dev"],
        llm: {
          generateModel: "qwen2.5-coder:14b",
          embedModel: "nomic-embed-text:latest",
          judgeModel: "qwen2.5-coder:14b",
          baseUrl: "http://localhost:11434"
        },
        eval: {
          evalThreshold: 100,
          goldenPromptsPath: join(dir, "golden-prompts.jsonl")
        }
      }),
      "utf8"
    );

    await writeFile(
      targetsPath,
      JSON.stringify({
        targets: [
          {
            id: "firecrawl-docs",
            kind: "web",
            url: "https://docs.firecrawl.dev",
            priority: 1,
            tags: ["crawler", "docs"]
          }
        ]
      }),
      "utf8"
    );

    globalThis.fetch = vi.fn(async (url: string | URL) => {
      if (String(url) === "https://docs.firecrawl.dev") {
        return new Response(html, {
          status: 200,
          headers: { "Content-Type": "text/html; charset=utf-8" }
        });
      }
      throw new Error(`unexpected url ${String(url)}`);
    }) as unknown as typeof fetch;

    const report = await runResearcherPipeline({
      policyPath,
      targetsPath,
      workspaceRoot,
      latestReportPath,
      reportRunsDir,
      corpusPaths,
      skipJudge: true,
      skipEmbed: true,
      crawlerConfig: {
        userAgent: "test-agent",
        timeoutMs: 1000
      }
    });

    expect(report.targetsSucceeded).toBe(1);
    expect(report.chunksKept).toBeGreaterThan(0);
    expect(report.topKeptTitles[0]).toContain("Firecrawl");

    const latestReport = await readLatestResearcherRunReport(latestReportPath);
    expect(latestReport?.runId).toBe(report.runId);

    const workspace = resolveResearcherWorkspacePaths(workspaceRoot);
    const outbox = await readFile(workspace.outbox, "utf8");
    expect(outbox).toContain(`run ${report.runId}`);
    expect(outbox).toContain("Top kept:");

    const manifest = JSON.parse(await readFile(corpusPaths.manifest, "utf8")) as {
      chunkCount: number;
      lastRunId: string;
    };
    expect(manifest.chunkCount).toBe(report.chunksKept);
    expect(manifest.lastRunId).toBe(report.runId);
  });

  it("treats a fully deduped successful run as healthy rather than broken", async () => {
    const dir = await mkdtemp(join(tmpdir(), "researcher-run-dedup-"));
    const workspaceRoot = join(dir, "workspace");
    const policyPath = join(dir, "policy.json");
    const targetsPath = join(dir, "targets.json");
    const latestReportPath = join(dir, "latest-run.json");
    const reportRunsDir = join(dir, "runs");
    const corpusPaths = resolveCorpusPaths(join(dir, "corpus"));
    const html = `
      <html>
        <head><title>Repeated Docs</title></head>
        <body>
          <main>
            <h1>Repeated Page</h1>
            <p>${"This page is intentionally repeated to exercise dedup handling. ".repeat(20)}</p>
          </main>
        </body>
      </html>
    `;

    await writeFile(
      policyPath,
      JSON.stringify({
        version: 1,
        budgets: {
          dailyCrawlBudget: 10,
          maxCorpusGb: 2,
          maxConcurrentBrowsers: 2,
          heartbeatMinutes: 60
        },
        quality: {
          minChunkChars: 250,
          maxChunkChars: 800
        },
        allowedDomains: ["example.com"],
        llm: {
          generateModel: "qwen2.5-coder:14b",
          embedModel: "nomic-embed-text:latest",
          judgeModel: "qwen2.5-coder:14b",
          baseUrl: "http://localhost:11434"
        },
        eval: {
          evalThreshold: 100,
          goldenPromptsPath: join(dir, "golden-prompts.jsonl")
        }
      }),
      "utf8"
    );

    await writeFile(
      targetsPath,
      JSON.stringify({
        targets: [
          {
            id: "repeated-page",
            kind: "web",
            url: "https://example.com/repeated",
            priority: 1
          }
        ]
      }),
      "utf8"
    );

    globalThis.fetch = vi.fn(async (url: string | URL, init?: RequestInit) => {
      if (String(url) === "http://firecrawl.test/health") {
        return new Response("ok", { status: 200 });
      }
      if (String(url) === "http://firecrawl.test/v2/scrape" && init?.method === "POST") {
        return new Response(JSON.stringify({
          success: true,
          data: {
            markdown: `# Repeated Page\n\n${"This page is intentionally repeated to exercise dedup handling. ".repeat(20)}`,
            metadata: { title: "Repeated Docs", statusCode: 200 }
          }
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response(html, {
        status: 200,
        headers: { "Content-Type": "text/html; charset=utf-8" }
      });
    }) as unknown as typeof fetch;

    const first = await runResearcherPipeline({
      policyPath,
      targetsPath,
      workspaceRoot,
      latestReportPath,
      reportRunsDir,
      corpusPaths,
      skipJudge: true,
      skipEmbed: true,
      crawlerConfig: {
        userAgent: "test-agent",
        timeoutMs: 1000,
        firecrawlBaseUrl: "http://firecrawl.test"
      }
    });
    const second = await runResearcherPipeline({
      policyPath,
      targetsPath,
      workspaceRoot,
      latestReportPath,
      reportRunsDir,
      corpusPaths,
      skipJudge: true,
      skipEmbed: true,
      crawlerConfig: {
        userAgent: "test-agent",
        timeoutMs: 1000,
        firecrawlBaseUrl: "http://firecrawl.test"
      }
    });

    expect(first.chunksKept).toBeGreaterThan(0);
    expect(second.targetsSucceeded).toBe(1);
    expect(second.chunksKept).toBe(0);
    expect(second.chunksCollected).toBe(0);
    expect(second.status).toBe("degraded");
    expect(second.blockers).toContain("Selected researcher targets yielded no novel chunks in the latest run.");
    expect(second.nextAction).toContain("already-covered material");
  });

  it("prefers fresh targets over already covered sources when auto-selecting the next batch", async () => {
    const dir = await mkdtemp(join(tmpdir(), "researcher-target-rotation-"));
    const workspaceRoot = join(dir, "workspace");
    const policyPath = join(dir, "policy.json");
    const targetsPath = join(dir, "targets.json");
    const latestReportPath = join(dir, "latest-run.json");
    const reportRunsDir = join(dir, "runs");
    const corpusPaths = resolveCorpusPaths(join(dir, "corpus"));

    await writeFile(
      policyPath,
      JSON.stringify({
        version: 1,
        budgets: {
          dailyCrawlBudget: 10,
          maxCorpusGb: 2,
          maxConcurrentBrowsers: 2,
          heartbeatMinutes: 60
        },
        quality: {
          minChunkChars: 250,
          maxChunkChars: 800
        },
        allowedDomains: ["example.com"],
        llm: {
          generateModel: "qwen2.5-coder:14b",
          embedModel: "nomic-embed-text:latest",
          judgeModel: "qwen2.5-coder:14b",
          baseUrl: "http://localhost:11434"
        },
        eval: {
          evalThreshold: 100,
          goldenPromptsPath: join(dir, "golden-prompts.jsonl")
        }
      }),
      "utf8"
    );

    await writeFile(
      targetsPath,
      JSON.stringify({
        targets: [
          {
            id: "covered-high",
            kind: "web",
            url: "https://example.com/covered-high",
            priority: 1
          },
          {
            id: "fresh-mid",
            kind: "web",
            url: "https://example.com/fresh-mid",
            priority: 2
          },
          {
            id: "fresh-low",
            kind: "web",
            url: "https://example.com/fresh-low",
            priority: 3
          }
        ]
      }),
      "utf8"
    );

    globalThis.fetch = vi.fn(async (url: string | URL) => {
      const htmlByUrl = new Map<string, string>([
        [
          "https://example.com/covered-high",
          `
            <html>
              <head><title>Covered High</title></head>
              <body>
                <main>
                  <h1>Covered High</h1>
                  <p>${"This target has already been ingested and should not be selected again first. ".repeat(18)}</p>
                </main>
              </body>
            </html>
          `
        ],
        [
          "https://example.com/fresh-mid",
          `
            <html>
              <head><title>Fresh Mid</title></head>
              <body>
                <main>
                  <h1>Fresh Mid</h1>
                  <p>${"This fresh target should be preferred over the covered one during automatic selection. ".repeat(18)}</p>
                </main>
              </body>
            </html>
          `
        ],
        [
          "https://example.com/fresh-low",
          `
            <html>
              <head><title>Fresh Low</title></head>
              <body>
                <main>
                  <h1>Fresh Low</h1>
                  <p>${"This target is also fresh but lower priority than the other uncovered target. ".repeat(18)}</p>
                </main>
              </body>
            </html>
          `
        ]
      ]);
      const html = htmlByUrl.get(String(url));
      if (!html) {
        throw new Error(`unexpected url ${String(url)}`);
      }
      return new Response(html, {
        status: 200,
        headers: { "Content-Type": "text/html; charset=utf-8" }
      });
    }) as unknown as typeof fetch;

    const first = await runResearcherPipeline({
      policyPath,
      targetsPath,
      workspaceRoot,
      latestReportPath,
      reportRunsDir,
      corpusPaths,
      targetIds: ["covered-high"],
      maxTargets: 1,
      skipJudge: true,
      skipEmbed: true,
      crawlerConfig: {
        userAgent: "test-agent",
        timeoutMs: 1000
      }
    });
    const second = await runResearcherPipeline({
      policyPath,
      targetsPath,
      workspaceRoot,
      latestReportPath,
      reportRunsDir,
      corpusPaths,
      maxTargets: 1,
      skipJudge: true,
      skipEmbed: true,
      crawlerConfig: {
        userAgent: "test-agent",
        timeoutMs: 1000
      }
    });

    expect(first.targetResults.map((result) => result.targetId)).toEqual(["covered-high"]);
    expect(first.chunksKept).toBeGreaterThan(0);
    expect(second.targetResults.map((result) => result.targetId)).toEqual(["fresh-mid"]);
    expect(second.chunksKept).toBeGreaterThan(0);
  });

  it("rejects off-topic arxiv chunks when finance targets demand tighter relevance", async () => {
    const dir = await mkdtemp(join(tmpdir(), "researcher-finance-relevance-"));
    const workspaceRoot = join(dir, "workspace");
    const policyPath = join(dir, "policy.json");
    const targetsPath = join(dir, "targets.json");
    const latestReportPath = join(dir, "latest-run.json");
    const reportRunsDir = join(dir, "runs");
    const corpusPaths = resolveCorpusPaths(join(dir, "corpus"));

    await writeFile(
      policyPath,
      JSON.stringify({
        version: 1,
        budgets: {
          dailyCrawlBudget: 10,
          maxCorpusGb: 2,
          maxConcurrentBrowsers: 2,
          heartbeatMinutes: 60
        },
        quality: {
          minChunkChars: 250,
          maxChunkChars: 1200,
          classifierMinScore: 4
        },
        allowedDomains: [],
        llm: {
          generateModel: "qwen2.5-coder:14b",
          embedModel: "nomic-embed-text:latest",
          judgeModel: "qwen2.5-coder:14b",
          baseUrl: "http://localhost:11434"
        },
        eval: {
          evalThreshold: 100,
          goldenPromptsPath: join(dir, "golden-prompts.jsonl")
        }
      }),
      "utf8"
    );

    await writeFile(
      targetsPath,
      JSON.stringify({
        targets: [
          {
            id: "arxiv-walk-forward-overfitting",
            kind: "arxiv-query",
            query: "walk-forward overfitting prediction markets",
            priority: 1,
            limit: 1,
            tags: ["prediction", "oos"]
          }
        ]
      }),
      "utf8"
    );

    globalThis.fetch = vi.fn(async (url: string | URL) => {
      if (!String(url).startsWith("http://export.arxiv.org/api/query?")) {
        throw new Error(`unexpected url ${String(url)}`);
      }
      return new Response(
        `<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/1234.5678</id>
            <published>2026-04-24T00:00:00Z</published>
            <title>Dataset Curation for Large Language Model Pretraining</title>
            <summary>${"This paper studies dataset curation, synthetic data generation, and crawler orchestration for large language model pretraining pipelines with benchmark analysis and evaluation details. ".repeat(8)}</summary>
            <author><name>Researcher One</name></author>
          </entry>
        </feed>`,
        {
          status: 200,
          headers: { "Content-Type": "application/atom+xml; charset=utf-8" }
        }
      );
    }) as unknown as typeof fetch;

    const report = await runResearcherPipeline({
      policyPath,
      targetsPath,
      workspaceRoot,
      latestReportPath,
      reportRunsDir,
      corpusPaths,
      skipJudge: true,
      skipEmbed: true,
      crawlerConfig: {
        userAgent: "test-agent",
        timeoutMs: 1000
      }
    });

    expect(report.targetsSucceeded).toBe(1);
    expect(report.chunksCollected).toBe(0);
    expect(report.chunksKept).toBe(0);
    expect(report.status).toBe("degraded");
    expect(report.blockers).toContain("Selected researcher targets yielded no novel chunks in the latest run.");
    expect(report.targetResults[0]?.targetId).toBe("arxiv-walk-forward-overfitting");
    expect(report.targetResults[0]?.kept).toBe(0);
    expect(report.targetResults[0]?.rejected).toBe(0);
  });

  it("resolves default workspace policy and targets from env-backed OpenClaw paths", async () => {
    const dir = await mkdtemp(join(tmpdir(), "researcher-defaults-"));
    const workspaceRoot = join(dir, ".openclaw", "workspace-researcher");
    const policyPath = join(workspaceRoot, "policy.json");
    const targetsPath = join(workspaceRoot, "targets.json");
    await mkdir(workspaceRoot, { recursive: true });
    await writeFile(
      policyPath,
      JSON.stringify({
        version: 1,
        budgets: {
          dailyCrawlBudget: 25,
          maxCorpusGb: 1,
          maxConcurrentBrowsers: 1,
          heartbeatMinutes: 30
        },
        quality: {
          minChunkChars: 250,
          maxChunkChars: 900
        },
        allowedDomains: ["example.com"],
        llm: {
          generateModel: "qwen2.5-coder:14b",
          embedModel: "nomic-embed-text:latest",
          judgeModel: "qwen2.5-coder:14b",
          baseUrl: "http://localhost:11434"
        },
        eval: {
          evalThreshold: 50
        }
      }),
      "utf8"
    );
    await writeFile(
      targetsPath,
      JSON.stringify({
        targets: [
          { id: "t1", kind: "web", url: "https://example.com" },
          { id: "t2", kind: "web", url: "https://example.com/disabled", enabled: false }
        ]
      }),
      "utf8"
    );

    const env = {
      ...process.env,
      OPENCLAW_HOME: join(dir, ".openclaw")
    };
    const policy = await loadPolicy(undefined, env);
    const workspace = resolveResearcherWorkspacePaths(undefined, env);

    expect(policy.budgets.dailyCrawlBudget).toBe(25);
    expect(policy.eval.goldenPromptsPath).toBe(join(workspaceRoot, "eval", "golden-prompts.jsonl"));
    expect(workspace.root).toBe(workspaceRoot);
    await expect(loadTargets(undefined, env)).resolves.toHaveLength(1);
  });

  it("ingests youtube transcript targets into the researcher lane and emits strategy artifacts without persisting raw transcripts", async () => {
    const dir = await mkdtemp(join(tmpdir(), "researcher-youtube-"));
    const workspaceRoot = join(dir, "workspace");
    const policyPath = join(dir, "policy.json");
    const targetsPath = join(dir, "targets.json");
    const latestReportPath = join(dir, "latest-run.json");
    const reportRunsDir = join(dir, "runs");
    const corpusPaths = resolveCorpusPaths(join(dir, "corpus"));
    process.env.YOUTUBE_TRANSCRIPT_DEV_API_KEY = "test-transcript-key";
    process.env.BILL_YOUTUBE_TRANSCRIPT_PROVIDER_TIMEOUT_MS = "20";
    process.env.BILL_YOUTUBE_TRANSCRIPT_SKIP_FREE = "1";
    delete process.env.GEMINI_API_KEY;
    delete process.env.BILL_YT_DLP_PATH;

    await writeFile(
      policyPath,
      JSON.stringify({
        version: 1,
        budgets: {
          dailyCrawlBudget: 10,
          maxCorpusGb: 2,
          maxConcurrentBrowsers: 2,
          heartbeatMinutes: 60
        },
        quality: {
          minChunkChars: 200,
          maxChunkChars: 1200
        },
        allowedDomains: ["youtube.com", "www.youtube.com"],
        llm: {
          generateModel: "qwen2.5-coder:14b",
          embedModel: "nomic-embed-text:latest",
          judgeModel: "qwen2.5-coder:14b",
          baseUrl: "http://localhost:11434"
        },
        eval: {
          evalThreshold: 100,
          goldenPromptsPath: join(dir, "golden-prompts.jsonl")
        }
      }),
      "utf8"
    );

    await writeFile(
      targetsPath,
      JSON.stringify({
        targets: [
          {
            id: "ict-youtube-query",
            kind: "youtube-transcript",
            query: "ict trading futures",
            limit: 1,
            tags: ["futures-core", "ict", "order-flow"]
          }
        ]
      }),
      "utf8"
    );

    mockYoutubeCreate.mockResolvedValue({
      search: vi.fn(async () => ({
        videos: [
          {
            id: "video-123",
            title: { text: "ICT NQ futures setup" },
            author: { name: "ICT Desk" }
          }
        ],
        has_continuation: false
      }))
    });

    mockExtractStrategies.mockResolvedValue({
      provider: "cloud",
      model: "test-cloud-model",
      hypotheses: [
        {
          id: "ict-fvg-hypothesis",
          title: "ICT fair value gap continuation",
          market: "futures",
          symbols: ["NQ"],
          timeframes: ["5m"],
          sessions: ["New York AM"],
          setupSummary: "Trade continuation after displacement and fair value gap retest.",
          biasRules: ["Require directional displacement before entry."],
          entryRules: ["Enter on first fair value gap retest."],
          stopRules: ["Stop beyond the displacement origin."],
          targetRules: ["Target prior buy-side liquidity."],
          riskRules: ["Stand down after one invalidation."],
          confluence: ["Session high sweep", "fair value gap"],
          invalidationRules: ["No trade if displacement is weak."],
          evidence: ["fair value gap retest", "buy-side liquidity"],
          automationReadiness: "medium",
          confidence: 0.74,
          sourceTargetIds: ["ict-youtube-query"],
          sourceVideoIds: ["video-123"],
          sourceVideoTitles: ["ICT NQ futures setup"],
          sourceChannels: ["ICT Desk"],
          sourceUrls: ["https://www.youtube.com/watch?v=video-123"]
        }
      ]
    });

    globalThis.fetch = vi.fn(async (url: string | URL) => {
      if (String(url) === "https://youtubetranscript.dev/api/v2/transcribe") {
        return new Response(JSON.stringify({
          data: {
            language: "en",
            transcript: [
              {
                start: 0,
                duration: 4,
                text: "Wait for displacement and confirm the move is backed by aggressive delivery before looking for continuation."
              },
              {
                start: 4,
                duration: 5,
                text: "Enter at the fair value gap retest only after the sweep, keep risk tight beyond the displacement origin, and target the next liquidity pool."
              }
            ]
          }
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      throw new Error(`unexpected url ${String(url)}`);
    }) as unknown as typeof fetch;

    const report = await runResearcherPipeline({
      policyPath,
      targetsPath,
      workspaceRoot,
      latestReportPath,
      reportRunsDir,
      corpusPaths,
      skipJudge: true,
      skipEmbed: true,
      crawlerConfig: {
        userAgent: "test-agent",
        timeoutMs: 1000
      }
    });

    expect(report.targetsSucceeded).toBe(1);
    expect(report.chunksKept).toBeGreaterThan(0);
    expect(report.strategyHypothesesCount).toBe(1);
    expect(report.topStrategyHypotheses).toContain("ICT fair value gap continuation");
    expect(report.transcriptArtifactsDeleted).toBe(1);
    expect(report.targetResults[0]?.videosProcessed).toBe(1);
    expect(report.strategyArtifactPath).toBeTruthy();

    const latestArtifact = JSON.parse(await readFile(report.strategyArtifactPath!, "utf8")) as {
      count: number;
      hypotheses: Array<{ title: string }>;
    };
    expect(latestArtifact.count).toBe(1);
    expect(latestArtifact.hypotheses[0]?.title).toBe("ICT fair value gap continuation");

    const corpusRaw = await readFile(corpusPaths.chunksJsonl, "utf8");
    expect(corpusRaw).toContain("Strategy hypothesis: ICT fair value gap continuation");
    expect(corpusRaw).toContain("Entry rules: Enter on first fair value gap retest.");
    expect(corpusRaw).not.toContain("Wait for displacement and confirm the move is backed by aggressive delivery");

    const workspace = resolveResearcherWorkspacePaths(workspaceRoot);
    const outbox = await readFile(workspace.outbox, "utf8");
    expect(outbox).toContain("Strategy feed:");
  });

  it("falls back to yt-dlp plus Gemini audio transcription when captions are unavailable", async () => {
    const dir = await mkdtemp(join(tmpdir(), "researcher-youtube-gemini-"));
    const workspaceRoot = join(dir, "workspace");
    const policyPath = join(dir, "policy.json");
    const targetsPath = join(dir, "targets.json");
    const latestReportPath = join(dir, "latest-run.json");
    const reportRunsDir = join(dir, "runs");
    const corpusPaths = resolveCorpusPaths(join(dir, "corpus"));
    const fakeToolDir = await mkdtemp(join(tmpdir(), "researcher-youtube-tools-"));
    const fakeYtDlpPath = join(fakeToolDir, "yt-dlp");

    process.env.GEMINI_API_KEY = "test-gemini-key";
    process.env.BILL_YT_DLP_PATH = fakeYtDlpPath;
    process.env.BILL_YOUTUBE_TRANSCRIPT_MODEL = "gemini-test";
    delete process.env.YOUTUBE_TRANSCRIPT_DEV_API_KEY;
    writeFileSync(fakeYtDlpPath, "#!/bin/sh\nexit 0\n", "utf8");

    await writeFile(
      policyPath,
      JSON.stringify({
        version: 1,
        budgets: {
          dailyCrawlBudget: 10,
          maxCorpusGb: 2,
          maxConcurrentBrowsers: 2,
          heartbeatMinutes: 60
        },
        quality: {
          minChunkChars: 200,
          maxChunkChars: 1200
        },
        allowedDomains: ["youtube.com", "www.youtube.com"],
        llm: {
          generateModel: "qwen2.5-coder:14b",
          embedModel: "nomic-embed-text:latest",
          judgeModel: "qwen2.5-coder:14b",
          baseUrl: "http://localhost:11434"
        },
        eval: {
          evalThreshold: 100,
          goldenPromptsPath: join(dir, "golden-prompts.jsonl")
        }
      }),
      "utf8"
    );

    await writeFile(
      targetsPath,
      JSON.stringify({
        targets: [
          {
            id: "ict-youtube-audio",
            kind: "youtube-transcript",
            videos: ["video-456"],
            tags: ["futures-core", "ict"]
          }
        ]
      }),
      "utf8"
    );

    mockYoutubeCreate.mockResolvedValue({
      getBasicInfo: vi.fn(async () => ({
        basic_info: {
          title: "Gemini fallback setup",
          author: "ICT Desk"
        }
      }))
    });

    mockExtractStrategies.mockResolvedValue({
      provider: "cloud",
      model: "test-cloud-model",
      hypotheses: [
        {
          id: "ict-fallback-hypothesis",
          title: "Gemini fallback continuation",
          market: "futures",
          symbols: ["NQ"],
          timeframes: ["5m"],
          sessions: ["New York AM"],
          setupSummary: "Use Gemini fallback transcripts when free captions fail.",
          biasRules: ["Bias toward displacement with confirmation."],
          entryRules: ["Enter after retest."],
          stopRules: ["Stop beyond origin."],
          targetRules: ["Target liquidity."],
          riskRules: ["Stand down after invalidation."],
          confluence: ["displacement", "liquidity"],
          invalidationRules: ["No trade without displacement."],
          evidence: ["Gemini fallback transcript"],
          automationReadiness: "medium",
          confidence: 0.68,
          sourceTargetIds: ["ict-youtube-audio"],
          sourceVideoIds: ["video-456"],
          sourceVideoTitles: ["Gemini fallback setup"],
          sourceChannels: ["ICT Desk"],
          sourceUrls: ["https://www.youtube.com/watch?v=video-456"]
        }
      ]
    });

    mockExecFile.mockImplementation((
      file: string,
      args: string[],
      optionsOrCallback: unknown,
      maybeCallback?: (error: Error | null, stdout?: string, stderr?: string) => void
    ) => {
      const callback = typeof optionsOrCallback === "function"
        ? optionsOrCallback as (error: Error | null, stdout?: string, stderr?: string) => void
        : maybeCallback as (error: Error | null, stdout?: string, stderr?: string) => void;
      if (args.length === 1 && (args[0] === "--version" || args[0] === "-version")) {
        callback(null, "2026.03.17", "");
        return {} as any;
      }
      if (file.includes("yt-dlp")) {
        const outputIndex = args.findIndex((arg) => arg === "--output");
        const outputPattern = outputIndex >= 0 ? args[outputIndex + 1] : "";
        const outputPath = outputPattern.replace("%(id)s", "video-456").replace("%(ext)s", "mp3");
        writeFileSync(outputPath, "raw-audio", "utf8");
        callback(null, "", "");
        return {} as any;
      }
      if (file.includes("ffmpeg")) {
        const outputPath = args[args.length - 1]!;
        writeFileSync(outputPath, "optimized-audio", "utf8");
        callback(null, "", "");
        return {} as any;
      }
      callback(new Error(`unexpected execFile call: ${file}`));
      return {} as any;
    });

    globalThis.fetch = vi.fn(async (url: string | URL) => {
      const asString = String(url);
      if (asString === "https://www.youtube.com/watch?v=video-456") {
        return new Response("<html><body>no captions</body></html>", { status: 200 });
      }
      if (asString.startsWith("https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent")) {
        return new Response(JSON.stringify({
          candidates: [
            {
              content: {
                parts: [
                  {
                    text: JSON.stringify({
                      language: "en",
                      segments: [
                        {
                          start: 0,
                          duration: 24,
                          text: "Wait for displacement before entering the fair value gap retest."
                        },
                        {
                          start: 24,
                          duration: 21,
                          text: "Target the next liquidity pool and keep risk beyond the origin."
                        }
                      ]
                    })
                  }
                ]
              }
            }
          ]
        }), { status: 200 });
      }
      throw new Error(`unexpected url ${asString}`);
    }) as unknown as typeof fetch;

    const report = await runResearcherPipeline({
      policyPath,
      targetsPath,
      workspaceRoot,
      latestReportPath,
      reportRunsDir,
      corpusPaths,
      skipJudge: true,
      skipEmbed: true,
      crawlerConfig: {
        userAgent: "test-agent",
        timeoutMs: 1000
      }
    });

    expect(report.targetsSucceeded).toBe(1);
    expect(report.chunksKept).toBeGreaterThan(0);
    expect(report.strategyHypothesesCount).toBe(1);
    expect(report.transcriptArtifactsDeleted).toBe(1);
    expect(report.targetResults[0]?.videosProcessed).toBe(1);

    const corpusRaw = await readFile(corpusPaths.chunksJsonl, "utf8");
    expect(corpusRaw).toContain("Strategy hypothesis: Gemini fallback continuation");
    expect(corpusRaw).toContain("Use Gemini fallback transcripts when free captions fail.");
    expect(corpusRaw).not.toContain("Wait for displacement before entering the fair value gap retest.");
  });
});
