/**
 * Minimal OpenAI-compatible chat adapter for hosted providers such as OpenRouter.
 * Keep this surface intentionally small until a caller needs more.
 */

import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

export interface OpenAiCompatibleConfig {
  baseUrl: string;
  apiKey?: string;
  defaultModel: string;
  timeoutMs: number;
  provider: string;
}

export interface GenerateOptions {
  model?: string;
  system?: string;
  temperature?: number;
  maxTokens?: number;
  stop?: string[];
  format?: "json";
  signal?: AbortSignal;
  extraBody?: Record<string, unknown>;
}

export interface GenerateResult {
  text: string;
  model: string;
  promptTokens?: number;
  completionTokens?: number;
  durationMs: number;
}

interface CloudBudgetLedger {
  date: string;
  requests: number;
  promptTokens: number;
  completionTokens: number;
  lastModel?: string;
  lastReservedAt?: string;
  lastCompletedAt?: string;
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function buildOpenAiCompatibleConfigFromEnv(
  env: NodeJS.ProcessEnv = process.env
): OpenAiCompatibleConfig {
  const timeoutRaw = Number.parseInt(
    env.BILL_CLOUD_TIMEOUT_MS ?? env.BILL_OLLAMA_TIMEOUT_MS ?? "120000",
    10
  );
  return {
    baseUrl: trimTrailingSlash(
      env.BILL_CLOUD_BASE_URL
      ?? env.NVIDIA_NIM_BASE_URL
      ?? "https://openrouter.ai/api/v1"
    ),
    apiKey: env.BILL_CLOUD_API_KEY ?? env.NVIDIA_NIM_API_KEY ?? env.NVIDIA_API_KEY,
    defaultModel: env.BILL_CLOUD_REVIEW_MODEL ?? "deepseek/deepseek-v3.2",
    timeoutMs: Number.isFinite(timeoutRaw) && timeoutRaw > 0 ? timeoutRaw : 120_000,
    provider: env.BILL_CLOUD_PROVIDER ?? "openrouter"
  };
}

function buildChatMessages(prompt: string, options: GenerateOptions): Array<Record<string, unknown>> {
  const messages: Array<Record<string, unknown>> = [];
  if (options.system) {
    messages.push({
      role: "system",
      content: options.system
    });
  }
  messages.push({
    role: "user",
    content: prompt
  });
  return messages;
}

function extractTextContent(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") {
          return part;
        }
        if (part && typeof part === "object" && "text" in part && typeof part.text === "string") {
          return part.text;
        }
        return "";
      })
      .join("");
  }
  return "";
}

function requireApiKey(config: OpenAiCompatibleConfig): string {
  if (!config.apiKey) {
    throw new Error(
      `${config.provider} requires BILL_CLOUD_API_KEY, NVIDIA_NIM_API_KEY, or NVIDIA_API_KEY.`
    );
  }
  return config.apiKey;
}

function cloudBudgetDateKey(now = new Date()): string {
  return now.toISOString().slice(0, 10);
}

function cloudBudgetLedgerPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.BILL_CLOUD_BUDGET_LEDGER_PATH ?? ".rumbling-hedge/state/cloud-budget-ledger.json");
}

function readCloudBudgetLedger(pathname: string, date: string): CloudBudgetLedger {
  try {
    const parsed = JSON.parse(readFileSync(pathname, "utf8")) as Partial<CloudBudgetLedger>;
    if (parsed.date === date) {
      return {
        date,
        requests: Number(parsed.requests ?? 0),
        promptTokens: Number(parsed.promptTokens ?? 0),
        completionTokens: Number(parsed.completionTokens ?? 0),
        lastModel: parsed.lastModel,
        lastReservedAt: parsed.lastReservedAt,
        lastCompletedAt: parsed.lastCompletedAt
      };
    }
  } catch {
    // Missing or corrupt ledgers reset for the current day.
  }
  return {
    date,
    requests: 0,
    promptTokens: 0,
    completionTokens: 0
  };
}

function writeCloudBudgetLedger(pathname: string, ledger: CloudBudgetLedger): void {
  mkdirSync(dirname(pathname), { recursive: true });
  writeFileSync(pathname, `${JSON.stringify(ledger, null, 2)}\n`, "utf8");
}

function parseOptionalNonNegativeInt(value: string | undefined): number | null {
  if (value == null || value.trim() === "") {
    return null;
  }
  const limit = Number.parseInt(value, 10);
  return Number.isFinite(limit) ? Math.max(0, limit) : null;
}

function parseDailyCloudRequestLimit(env: NodeJS.ProcessEnv = process.env): number | null {
  return parseOptionalNonNegativeInt(env.BILL_MAX_CLOUD_REVIEWS_PER_DAY);
}

function parseDailyCloudTokenLimit(env: NodeJS.ProcessEnv = process.env): number | null {
  return parseOptionalNonNegativeInt(env.BILL_MAX_CLOUD_TOKENS_PER_DAY);
}

function withCloudBudgetLock<T>(pathname: string, fn: () => T): T {
  const lockPath = `${pathname}.lock`;
  const deadline = Date.now() + 5_000;
  mkdirSync(dirname(lockPath), { recursive: true });
  for (;;) {
    try {
      mkdirSync(lockPath);
      break;
    } catch {
      if (Date.now() > deadline) {
        throw new Error(`Bill cloud budget ledger is locked: ${lockPath}`);
      }
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 50);
    }
  }
  try {
    return fn();
  } finally {
    rmSync(lockPath, { recursive: true, force: true });
  }
}

function assertCloudTokenBudget(ledger: CloudBudgetLedger, maxTokens: number | null, date: string): void {
  if (maxTokens == null) {
    return;
  }
  const usedTokens = Number(ledger.promptTokens ?? 0) + Number(ledger.completionTokens ?? 0);
  if (usedTokens >= maxTokens) {
    throw new Error(
      `Bill cloud token budget exhausted for ${date}: ${usedTokens}/${maxTokens} hosted tokens used. Increase BILL_MAX_CLOUD_TOKENS_PER_DAY or run local/offline.`
    );
  }
}

function reserveCloudBudget(model: string): { path: string; date: string } | null {
  const maxRequests = parseDailyCloudRequestLimit();
  const maxTokens = parseDailyCloudTokenLimit();
  if (maxRequests == null && maxTokens == null) {
    return null;
  }

  const date = cloudBudgetDateKey();
  const path = cloudBudgetLedgerPath();
  withCloudBudgetLock(path, () => {
    const ledger = readCloudBudgetLedger(path, date);
    if (maxRequests != null && ledger.requests >= maxRequests) {
      throw new Error(
        `Bill cloud budget exhausted for ${date}: ${ledger.requests}/${maxRequests} hosted review calls used. Increase BILL_MAX_CLOUD_REVIEWS_PER_DAY or run local/offline.`
      );
    }
    assertCloudTokenBudget(ledger, maxTokens, date);

    ledger.requests += 1;
    ledger.lastModel = model;
    ledger.lastReservedAt = new Date().toISOString();
    writeCloudBudgetLedger(path, ledger);
  });
  return { path, date };
}

function completeCloudBudget(
  reservation: { path: string; date: string } | null,
  result: { model: string; promptTokens?: number; completionTokens?: number }
): void {
  if (!reservation) {
    return;
  }

  withCloudBudgetLock(reservation.path, () => {
    const ledger = readCloudBudgetLedger(reservation.path, reservation.date);
    ledger.promptTokens += Number(result.promptTokens ?? 0);
    ledger.completionTokens += Number(result.completionTokens ?? 0);
    ledger.lastModel = result.model;
    ledger.lastCompletedAt = new Date().toISOString();
    writeCloudBudgetLedger(reservation.path, ledger);
  });
}

export async function generate(
  prompt: string,
  options: GenerateOptions = {},
  config: OpenAiCompatibleConfig = buildOpenAiCompatibleConfigFromEnv()
): Promise<GenerateResult> {
  const controller = new AbortController();
  const linked = options.signal ? linkAbort(options.signal, controller) : undefined;
  const timer = setTimeout(() => controller.abort(new Error("openai-compatible-timeout")), config.timeoutMs);
  const started = Date.now();
  const model = options.model ?? config.defaultModel;
  const reservation = reserveCloudBudget(model);

  try {
    const res = await fetch(`${config.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${requireApiKey(config)}`
      },
      body: JSON.stringify({
        model,
        messages: buildChatMessages(prompt, options),
        temperature: options.temperature ?? 0.2,
        max_tokens: options.maxTokens ?? 1024,
        stop: options.stop,
        ...(options.format === "json" ? { response_format: { type: "json_object" } } : {}),
        ...(options.extraBody ?? {})
      }),
      signal: controller.signal
    });
    if (!res.ok) {
      throw new Error(
        `${config.provider} /chat/completions ${res.status}: ${await res.text().catch(() => "")}`
      );
    }

    const json = (await res.json()) as {
      model?: string;
      choices?: Array<{ message?: { content?: unknown } }>;
      usage?: { prompt_tokens?: number; completion_tokens?: number };
    };
    const text = extractTextContent(json.choices?.[0]?.message?.content);
    const result = {
      text,
      model: json.model ?? model,
      promptTokens: json.usage?.prompt_tokens,
      completionTokens: json.usage?.completion_tokens,
      durationMs: Date.now() - started
    };
    completeCloudBudget(reservation, result);
    return result;
  } finally {
    clearTimeout(timer);
    linked?.dispose();
  }
}

export async function generateJson<T = unknown>(
  prompt: string,
  options: Omit<GenerateOptions, "format"> = {},
  config: OpenAiCompatibleConfig = buildOpenAiCompatibleConfigFromEnv()
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
      `${config.provider} returned unparseable JSON (${(err as Error).message}). raw=${result.text.slice(0, 200)}`
    );
  }
}

export async function listModels(
  config: OpenAiCompatibleConfig = buildOpenAiCompatibleConfigFromEnv()
): Promise<Array<{ id: string; ownedBy?: string }>> {
  const res = await fetch(`${config.baseUrl}/models`, {
    headers: {
      Authorization: `Bearer ${requireApiKey(config)}`
    }
  });
  if (!res.ok) {
    throw new Error(`${config.provider} /models ${res.status}: ${await res.text().catch(() => "")}`);
  }
  const json = (await res.json()) as {
    data?: Array<{ id?: string; owned_by?: string }>;
  };
  return (json.data ?? [])
    .filter((model): model is { id: string; owned_by?: string } => typeof model.id === "string")
    .map((model) => ({
      id: model.id,
      ownedBy: model.owned_by
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
