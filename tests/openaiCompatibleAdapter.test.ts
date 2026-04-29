import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  buildOpenAiCompatibleConfigFromEnv,
  generate,
  generateJson,
  listModels
} from "../src/llm/openaiCompatible.js";

const realFetch = globalThis.fetch;
const originalBudgetLimit = process.env.BILL_MAX_CLOUD_REVIEWS_PER_DAY;
const originalBudgetLedgerPath = process.env.BILL_CLOUD_BUDGET_LEDGER_PATH;

describe("openai-compatible adapter", () => {
  afterEach(() => {
    globalThis.fetch = realFetch;
    if (originalBudgetLimit == null) {
      delete process.env.BILL_MAX_CLOUD_REVIEWS_PER_DAY;
    } else {
      process.env.BILL_MAX_CLOUD_REVIEWS_PER_DAY = originalBudgetLimit;
    }
    if (originalBudgetLedgerPath == null) {
      delete process.env.BILL_CLOUD_BUDGET_LEDGER_PATH;
    } else {
      process.env.BILL_CLOUD_BUDGET_LEDGER_PATH = originalBudgetLedgerPath;
    }
    vi.restoreAllMocks();
  });

  it("buildOpenAiCompatibleConfigFromEnv uses OpenRouter defaults", () => {
    const config = buildOpenAiCompatibleConfigFromEnv({});
    expect(config.provider).toBe("openrouter");
    expect(config.baseUrl).toBe("https://openrouter.ai/api/v1");
    expect(config.defaultModel).toBe("deepseek/deepseek-v3.2");
    expect(config.timeoutMs).toBeGreaterThan(0);
  });

  it("buildOpenAiCompatibleConfigFromEnv honours overrides", () => {
    const config = buildOpenAiCompatibleConfigFromEnv({
      BILL_CLOUD_PROVIDER: "custom-cloud",
      BILL_CLOUD_BASE_URL: "https://example.test/v1/",
      BILL_CLOUD_API_KEY: "secret",
      BILL_CLOUD_REVIEW_MODEL: "moonshotai/kimi-k2-thinking",
      BILL_CLOUD_TIMEOUT_MS: "45000"
    });
    expect(config.provider).toBe("custom-cloud");
    expect(config.baseUrl).toBe("https://example.test/v1");
    expect(config.apiKey).toBe("secret");
    expect(config.defaultModel).toBe("moonshotai/kimi-k2-thinking");
    expect(config.timeoutMs).toBe(45_000);
  });

  it("generate posts an OpenAI-compatible chat request", async () => {
    delete process.env.BILL_MAX_CLOUD_REVIEWS_PER_DAY;
    const captured: { url?: string; init?: RequestInit } = {};
    globalThis.fetch = vi.fn(async (url: string | URL, init?: RequestInit) => {
      captured.url = String(url);
      captured.init = init;
      return new Response(
        JSON.stringify({
          model: "moonshotai/kimi-k2.5",
          choices: [{ message: { content: " ok " } }],
          usage: { prompt_tokens: 4, completion_tokens: 1 }
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as unknown as typeof fetch;

    const result = await generate("hi", { temperature: 0, maxTokens: 16 }, {
      provider: "nvidia-nim",
      baseUrl: "https://integrate.api.nvidia.com/v1",
      apiKey: "secret",
      defaultModel: "moonshotai/kimi-k2.5",
      timeoutMs: 30_000
    });

    expect(captured.url).toBe("https://integrate.api.nvidia.com/v1/chat/completions");
    expect(captured.init?.method).toBe("POST");
    expect(captured.init?.headers).toMatchObject({
      Authorization: "Bearer secret",
      "Content-Type": "application/json"
    });
    expect(JSON.parse(String(captured.init?.body))).toMatchObject({
      model: "moonshotai/kimi-k2.5",
      temperature: 0,
      max_tokens: 16,
      messages: [{ role: "user", content: "hi" }]
    });
    expect(result.text).toBe(" ok ");
    expect(result.promptTokens).toBe(4);
    expect(result.completionTokens).toBe(1);
  });

  it("generateJson parses JSON replies", async () => {
    delete process.env.BILL_MAX_CLOUD_REVIEWS_PER_DAY;
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          model: "moonshotai/kimi-k2.5",
          choices: [{ message: { content: "{\"ok\":true}" } }]
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    const { value } = await generateJson<{ ok: boolean }>("x", {}, {
      provider: "nvidia-nim",
      baseUrl: "https://integrate.api.nvidia.com/v1",
      apiKey: "secret",
      defaultModel: "moonshotai/kimi-k2.5",
      timeoutMs: 30_000
    });
    expect(value).toEqual({ ok: true });
  });

  it("listModels reads OpenAI-compatible model lists", async () => {
    delete process.env.BILL_MAX_CLOUD_REVIEWS_PER_DAY;
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          data: [
            { id: "moonshotai/kimi-k2.5", owned_by: "moonshotai" },
            { id: "nvidia/nv-embed-v1", owned_by: "nvidia" }
          ]
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    const result = await listModels({
      provider: "nvidia-nim",
      baseUrl: "https://integrate.api.nvidia.com/v1",
      apiKey: "secret",
      defaultModel: "moonshotai/kimi-k2.5",
      timeoutMs: 30_000
    });
    expect(result).toEqual([
      { id: "moonshotai/kimi-k2.5", ownedBy: "moonshotai" },
      { id: "nvidia/nv-embed-v1", ownedBy: "nvidia" }
    ]);
  });

  it("generate fails clearly when no key is configured", async () => {
    delete process.env.BILL_MAX_CLOUD_REVIEWS_PER_DAY;
    await expect(generate("hi", {}, {
      provider: "nvidia-nim",
      baseUrl: "https://integrate.api.nvidia.com/v1",
      defaultModel: "moonshotai/kimi-k2.5",
      timeoutMs: 30_000
    })).rejects.toThrow(/requires BILL_CLOUD_API_KEY, NVIDIA_NIM_API_KEY, or NVIDIA_API_KEY/);
  });

  it("enforces a persistent daily cloud request budget", async () => {
    const tempDir = mkdtempSync(join(tmpdir(), "bill-cloud-budget-"));
    const ledgerPath = join(tempDir, "ledger.json");
    process.env.BILL_MAX_CLOUD_REVIEWS_PER_DAY = "1";
    process.env.BILL_CLOUD_BUDGET_LEDGER_PATH = ledgerPath;
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          model: "moonshotai/kimi-k2.5",
          choices: [{ message: { content: "ok" } }],
          usage: { prompt_tokens: 7, completion_tokens: 2 }
        }),
        { status: 200 }
      )
    ) as unknown as typeof fetch;

    await generate("first", {}, {
      provider: "nvidia-nim",
      baseUrl: "https://integrate.api.nvidia.com/v1",
      apiKey: "secret",
      defaultModel: "moonshotai/kimi-k2.5",
      timeoutMs: 30_000
    });

    await expect(generate("second", {}, {
      provider: "nvidia-nim",
      baseUrl: "https://integrate.api.nvidia.com/v1",
      apiKey: "secret",
      defaultModel: "moonshotai/kimi-k2.5",
      timeoutMs: 30_000
    })).rejects.toThrow(/cloud budget exhausted/);

    const ledger = JSON.parse(readFileSync(ledgerPath, "utf8"));
    expect(ledger.requests).toBe(1);
    expect(ledger.promptTokens).toBe(7);
    expect(ledger.completionTokens).toBe(2);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    rmSync(tempDir, { recursive: true, force: true });
  });
});
