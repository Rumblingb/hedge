import { z } from "zod";
import {
  ALLOWED_TOPSTEP_MARKETS,
  SUPPORTED_STRATEGY_IDS,
  type AccountPhase,
  type GuardrailConfig,
  type LabConfig,
  type RedactedLabConfig,
  type SupportedStrategyId
} from "./domain.js";
import { resolveProjectXApiBaseUrl } from "./adapters/projectx/baseUrl.js";

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
  RH_TRAILING_MAX_DRAWDOWN_R: z.coerce.number().optional(),
  RH_MAX_CONSECUTIVE_LOSSES: z.coerce.number().optional(),
  RH_NEWS_THRESHOLD: z.coerce.number().optional(),
  RH_NEWS_BLACKOUT_MINUTES_BEFORE: z.coerce.number().optional(),
  RH_NEWS_BLACKOUT_MINUTES_AFTER: z.coerce.number().optional(),
  RH_FEE_R_PER_CONTRACT: z.coerce.number().optional(),
  RH_SLIPPAGE_R_PER_SIDE: z.coerce.number().optional(),
  RH_STRESS_MULTIPLIER: z.coerce.number().optional(),
  RH_STRESS_BUFFER_R: z.coerce.number().optional(),
  RH_EXECUTION_LATENCY_MS: z.coerce.number().optional(),
  RH_EXECUTION_LATENCY_JITTER_MS: z.coerce.number().optional(),
  RH_EXECUTION_SLIPPAGE_TICKS_PER_SIDE: z.coerce.number().optional(),
  RH_EXECUTION_DATA_QUALITY_PENALTY_R: z.coerce.number().optional(),
  RH_EXECUTION_MAX_SPREAD_TICKS: z.coerce.number().optional(),
  RH_EXECUTION_RISK_PER_CONTRACT_USD: z.coerce.number().optional(),
  RH_EXECUTION_SLIPPAGE_MODEL: z.enum(["ticks", "dollars"]).optional(),
  RH_STOP_MGMT_ENABLED: z.string().optional(),
  RH_BREAK_EVEN_TRIGGER_R: z.coerce.number().optional(),
  RH_BREAK_EVEN_OFFSET_R: z.coerce.number().optional(),
  RH_RUNNER_ENABLED: z.string().optional(),
  RH_RUNNER_TRIGGER_R: z.coerce.number().optional(),
  RH_RUNNER_TRAILING_DISTANCE_R: z.coerce.number().optional(),
  RH_JOURNAL_PATH: z.string().optional(),
  RH_KILL_SWITCH_PATH: z.string().optional(),
  RH_LIVE_EXECUTION_ENABLED: z.string().optional(),
  RH_ENABLED_STRATEGIES: z.string().optional(),
  RH_TOPSTEP_BASE_URL: z.string().optional(),
  RH_TOPSTEP_USERNAME: z.string().optional(),
  RH_TOPSTEP_ACCOUNT_ID: z.string().optional(),
  RH_TOPSTEP_ALLOWED_ACCOUNT_ID: z.string().optional(),
  RH_TOPSTEP_ALLOWED_ACCOUNT_IDS: z.string().optional(),
  RH_TOPSTEP_ALLOWED_ACCOUNT_LABEL: z.string().optional(),
  RH_TOPSTEP_ALLOWED_ACCOUNT_LABELS: z.string().optional(),
  RH_TOPSTEP_API_KEY: z.string().optional(),
  RH_TOPSTEP_DEMO_ONLY: z.string().optional(),
  RH_TOPSTEP_READ_ONLY: z.string().optional(),
  RH_POLYGON_ENABLED: z.string().optional(),
  RH_POLYGON_API_KEY: z.string().optional(),
  RH_POLYGON_BASE_URL: z.string().optional()
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

function parseCsv(raw?: string): string[] {
  return (raw ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values));
}

function optionalTrimmed(value?: string): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

function resolveEnabledStrategies(raw?: string): SupportedStrategyId[] {
  const defaultStrategies: SupportedStrategyId[] = [
    "opening-range-reversal",
    "session-momentum",
    "liquidity-reversion",
    "ict-displacement"
  ];
  const requested = unique(parseCsv(raw).map((value) => value.toLowerCase()));
  if (requested.length === 0) {
    return defaultStrategies;
  }

  const supported = new Set<string>(SUPPORTED_STRATEGY_IDS);
  const filtered = requested.filter((strategyId): strategyId is SupportedStrategyId => supported.has(strategyId));
  return filtered.length > 0 ? filtered : defaultStrategies;
}

function resolveAllowedAccountIds(env: z.infer<typeof envSchema>): string[] {
  return unique([
    ...parseCsv(env.RH_TOPSTEP_ALLOWED_ACCOUNT_IDS),
    ...(env.RH_TOPSTEP_ALLOWED_ACCOUNT_ID ? [env.RH_TOPSTEP_ALLOWED_ACCOUNT_ID] : [])
  ]);
}

function resolveAllowedAccountLabels(env: z.infer<typeof envSchema>): string[] {
  const labels = parseCsv(env.RH_TOPSTEP_ALLOWED_ACCOUNT_LABELS);
  if (labels.length > 0) {
    return labels;
  }

  return env.RH_TOPSTEP_ALLOWED_ACCOUNT_LABEL
    ? [env.RH_TOPSTEP_ALLOWED_ACCOUNT_LABEL]
    : [];
}

function maskSecret(value?: string): string | undefined {
  if (!value) return value;
  if (value.length <= 8) return "*".repeat(value.length);
  return `${value.slice(0, 3)}***${value.slice(-3)}`;
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
  const enabledStrategies = resolveEnabledStrategies(env.RH_ENABLED_STRATEGIES);
  const allowedAccountIds = resolveAllowedAccountIds(env);
  const allowedAccountLabels = resolveAllowedAccountLabels(env);
  const primaryAllowedAccountId = optionalTrimmed(env.RH_TOPSTEP_ALLOWED_ACCOUNT_ID) ?? allowedAccountIds[0];
  const primaryAllowedAccountLabel = optionalTrimmed(env.RH_TOPSTEP_ALLOWED_ACCOUNT_LABEL) ?? allowedAccountLabels[0];
  const configuredAccountId = optionalTrimmed(env.RH_TOPSTEP_ACCOUNT_ID)
    ?? (allowedAccountIds.length === 1 ? allowedAccountIds[0] : undefined);

  return {
    mode: env.RH_MODE ?? "paper",
    accountPhase,
    journalPath: env.RH_JOURNAL_PATH ?? ".rumbling-hedge/journal.jsonl",
    killSwitchPath: env.RH_KILL_SWITCH_PATH ?? ".rumbling-hedge/kill-switch.json",
    enabledStrategies,
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
      trailingMaxDrawdownR: env.RH_TRAILING_MAX_DRAWDOWN_R ?? (phaseDefaults.maxDailyLossR * 2),
      maxConsecutiveLosses: env.RH_MAX_CONSECUTIVE_LOSSES ?? phaseDefaults.maxConsecutiveLosses,
      newsProbabilityThreshold: env.RH_NEWS_THRESHOLD ?? 0.65,
      newsBlackoutMinutesBefore: env.RH_NEWS_BLACKOUT_MINUTES_BEFORE ?? 15,
      newsBlackoutMinutesAfter: env.RH_NEWS_BLACKOUT_MINUTES_AFTER ?? 30
    },
    executionCosts: {
      roundTripFeeRPerContract: env.RH_FEE_R_PER_CONTRACT ?? 0.01,
      slippageRPerSidePerContract: env.RH_SLIPPAGE_R_PER_SIDE ?? 0.015,
      stressMultiplier: env.RH_STRESS_MULTIPLIER ?? 1.25,
      stressBufferRPerTrade: env.RH_STRESS_BUFFER_R ?? 0.01
    },
    executionEnv: {
      latencyMs: env.RH_EXECUTION_LATENCY_MS ?? 75,
      latencyJitterMs: env.RH_EXECUTION_LATENCY_JITTER_MS ?? 30,
      slippageTicksPerSide: env.RH_EXECUTION_SLIPPAGE_TICKS_PER_SIDE ?? 1,
      dataQualityPenaltyR: env.RH_EXECUTION_DATA_QUALITY_PENALTY_R ?? 0.015,
      maxSpreadTicks: env.RH_EXECUTION_MAX_SPREAD_TICKS ?? 2,
      riskPerContractDollars: env.RH_EXECUTION_RISK_PER_CONTRACT_USD ?? 300,
      slippageModel: env.RH_EXECUTION_SLIPPAGE_MODEL ?? "ticks"
    },
    stopManagement: {
      enabled: env.RH_STOP_MGMT_ENABLED === "true",
      breakEvenTriggerR: env.RH_BREAK_EVEN_TRIGGER_R ?? 1,
      breakEvenOffsetR: env.RH_BREAK_EVEN_OFFSET_R ?? 0,
      runnerEnabled: env.RH_RUNNER_ENABLED === "true",
      runnerTriggerR: env.RH_RUNNER_TRIGGER_R ?? 1.5,
      runnerTrailingDistanceR: env.RH_RUNNER_TRAILING_DISTANCE_R ?? 1
    },
    tuning: {
      momentumLookbackBars: 6,
      momentumVolumeMultiplier: 1.2,
      reversionLookbackBars: 8,
      reversionWickToBody: 1.5,
      measuredMoveRr: 2.8,
      volatilityKillAtrMultiple: 2.5
    },
    live: {
      enabled: env.RH_LIVE_EXECUTION_ENABLED === "true",
      baseUrl: resolveProjectXApiBaseUrl(optionalTrimmed(env.RH_TOPSTEP_BASE_URL)),
      username: optionalTrimmed(env.RH_TOPSTEP_USERNAME),
      accountId: configuredAccountId,
      allowedAccountId: primaryAllowedAccountId,
      allowedAccountIds,
      allowedAccountLabel: primaryAllowedAccountLabel,
      allowedAccountLabels,
      apiKey: optionalTrimmed(env.RH_TOPSTEP_API_KEY),
      demoOnly: env.RH_TOPSTEP_DEMO_ONLY !== "false",
      readOnly: env.RH_TOPSTEP_READ_ONLY !== "false"
    },
    polygon: {
      enabled: env.RH_POLYGON_ENABLED === "true",
      apiKey: env.RH_POLYGON_API_KEY,
      baseUrl: env.RH_POLYGON_BASE_URL ?? "https://api.polygon.io"
    }
  };
}

export function redactConfigForDiagnostics(config: LabConfig): RedactedLabConfig {
  return {
    ...config,
    live: {
      ...config.live,
      apiKey: maskSecret(config.live.apiKey)
    },
    polygon: {
      ...config.polygon,
      apiKey: maskSecret(config.polygon.apiKey)
    }
  };
}
