import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { ALLOWED_TOPSTEP_MARKETS, SUPPORTED_STRATEGY_IDS, type SupportedStrategyId } from "../domain.js";

export interface OperatorIntentArtifact {
  capturedAt?: string;
  source?: "voice" | "discord" | "cli" | "note";
  text?: string;
  requestedActions?: string[];
}

export interface OperatorIntentAssessment {
  path: string;
  present: boolean;
  source: string | null;
  capturedAt: string | null;
  status: "none" | "advisory" | "requires-approval";
  summary: string;
  preferredStrategies: SupportedStrategyId[];
  preferredSymbols: string[];
  executionBlockers: string[];
  warnings: string[];
}

const RISKY_AUTHORITY_PATTERNS = [
  /enable\s+live/i,
  /real[-\s]?money/i,
  /route\s+live/i,
  /force\s+(a\s+)?trade/i,
  /ignore\s+(oos|out[-\s]?of[-\s]?sample|guardrails?|risk|drawdown)/i,
  /disable\s+(guardrails?|kill\s*switch|risk|oos|news|blackout)/i,
  /increase\s+(contracts?|size|risk|daily\s+loss|drawdown)/i,
  /raise\s+(contracts?|size|risk|daily\s+loss|drawdown)/i,
  /turn\s+off\s+(guardrails?|kill\s*switch|risk|oos|news|blackout)/i
];

const STRATEGY_PATTERNS: Array<{ strategyId: SupportedStrategyId; patterns: RegExp[] }> = [
  { strategyId: "session-momentum", patterns: [/session\s+momentum/i, /trend\s+day/i, /open\s+drive/i, /continuation/i] },
  { strategyId: "opening-range-reversal", patterns: [/opening\s+range/i, /\borr\b/i, /open(?:ing)?\s+reversal/i] },
  { strategyId: "liquidity-reversion", patterns: [/liquidity\s+sweep/i, /sweep\s+and\s+reverse/i, /mean\s+reversion/i, /\bfade\b/i] },
  { strategyId: "ict-displacement", patterns: [/\bict\b/i, /displacement/i, /fair\s+value\s+gap/i, /\bfvg\b/i, /\bmss\b/i] }
];

const SYMBOL_PATTERNS: Array<{ symbol: string; patterns: RegExp[] }> = [
  { symbol: "NQ", patterns: [/\bnq\b/i, /nasdaq/i, /nas100/i] },
  { symbol: "ES", patterns: [/\bes\b/i, /s&p/i, /\bspx\b/i] },
  { symbol: "CL", patterns: [/\bcl\b/i, /crude/i, /\bwti\b/i, /\boil\b/i] },
  { symbol: "GC", patterns: [/\bgc\b/i, /gold/i, /\bxau\b/i] },
  { symbol: "6E", patterns: [/\b6e\b/i, /eurusd/i, /euro/i] },
  { symbol: "ZN", patterns: [/\bzn\b/i, /10[\s-]?y/i, /treasury/i] }
];

function defaultPath(env: NodeJS.ProcessEnv): string {
  return resolve(env.BILL_OPERATOR_INTENT_PATH ?? ".rumbling-hedge/state/operator-intent.latest.json");
}

function unique<T>(values: T[]): T[] {
  return Array.from(new Set(values));
}

function artifactText(artifact: OperatorIntentArtifact): string {
  return [
    artifact.text,
    ...(artifact.requestedActions ?? [])
  ].filter((value): value is string => typeof value === "string" && value.trim().length > 0).join("\n");
}

function parseArtifact(raw: string, path: string): OperatorIntentArtifact {
  if (path.endsWith(".json")) {
    return JSON.parse(raw) as OperatorIntentArtifact;
  }
  return {
    source: "note",
    text: raw
  };
}

export async function assessLatestOperatorIntent(options: {
  path?: string;
  env?: NodeJS.ProcessEnv;
} = {}): Promise<OperatorIntentAssessment> {
  const path = resolve(options.path ?? defaultPath(options.env ?? process.env));
  let artifact: OperatorIntentArtifact;
  try {
    artifact = parseArtifact(await readFile(path, "utf8"), path);
  } catch {
    return {
      path,
      present: false,
      source: null,
      capturedAt: null,
      status: "none",
      summary: "no operator intent artifact present",
      preferredStrategies: [],
      preferredSymbols: [],
      executionBlockers: [],
      warnings: []
    };
  }

  const text = artifactText(artifact);
  const riskyHits = RISKY_AUTHORITY_PATTERNS
    .filter((pattern) => pattern.test(text))
    .map((pattern) => pattern.source);
  const preferredStrategies = unique(
    STRATEGY_PATTERNS
      .filter((entry) => entry.patterns.some((pattern) => pattern.test(text)))
      .map((entry) => entry.strategyId)
      .filter((strategyId) => (SUPPORTED_STRATEGY_IDS as readonly string[]).includes(strategyId))
  );
  const allowedSymbolSet = new Set<string>(ALLOWED_TOPSTEP_MARKETS);
  const preferredSymbols = unique(
    SYMBOL_PATTERNS
      .filter((entry) => allowedSymbolSet.has(entry.symbol) && entry.patterns.some((pattern) => pattern.test(text)))
      .map((entry) => entry.symbol)
  );
  const status = riskyHits.length > 0 ? "requires-approval" : "advisory";
  const summary = status === "requires-approval"
    ? "operator intent requests authority/risk changes; treating as advisory and blocking execution widening"
    : "operator intent is advisory only; using it as weak research focus";
  const executionBlockers = status === "requires-approval"
    ? ["operator intent requests authority/risk changes; execution widening requires explicit approval and evidence gates"]
    : [];

  return {
    path,
    present: true,
    source: artifact.source ?? "unknown",
    capturedAt: artifact.capturedAt ?? null,
    status,
    summary,
    preferredStrategies,
    preferredSymbols,
    executionBlockers,
    warnings: riskyHits.map((hit) => `risky operator intent matched /${hit}/`)
  };
}
