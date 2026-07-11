import { describe, expect, it, afterEach, beforeEach, vi } from "vitest";
import { buildOllamaConfigFromEnv, generate, embed, generateJson } from "../src/llm/ollama.js";

const realFetch = globalThis.fetch;

describe("ollama adapter", () => {
  afterEach(() => {
    globalThis.fetch = realFetch;
    vi.restoreAllMocks();
  });

  it("buildOllamaConfigFromEnv uses sensible defaults", () => {
    const config = buildOllamaConfigFromEnv({});
    expect(config.baseUrl).toBe("http://localhost:11434");
    expect(config.defaultModel).toBe("qwen2.5-coder:14b");
    expect(config.defaultEmbedModel).toBe("nomic-embed-text:latest");
    expect(config.timeoutMs).toBeGreaterThan(0);
  });

  it("buildOllamaConfigFromEnv honours env overrides", () => {
    const config = buildOllamaConfigFromEnv({
      BILL_OLLAMA_BASE_URL: "http://host.docker.internal:11434",
      BILL_OLLAMA_MODEL: "qwen2.5:14b",
      BILL_OLLAMA_EMBED_MODEL: "nomic-embed-text",
      BILL_OLLAMA_TIMEOUT_MS: "30000"
    });
    expect(config.baseUrl).toBe("http://host.docker.internal:11434");
    expect(config.defaultModel).toBe("qwen2.5:14b");
    expect(config.timeoutMs).toBe(30_000);
  });

  it("generate posts the expected body and returns the response", async () => {
    const captured: { url?: string; init?: RequestInit } = {};
    globalThis.fetch = vi.fn(async (url: string | URL, init?: RequestInit) => {
      captured.url = String(url);
      captured.init = init;
      return new Response(
        JSON.stringify({
          response: " hello world ",
          model: "qwen2.5-coder:14b",
          prompt_eval_count: 4,
          eval_count: 3
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }) as unknown as typeof fetch;

    const result = await generate("hi", { temperature: 0, maxTokens: 16 });
    expect(captured.url).toBe("http://localhost:11434/api/generate");
    expect(captured.init?.method).toBe("POST");
    const body = JSON.parse(String(captured.init?.body));
    expect(body).toMatchObject({
      model: "qwen2.5-coder:14b",
      prompt: "hi",
      stream: false,
      options: { temperature: 0, num_predict: 16 }
    });
    expect(result.text).toBe(" hello world ");
    expect(result.promptTokens).toBe(4);
    expect(result.completionTokens).toBe(3);
  });

  it("generateJson parses the model response", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ response: '{"ok":true,"n":3}', model: "m" }), { status: 200 })
    ) as unknown as typeof fetch;
    const { value } = await generateJson<{ ok: boolean; n: number }>("x");
    expect(value).toEqual({ ok: true, n: 3 });
  });

  it("generateJson throws a useful error on bad JSON", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ response: "not-json", model: "m" }), { status: 200 })
    ) as unknown as typeof fetch;
    await expect(generateJson("x")).rejects.toThrow(/unparseable JSON/);
  });

  it("embed returns the vector", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ embedding: [0.1, 0.2, 0.3] }), { status: 200 })
    ) as unknown as typeof fetch;
    const result = await embed("prediction markets");
    expect(result.embedding).toHaveLength(3);
    expect(result.embedding[0]).toBeCloseTo(0.1);
  });

  it("generate surfaces non-2xx responses", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response("model not found", { status: 404 })
    ) as unknown as typeof fetch;
    await expect(generate("x")).rejects.toThrow(/ollama \/api\/generate 404/);
  });
});
