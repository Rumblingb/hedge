const DEFAULT_BASE_URL = "http://127.0.0.1:8787";
const DEFAULT_TIMEOUT_MS = 60_000;

export interface KronosOHLCV {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  amount?: number;
}

export interface KronosForecastInput {
  symbol: string;
  history: KronosOHLCV[];
  futureTimestamps: string[];
  modelName?: string;
  tokenizerName?: string;
  maxContext?: number;
  temperature?: number;
  topP?: number;
  sampleCount?: number;
}

export interface KronosPredictedRow {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number | null;
}

export interface KronosClientConfig {
  baseUrl?: string;
  timeoutMs?: number;
}

function baseUrl(config?: KronosClientConfig): string {
  return (config?.baseUrl ?? process.env.KRONOS_SIDECAR_URL ?? DEFAULT_BASE_URL).replace(/\/$/, "");
}

export async function kronosHealth(config?: KronosClientConfig): Promise<{
  ok: boolean;
  status?: number;
  body?: unknown;
  error?: string;
}> {
  try {
    const res = await fetch(`${baseUrl(config)}/health`, {
      signal: AbortSignal.timeout(config?.timeoutMs ?? 3000)
    });
    const body = await res.json().catch(() => undefined);
    return { ok: res.ok, status: res.status, body };
  } catch (err) {
    return { ok: false, error: (err as Error).message };
  }
}

export async function kronosForecast(
  input: KronosForecastInput,
  config?: KronosClientConfig
): Promise<KronosPredictedRow[]> {
  if (input.history.length < 8) {
    throw new Error(`kronos: need >=8 history bars, got ${input.history.length}`);
  }
  if (input.futureTimestamps.length < 1) {
    throw new Error("kronos: futureTimestamps must be non-empty");
  }
  const payload = {
    symbol: input.symbol,
    history: input.history.map((r) => ({
      ts: r.ts,
      open: r.open,
      high: r.high,
      low: r.low,
      close: r.close,
      volume: r.volume ?? 0,
      amount: r.amount ?? null
    })),
    future_timestamps: input.futureTimestamps,
    model_name: input.modelName,
    tokenizer_name: input.tokenizerName,
    max_context: input.maxContext,
    temperature: input.temperature ?? 1.0,
    top_p: input.topP ?? 0.9,
    sample_count: input.sampleCount ?? 1
  };
  const res = await fetch(`${baseUrl(config)}/forecast`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(config?.timeoutMs ?? DEFAULT_TIMEOUT_MS)
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`kronos forecast failed: ${res.status} ${text}`);
  }
  const body = (await res.json()) as { predicted: KronosPredictedRow[] };
  return body.predicted;
}
