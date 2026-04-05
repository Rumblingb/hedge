import { z } from "zod";
import { ALLOWED_TOPSTEP_MARKETS, type LabConfig } from "./domain.js";

const envSchema = z.object({
  RH_MODE: z.enum(["paper", "backtest", "live"]).optional(),
  RH_ALLOWED_SYMBOLS: z.string().optional(),
  RH_SESSION_START_CT: z.string().optional(),
  RH_LAST_ENTRY_CT: z.string().optional(),
  RH_FLAT_BY_CT: z.string().optional(),
  RH_MIN_RR: z.coerce.number().optional(),
  RH_MAX_CONTRACTS: z.coerce.number().optional(),
  RH_MAX_TRADES_PER_DAY: z.coerce.number().optional(),
  RH_MAX_HOLD_MINUTES: z.coerce.number().optional(),
  RH_MAX_DAILY_LOSS_R: z.coerce.number().optional(),
  RH_MAX_CONSECUTIVE_LOSSES: z.coerce.number().optional(),
  RH_NEWS_THRESHOLD: z.coerce.number().optional(),
  RH_JOURNAL_PATH: z.string().optional(),
  RH_LIVE_EXECUTION_ENABLED: z.string().optional(),
  RH_TOPSTEP_BASE_URL: z.string().optional(),
  RH_TOPSTEP_ACCOUNT_ID: z.string().optional(),
  RH_TOPSTEP_API_KEY: z.string().optional()
});

function resolveAllowedSymbols(raw?: string): string[] {
  if (!raw) {
    return ["NQ", "ES", "CL", "GC", "6E"];
  }

  const requested = raw
    .split(",")
    .map((value) => value.trim().toUpperCase())
    .filter(Boolean);

  return requested.filter((symbol) =>
    (ALLOWED_TOPSTEP_MARKETS as readonly string[]).includes(symbol)
  );
}

export function getConfig(): LabConfig {
  const env = envSchema.parse(process.env);

  return {
    mode: env.RH_MODE ?? "paper",
    journalPath: env.RH_JOURNAL_PATH ?? ".rumbling-hedge/journal.jsonl",
    enabledStrategies: ["session-momentum"],
    guardrails: {
      allowedSymbols: resolveAllowedSymbols(env.RH_ALLOWED_SYMBOLS),
      sessionStartCt: env.RH_SESSION_START_CT ?? "08:30",
      lastEntryCt: env.RH_LAST_ENTRY_CT ?? "11:30",
      flatByCt: env.RH_FLAT_BY_CT ?? "15:10",
      minRr: env.RH_MIN_RR ?? 2.5,
      maxRiskPerTradePct: 1,
      maxContracts: env.RH_MAX_CONTRACTS ?? 2,
      maxTradesPerDay: env.RH_MAX_TRADES_PER_DAY ?? 3,
      maxHoldMinutes: env.RH_MAX_HOLD_MINUTES ?? 30,
      maxDailyLossR: env.RH_MAX_DAILY_LOSS_R ?? 2,
      maxConsecutiveLosses: env.RH_MAX_CONSECUTIVE_LOSSES ?? 2,
      newsProbabilityThreshold: env.RH_NEWS_THRESHOLD ?? 0.65
    },
    tuning: {
      momentumLookbackBars: 6,
      momentumVolumeMultiplier: 1.2,
      reversionLookbackBars: 8,
      reversionWickToBody: 1.5,
      measuredMoveRr: 2.8
    },
    live: {
      enabled: env.RH_LIVE_EXECUTION_ENABLED === "true",
      baseUrl: env.RH_TOPSTEP_BASE_URL,
      accountId: env.RH_TOPSTEP_ACCOUNT_ID,
      apiKey: env.RH_TOPSTEP_API_KEY
    }
  };
}
