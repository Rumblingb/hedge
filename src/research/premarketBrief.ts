import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { buildFreeMacroContextReport, type FreeMacroContextReport } from "./freeMacroContext.js";
import { loadRedFolderEvents } from "../news/redFolder.js";

export interface PremarketSearchResult {
  title: string;
  url: string;
  content: string;
  engine?: string;
}

export interface PremarketQueryResult {
  query: string;
  ok: boolean;
  resultCount: number;
  results: PremarketSearchResult[];
  error?: string;
}

export interface PremarketBriefReport {
  command: "premarket-brief";
  generatedAt: string;
  sessionDate: string;
  outputPath: string;
  markdownPath: string;
  search: {
    searxngUrl: string;
    queries: PremarketQueryResult[];
  };
  macro: {
    riskRegime: FreeMacroContextReport["derived"]["riskRegime"];
    tailScore: number;
    notes: string[];
  };
  redFolders: {
    path: string;
    count: number;
    upcomingHighImpact: Array<{
      symbol: string;
      ts: string;
      headline: string;
      direction: string;
      probability: number;
      impact: string;
    }>;
    warnings: string[];
  };
  deterministicRead: {
    themes: string[];
    riskFlags: string[];
    nqBias: "risk-on" | "risk-off" | "mixed" | "unknown";
    predictionMarketFocus: string[];
    tradePermission: "advisory-only";
  };
  advisory: {
    provider: "none" | "openrouter";
    model: string | null;
    ok: boolean;
    summary: string | null;
    error?: string;
  };
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/research/premarket/premarket-brief.latest.json";
const DEFAULT_MARKDOWN_PATH = ".rumbling-hedge/research/premarket/premarket-brief.latest.md";
const DEFAULT_SEARXNG_URL = "http://127.0.0.1:8888";

const DEFAULT_QUERIES = [
  "NQ futures premarket today Nasdaq catalysts",
  "Nasdaq futures today yields dollar VIX premarket",
  "economic calendar today CPI PPI FOMC jobs red folder",
  "Polymarket Kalshi trending markets today election crypto macro",
  "Treasury yields dollar index oil gold futures today",
  "market moving news today stocks futures premarket"
];

function cleanText(value: unknown): string {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function includesAny(text: string, needles: string[]): boolean {
  const lower = text.toLowerCase();
  return needles.some((needle) => lower.includes(needle));
}

async function searchSearxng(args: {
  baseUrl: string;
  query: string;
  maxResults: number;
  timeoutMs: number;
}): Promise<PremarketQueryResult> {
  const url = new URL("/search", args.baseUrl.endsWith("/") ? args.baseUrl : `${args.baseUrl}/`);
  url.searchParams.set("q", args.query);
  url.searchParams.set("format", "json");
  url.searchParams.set("language", "en");
  url.searchParams.set("safesearch", "0");

  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(args.timeoutMs),
      headers: { accept: "application/json" }
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json() as { results?: Array<Record<string, unknown>> };
    const results = (payload.results ?? []).slice(0, args.maxResults).map((item): PremarketSearchResult => ({
      title: cleanText(item.title),
      url: cleanText(item.url),
      content: cleanText(item.content),
      engine: cleanText(item.engine) || undefined
    })).filter((item) => item.title || item.url || item.content);
    return { query: args.query, ok: true, resultCount: results.length, results };
  } catch (error) {
    return {
      query: args.query,
      ok: false,
      resultCount: 0,
      results: [],
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

function dedupe<T>(items: T[]): T[] {
  return Array.from(new Set(items));
}

function deterministicRead(args: {
  macro: FreeMacroContextReport;
  queries: PremarketQueryResult[];
  redFolderCount: number;
}): PremarketBriefReport["deterministicRead"] {
  const text = args.queries
    .flatMap((query) => query.results.flatMap((result) => [result.title, result.content]))
    .join(" ");
  const themes: string[] = [];
  const riskFlags: string[] = [];
  const predictionMarketFocus: string[] = [];

  if (includesAny(text, ["fed", "fomc", "powell", "rate cut", "rate hike", "treasury", "yield"])) themes.push("rates-policy");
  if (includesAny(text, ["cpi", "ppi", "inflation", "jobs", "payroll", "unemployment"])) themes.push("macro-data");
  if (includesAny(text, ["vix", "volatility", "risk-off", "selloff", "crash"])) themes.push("volatility-risk");
  if (includesAny(text, ["nvidia", "ai", "semiconductor", "nasdaq", "mega-cap"])) themes.push("nasdaq-megacap");
  if (includesAny(text, ["oil", "gold", "dollar", "dxy", "geopolitical"])) themes.push("cross-asset-macro");
  if (includesAny(text, ["polymarket", "kalshi", "prediction market", "odds", "election"])) predictionMarketFocus.push("prediction-market-catalysts");
  if (includesAny(text, ["bitcoin", "crypto", "ethereum", "btc", "etf"])) predictionMarketFocus.push("crypto-linked-markets");
  if (includesAny(text, ["election", "congress", "president", "supreme court"])) predictionMarketFocus.push("political-event-markets");

  if (args.redFolderCount > 0) riskFlags.push("red-folder-events-present");
  if (args.macro.derived.riskRegime !== "normal") riskFlags.push(`macro-risk-${args.macro.derived.riskRegime}`);
  if (args.queries.some((query) => !query.ok)) riskFlags.push("searxng-query-degraded");
  if ((args.macro.derived.vixLevel ?? 0) >= 20) riskFlags.push("vix-above-20");

  const nqBias = args.macro.derived.riskRegime === "stress"
    ? "risk-off"
    : args.macro.derived.equityTrendProxy === "risk-on" && args.macro.derived.creditRiskProxy !== "weakening"
      ? "risk-on"
      : args.macro.derived.equityTrendProxy === "risk-off" || args.macro.derived.creditRiskProxy === "weakening"
        ? "risk-off"
        : themes.length > 0
          ? "mixed"
          : "unknown";

  return {
    themes: dedupe(themes),
    riskFlags: dedupe(riskFlags),
    nqBias,
    predictionMarketFocus: dedupe(predictionMarketFocus),
    tradePermission: "advisory-only"
  };
}

async function callOpenRouter(args: {
  apiKey: string;
  models: string[];
  report: Omit<PremarketBriefReport, "advisory">;
  timeoutMs: number;
}): Promise<PremarketBriefReport["advisory"]> {
  const prompt = [
    "You are Bill/Hedge's premarket analyst. Summarize only actionable context.",
    "Do not authorize trades. Do not claim edge. Return concise bullets:",
    "1) NQ/prop-firm context, 2) prediction-market watch themes, 3) red-folder risks, 4) what deterministic gates must verify.",
    JSON.stringify({
      macro: args.report.macro,
      redFolders: args.report.redFolders,
      deterministicRead: args.report.deterministicRead,
      search: args.report.search.queries.map((query) => ({
        query: query.query,
        results: query.results.slice(0, 3)
      }))
    })
  ].join("\n\n");

  const errors: string[] = [];
  for (const model of args.models) {
    try {
      const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
        method: "POST",
        signal: AbortSignal.timeout(args.timeoutMs),
        headers: {
          authorization: `Bearer ${args.apiKey}`,
          "content-type": "application/json",
          "http-referer": "http://localhost/bill-hedge",
          "x-title": "Bill Hedge Premarket Brief"
        },
        body: JSON.stringify({
          model,
          messages: [
            { role: "system", content: "You are an advisory research summarizer. You never authorize trades." },
            { role: "user", content: prompt }
          ],
          temperature: 0.1,
          max_tokens: 450
        })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json() as { choices?: Array<{ message?: { content?: string } }> };
      const summary = cleanText(payload.choices?.[0]?.message?.content);
      if (summary.length >= 20) {
        return { provider: "openrouter", model, ok: true, summary };
      }
      errors.push(`${model}: empty or too short response`);
    } catch (error) {
      errors.push(`${model}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  return {
    provider: "openrouter",
    model: args.models[0] ?? null,
    ok: false,
    summary: null,
    error: errors.join("; ") || "no OpenRouter models configured"
  };
}

function openRouterModelCandidates(env: NodeJS.ProcessEnv): string[] {
  const raw = env.BILL_PREMARKET_OPENROUTER_MODELS
    ?? env.BILL_PREMARKET_OPENROUTER_MODEL
    ?? env.OPENROUTER_MODEL;
  const configured = raw
    ? raw.split(/[|,]/).map((model) => model.trim()).filter(Boolean)
    : [];
  return dedupe([
    ...configured,
    "openrouter/free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openai/gpt-oss-120b:free"
  ]);
}

function renderMarkdown(report: PremarketBriefReport): string {
  const queryLines = report.search.queries.map((query) => [
    `### ${query.query}`,
    query.ok
      ? query.results.slice(0, 5).map((result) => `- ${result.title || result.url} — ${result.url}`).join("\n")
      : `- degraded: ${query.error}`
  ].join("\n"));
  return [
    "# Bill/Hedge Premarket Brief",
    "",
    `- generated: ${report.generatedAt}`,
    `- session date: ${report.sessionDate}`,
    `- trade permission: ${report.deterministicRead.tradePermission}`,
    `- NQ deterministic bias: ${report.deterministicRead.nqBias}`,
    `- macro: ${report.macro.riskRegime} / tail score ${report.macro.tailScore}`,
    `- red-folder events: ${report.redFolders.count}`,
    "",
    "## Themes",
    ...(report.deterministicRead.themes.length ? report.deterministicRead.themes.map((item) => `- ${item}`) : ["- none detected"]),
    "",
    "## Risk Flags",
    ...(report.deterministicRead.riskFlags.length ? report.deterministicRead.riskFlags.map((item) => `- ${item}`) : ["- none detected"]),
    "",
    "## Prediction-Market Watch",
    ...(report.deterministicRead.predictionMarketFocus.length ? report.deterministicRead.predictionMarketFocus.map((item) => `- ${item}`) : ["- none detected"]),
    "",
    "## Advisory LLM Summary",
    report.advisory.ok && report.advisory.summary ? report.advisory.summary : `- ${report.advisory.provider === "none" ? "LLM disabled/unconfigured." : `LLM unavailable: ${report.advisory.error ?? "unknown"}`}`,
    "",
    "## Search Evidence",
    ...queryLines,
    ""
  ].join("\n");
}

export async function buildPremarketBrief(args: {
  outputPath?: string;
  markdownPath?: string;
  searxngUrl?: string;
  queries?: string[];
  maxResults?: number;
  timeoutMs?: number;
  macroOutputPath?: string;
  macroCsvPath?: string;
  env?: NodeJS.ProcessEnv;
  now?: () => string;
} = {}): Promise<PremarketBriefReport> {
  const env = args.env ?? process.env;
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const outputPath = resolve(args.outputPath ?? env.BILL_PREMARKET_BRIEF_PATH ?? DEFAULT_OUTPUT_PATH);
  const markdownPath = resolve(args.markdownPath ?? env.BILL_PREMARKET_BRIEF_MARKDOWN_PATH ?? DEFAULT_MARKDOWN_PATH);
  const searxngUrl = args.searxngUrl ?? env.BILL_SEARXNG_URL ?? DEFAULT_SEARXNG_URL;
  const queries = args.queries ?? (env.BILL_PREMARKET_QUERIES
    ? env.BILL_PREMARKET_QUERIES.split("|").map((query) => query.trim()).filter(Boolean)
    : DEFAULT_QUERIES);
  const timeoutMs = args.timeoutMs ?? Number.parseInt(env.BILL_PREMARKET_TIMEOUT_MS ?? "20000", 10);
  const maxResults = args.maxResults ?? Number.parseInt(env.BILL_PREMARKET_MAX_RESULTS ?? "6", 10);

  const [macro, redFolders, searchQueries] = await Promise.all([
    buildFreeMacroContextReport({
      outputPath: args.macroOutputPath,
      csvPath: args.macroCsvPath,
      range: env.BILL_PREMARKET_MACRO_RANGE ?? "6mo",
      timeoutMs
    }),
    loadRedFolderEvents(env.BILL_RED_FOLDER_EVENTS_PATH),
    Promise.all(queries.map((query) => searchSearxng({ baseUrl: searxngUrl, query, maxResults, timeoutMs })))
  ]);

  const upcomingHighImpact = redFolders.events
    .filter((event) => event.impact === "high")
    .sort((left, right) => Date.parse(left.ts) - Date.parse(right.ts))
    .slice(0, 12)
    .map((event) => ({
      symbol: event.symbol,
      ts: event.ts,
      headline: event.headline,
      direction: event.direction,
      probability: event.probability,
      impact: event.impact
    }));

  const baseReport = {
    command: "premarket-brief" as const,
    generatedAt,
    sessionDate: generatedAt.slice(0, 10),
    outputPath,
    markdownPath,
    search: { searxngUrl, queries: searchQueries },
    macro: {
      riskRegime: macro.derived.riskRegime,
      tailScore: macro.derived.tailScore,
      notes: macro.derived.notes
    },
    redFolders: {
      path: redFolders.path,
      count: redFolders.events.length,
      upcomingHighImpact,
      warnings: redFolders.warnings
    },
    deterministicRead: deterministicRead({ macro, queries: searchQueries, redFolderCount: redFolders.events.length })
  };

  const openRouterKey = env.OPENROUTER_API_KEY ?? env.BILL_OPENROUTER_API_KEY;
  const openRouterEnabled = env.BILL_PREMARKET_OPENROUTER_ENABLED !== "false" && Boolean(openRouterKey);
  const advisory = openRouterEnabled
    ? await callOpenRouter({
        apiKey: openRouterKey!,
        models: openRouterModelCandidates(env),
        report: baseReport,
        timeoutMs
      })
    : { provider: "none" as const, model: null, ok: false, summary: null };

  const report: PremarketBriefReport = { ...baseReport, advisory };
  await mkdir(dirname(outputPath), { recursive: true });
  await mkdir(dirname(markdownPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await writeFile(markdownPath, renderMarkdown(report), "utf8");
  return report;
}
