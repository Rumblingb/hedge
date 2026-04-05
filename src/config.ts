import { z } from "zod";
import { ALLOWED_TOPSTEP_MARKETS, type AccountPhase, type GuardrailConfig, type LabConfig } from "./domain.js";

const envSchema = z.object({
  RH_MODE: z.enum(["paper", "backtest", "live"]).optional(),
  RH_ACCOUNT_PHASE: z.enum(["challenge", "funded"]).optional(),
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
  RH_FEE_R_PER_CONTRACT: z.coerce.number().optional(),
  RH_SLIPPAGE_R_PER_SIDE: z.coerce.number().optional(),
  RH_STRESS_MULTIPLIER: z.coerce.number().optional(),
  RH_STRESS_BUFFER_R: z.coerce.number().optional(),
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

function getPhaseGuardrailDefaults(phase: AccountPhase): Pick<GuardrailConfig, "minRr" | "maxContracts" | "maxTradesPerDay" | "maxHoldMinutes" | "maxDailyLossR" | "maxConsecutiveLosses"> {
  if (phase === "funded") {
    return {
      minRr: 2.8,
      maxContracts: 1,
      maxTradesPerDay: 2,
      maxHoldMinutes: 20,
      maxDailyLossR: 1.25,
      maxConsecutiveLosses: 1
    };
  }

  return {
    minRr: 2.5,
    maxContracts: 2,
    maxTradesPerDay: 3,
    maxHoldMinutes: 30,
    maxDailyLossR: 2,
    maxConsecutiveLosses: 2
  };
}

export function getConfig(): LabConfig {
  const env = envSchema.parse(process.env);
  const accountPhase = env.RH_ACCOUNT_PHASE ?? "challenge";
  const phaseDefaults = getPhaseGuardrailDefaults(accountPhase);

  return {
    mode: env.RH_MODE ?? "paper",
    accountPhase,
    journalPath: env.RH_JOURNAL_PATH ?? ".rumbling-hedge/journal.jsonl",
    enabledStrategies: ["session-momentum"],
    guardrails: {
      allowedSymbols: resolveAllowedSymbols(env.RH_ALLOWED_SYMBOLS),
      sessionStartCt: env.RH_SESSION_START_CT ?? "08:30",
      lastEntryCt: env.RH_LAST_ENTRY_CT ?? "11:30",
      flatByCt: env.RH_FLAT_BY_CT ?? "15:10",
      minRr: env.RH_MIN_RR ?? phaseDefaults.minRr,
      maxRiskPerTradePct: 1,
      maxContracts: env.RH_MAX_CONTRACTS ?? phaseDefaults.maxContracts,
      maxTradesPerDay: env.RH_MAX_TRADES_PER_DAY ?? phaseDefaults.maxTradesPerDay,
      maxHoldMinutes: env.RH_MAX_HOLD_MINUTES ?? phaseDefaults.maxHoldMinutes,
      maxDailyLossR: env.RH_MAX_DAILY_LOSS_R ?? phaseDefaults.maxDailyLossR,
      maxConsecutiveLosses: env.RH_MAX_CONSECUTIVE_LOSSES ?? phaseDefaults.maxConsecutiveLosses,
      newsProbabilityThreshold: env.RH_NEWS_THRESHOLD ?? 0.65
    },
    executionCosts: {
      roundTripFeeRPerContract: env.RH_FEE_R_PER_CONTRACT ?? 0.01,
      slippageRPerSidePerContract: env.RH_SLIPPAGE_R_PER_SIDE ?? 0.015,
      stressMultiplier: env.RH_STRESS_MULTIPLIER ?? 1.25,
      stressBufferRPerTrade: env.RH_STRESS_BUFFER_R ?? 0.01
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
