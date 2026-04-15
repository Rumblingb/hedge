/**
 * Thin Ollama adapter. Every agent (Bill, Researcher, Hermes) uses this for
 * local inference instead of rolling their own fetch code. Keep the surface
 * small on purpose: `generate`, `generateJson`, `embed`. Add features only
 * when a caller actually needs them.
 */

export interface OllamaConfig {
  baseUrl: string;
  defaultModel: string;
  defaultEmbedModel: string;
  timeoutMs: number;
}

export function buildOllamaConfigFromEnv(env: NodeJS.ProcessEnv = process.env): OllamaConfig {
  const timeoutRaw = Number.parseInt(env.BILL_OLLAMA_TIMEOUT_MS ?? "120000", 10);
  return {
    baseUrl: env.BILL_OLLAMA_BASE_URL ?? env.OLLAMA_BASE_URL ?? "http://localhost:11434",
    defaultModel: env.BILL_OLLAMA_MODEL ?? "qwen2.5-coder:14b",
    defaultEmbedModel: env.BILL_OLLAMA_EMBED_MODEL ?? "nomic-embed-text:latest",
    timeoutMs: Number.isFinite(timeoutRaw) && timeoutRaw > 0 ? timeoutRaw : 120_000
  };
}

export interface GenerateOptions {
  model?: string;
  system?: string;
  temperature?: number;
  maxTokens?: number;
  stop?: string[];
  format?: "json";
  signal?: AbortSignal;
}

export interface GenerateResult {
  text: string;
  model: string;
  promptTokens?: number;
  completionTokens?: number;
  durationMs: number;
}

export async function generate(
  prompt: string,
  options: GenerateOptions = {},
  config: OllamaConfig = buildOllamaConfigFromEnv()
): Promise<GenerateResult> {
  const body: Record<string, unknown> = {
    model: options.model ?? config.defaultModel,
    prompt,
    stream: false,
    options: {
      temperature: options.temperature ?? 0.2,
      num_predict: options.maxTokens ?? 1024,
      stop: options.stop
    }
  };
  if (options.system) body.system = options.system;
  if (options.format === "json") body.format = "json";

  const controller = new AbortController();
  const linked = options.signal
    ? linkAbort(options.signal, controller)
    : undefined;
  const timer = setTimeout(() => controller.abort(new Error("ollama-timeout")), config.timeoutMs);
  const started = Date.now();
  try {
    const res = await fetch(`${config.baseUrl}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal
    });
    if (!res.ok) {
      throw new Error(`ollama /api/generate ${res.status}: ${await res.text().catch(() => "")}`);
    }
    const json = (await res.json()) as {
      response: string;
      model: string;
      prompt_eval_count?: number;
      eval_count?: number;
    };
    return {
      text: json.response ?? "",
      model: json.model,
      promptTokens: json.prompt_eval_count,
      completionTokens: json.eval_count,
      durationMs: Date.now() - started
    };
  } finally {
    clearTimeout(timer);
    linked?.dispose();
  }
}

export async function generateJson<T = unknown>(
  prompt: string,
  options: Omit<GenerateOptions, "format"> = {},
  config: OllamaConfig = buildOllamaConfigFromEnv()
): Promise<{ value: T; raw: string; model: string; durationMs: number }> {
  const result = await generate(prompt, { ...options, format: "json" }, config);
  try {
    return {
      value: JSON.parse(result.text) as T,
      raw: result.text,
      model: result.model,
      durationMs: result.durationMs
    };
  } catch (err) {
    throw new Error(
      `ollama returned unparseable JSON (${(err as Error).message}). raw=${result.text.slice(0, 200)}`
    );
  }
}

export interface EmbedResult {
  embedding: number[];
  model: string;
  durationMs: number;
}

export async function embed(
  text: string,
  options: { model?: string; signal?: AbortSignal } = {},
  config: OllamaConfig = buildOllamaConfigFromEnv()
): Promise<EmbedResult> {
  const controller = new AbortController();
  const linked = options.signal ? linkAbort(options.signal, controller) : undefined;
  const timer = setTimeout(() => controller.abort(new Error("ollama-timeout")), config.timeoutMs);
  const started = Date.now();
  try {
    const res = await fetch(`${config.baseUrl}/api/embeddings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: options.model ?? config.defaultEmbedModel,
        prompt: text
      }),
      signal: controller.signal
    });
    if (!res.ok) {
      throw new Error(`ollama /api/embeddings ${res.status}: ${await res.text().catch(() => "")}`);
    }
    const json = (await res.json()) as { embedding: number[] };
    return {
      embedding: json.embedding,
      model: options.model ?? config.defaultEmbedModel,
      durationMs: Date.now() - started
    };
  } finally {
    clearTimeout(timer);
    linked?.dispose();
  }
}

export async function listModels(
  config: OllamaConfig = buildOllamaConfigFromEnv()
): Promise<Array<{ name: string; sizeBytes: number; quantization?: string }>> {
  const res = await fetch(`${config.baseUrl}/api/tags`);
  if (!res.ok) throw new Error(`ollama /api/tags ${res.status}`);
  const json = (await res.json()) as {
    models: Array<{ name: string; size: number; details?: { quantization_level?: string } }>;
  };
  return json.models.map((m) => ({
    name: m.name,
    sizeBytes: m.size,
    quantization: m.details?.quantization_level
  }));
}

function linkAbort(source: AbortSignal, target: AbortController): { dispose: () => void } {
  if (source.aborted) {
    target.abort(source.reason);
    return { dispose: () => undefined };
  }
  const onAbort = () => target.abort(source.reason);
  source.addEventListener("abort", onAbort, { once: true });
  return { dispose: () => source.removeEventListener("abort", onAbort) };
}
