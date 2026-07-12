/**
 * Pipeline Gate System — sequential strategy lifecycle with hard gates.
 *
 * Inspired by ochenryceo/trading-factory (MIT).
 *
 * Each strategy starts at IDEA and progresses through stages sequentially.
 * At each stage, a gate defines minimum metrics required to promote.
 * 3 consecutive demotions → RETIRED.
 * Kill switch → demotes to BACKTEST.
 *
 * Stages: IDEA → FAST_VALIDATION → BACKTEST → VALIDATION → PAPER
 *         → DEGRADATION → DEPENDENCY → MICRO_LIVE → FULL_LIVE
 */

// ── Pipeline Stage Enum ──

export enum PipelineStage {
  IDEA = "IDEA",
  FAST_VALIDATION = "FAST_VALIDATION",
  BACKTEST = "BACKTEST",
  VALIDATION = "VALIDATION",
  PAPER = "PAPER",
  DEGRADATION = "DEGRADATION",
  DEPENDENCY = "DEPENDENCY",
  MICRO_LIVE = "MICRO_LIVE",
  FULL_LIVE = "FULL_LIVE",
}

export const STAGE_ORDER: PipelineStage[] = Object.values(PipelineStage);

// ── Strategy Status ──

export enum StrategyStatus {
  ACTIVE = "ACTIVE",
  PAUSED = "PAUSED",
  KILLED = "KILLED",
  RETIRED = "RETIRED",
  PENDING = "PENDING",
  REJECTED_FAST = "REJECTED_FAST",
}

// ── Event Types (audit trail) ──

export enum PipelineEvent {
  STRATEGY_CREATED = "STRATEGY_CREATED",
  FAST_VALIDATION_STARTED = "FAST_VALIDATION_STARTED",
  FAST_VALIDATION_PASSED = "FAST_VALIDATION_PASSED",
  FAST_VALIDATION_FAILED = "FAST_VALIDATION_FAILED",
  STAGE_PROMOTED = "STAGE_PROMOTED",
  STAGE_REJECTED = "STAGE_REJECTED",
  STRATEGY_KILLED = "STRATEGY_KILLED",
  STRATEGY_DEMOTED = "STRATEGY_DEMOTED",
  STRATEGY_RETIRED = "STRATEGY_RETIRED",
  OVERRIDE_ATTEMPTED = "OVERRIDE_ATTEMPTED",
  OVERRIDE_APPROVED = "OVERRIDE_APPROVED",
  OVERRIDE_REJECTED = "OVERRIDE_REJECTED",
  TRADE_APPROVED = "TRADE_APPROVED",
  TRADE_REJECTED = "TRADE_REJECTED",
  RISK_LIMIT_HIT = "RISK_LIMIT_HIT",
}

// ── Metrics per Stage ──

export interface StageMetrics {
  winRate?: number;
  sharpe?: number;
  drawdown?: number;
  tradeCount?: number;
  durationDays?: number;
  profitFactor?: number;
  expectancy?: number;
}

// ── Gate Definition ──

export interface GateRequirement {
  minWinRate?: number;
  minSharpe?: number;
  maxDrawdown?: number;
  minTrades?: number;
  minDurationDays?: number;
  regimesRequired?: string[];
  degradationAxes?: string[];
  dependencyComponents?: string[];
}

const STAGE_GATES: Record<PipelineStage, GateRequirement> = {
  [PipelineStage.IDEA]: {},
  [PipelineStage.FAST_VALIDATION]: {
    minWinRate: 0.45,
    minTrades: 30,
    maxDrawdown: 0.12,
  },
  [PipelineStage.BACKTEST]: {
    minWinRate: 0.40,
    minSharpe: 0.5,
    maxDrawdown: 0.10,
    minTrades: 500,
  },
  [PipelineStage.VALIDATION]: {
    regimesRequired: ["trending", "ranging", "volatile"],
  },
  [PipelineStage.PAPER]: {
    minDurationDays: 14,
    minWinRate: 0.35,
    minSharpe: 0.3,
    maxDrawdown: 0.10,
  },
  [PipelineStage.DEGRADATION]: {
    degradationAxes: ["parameter", "execution", "data", "regime"],
  },
  [PipelineStage.DEPENDENCY]: {
    dependencyComponents: ["time_filter", "volume_filter", "secondary_indicator"],
  },
  [PipelineStage.MICRO_LIVE]: {
    minWinRate: 0.35,
    minSharpe: 0.3,
    maxDrawdown: 0.08,
  },
  [PipelineStage.FULL_LIVE]: {
    minWinRate: 0.35,
    minSharpe: 0.3,
    maxDrawdown: 0.08,
  },
};

// ── Promotion / Demotion Maps ──

function buildPromotionMap(): Map<PipelineStage, PipelineStage> {
  const m = new Map<PipelineStage, PipelineStage>();
  for (let i = 0; i < STAGE_ORDER.length - 1; i++) {
    m.set(STAGE_ORDER[i], STAGE_ORDER[i + 1]);
  }
  return m;
}

function buildDemotionMap(): Map<PipelineStage, PipelineStage> {
  const m = new Map<PipelineStage, PipelineStage>();
  for (const stage of STAGE_ORDER) {
    const idx = STAGE_ORDER.indexOf(stage);
    m.set(stage, STAGE_ORDER[Math.max(idx - 1, 0)]);
  }
  return m;
}

const PROMOTION_MAP = buildPromotionMap();
const DEMOTION_MAP = buildDemotionMap();

// ── Transition Result ──

export interface TransitionResult {
  allowed: boolean;
  fromStage: PipelineStage;
  toStage: PipelineStage | null;
  event: PipelineEvent | null;
  reason: string;
  newStatus?: StrategyStatus;
  failures?: string[];
}

// ── Can Promote ──

export function canPromote(
  currentStage: PipelineStage,
  metrics?: Partial<StageMetrics>,
  regimes?: string[],
): TransitionResult {
  if (currentStage === PipelineStage.FULL_LIVE) {
    return {
      allowed: false,
      fromStage: currentStage,
      toStage: null,
      event: null,
      reason: "Already at FULL_LIVE — no further promotion.",
    };
  }

  const target = PROMOTION_MAP.get(currentStage);
  if (!target) {
    return {
      allowed: false,
      fromStage: currentStage,
      toStage: null,
      event: null,
      reason: `No promotion target from ${currentStage}.`,
    };
  }

  const gate = STAGE_GATES[currentStage];
  const failures: string[] = [];

  if (gate.minWinRate !== undefined && (metrics?.winRate ?? 0) < gate.minWinRate) {
    failures.push(`winRate ${metrics?.winRate?.toFixed(2)} < ${gate.minWinRate}`);
  }
  if (gate.minSharpe !== undefined && (metrics?.sharpe ?? 0) < gate.minSharpe) {
    failures.push(`sharpe ${metrics?.sharpe?.toFixed(2)} < ${gate.minSharpe}`);
  }
  if (gate.maxDrawdown !== undefined && (metrics?.drawdown ?? 1) > gate.maxDrawdown) {
    failures.push(`drawdown ${metrics?.drawdown?.toFixed(2)} > ${gate.maxDrawdown}`);
  }
  if (gate.minTrades !== undefined && (metrics?.tradeCount ?? 0) < gate.minTrades) {
    failures.push(`trades ${metrics?.tradeCount} < ${gate.minTrades}`);
  }
  if (gate.regimesRequired && regimes) {
    const missing = gate.regimesRequired.filter((r) => !regimes.includes(r));
    if (missing.length > 0) {
      failures.push(`missing regimes: ${missing.join(", ")}`);
    }
  }

  if (failures.length > 0) {
    return {
      allowed: false,
      fromStage: currentStage,
      toStage: target,
      event: PipelineEvent.STAGE_REJECTED,
      reason: `Gate failed: ${failures.join("; ")}`,
      failures,
    };
  }

  return {
    allowed: true,
    fromStage: currentStage,
    toStage: target,
    event: PipelineEvent.STAGE_PROMOTED,
    reason: `Promoted ${currentStage} → ${target}`,
  };
}

// ── Demote ──

export function demote(
  currentStage: PipelineStage,
  reason: string = "Performance degradation",
  consecutiveDemotions: number = 0,
): TransitionResult {
  if (consecutiveDemotions >= 2) {
    const target = PipelineStage.IDEA;
    return {
      allowed: true,
      fromStage: currentStage,
      toStage: target,
      event: PipelineEvent.STRATEGY_RETIRED,
      reason: `3 consecutive demotions — permanently retired. ${reason}`,
      newStatus: StrategyStatus.RETIRED,
    };
  }

  const target = DEMOTION_MAP.get(currentStage) ?? PipelineStage.IDEA;
  return {
    allowed: true,
    fromStage: currentStage,
    toStage: target,
    event: PipelineEvent.STRATEGY_DEMOTED,
    reason,
  };
}

// ── Kill Switch ──

export function killSwitch(
  currentStage: PipelineStage,
  reason: string,
): TransitionResult {
  const target = PipelineStage.BACKTEST;
  return {
    allowed: true,
    fromStage: currentStage,
    toStage: target,
    event: PipelineEvent.STRATEGY_KILLED,
    reason: `Kill switch: ${reason}`,
    newStatus: StrategyStatus.KILLED,
  };
}

// ── Override ──

export function overrideGate(
  currentStage: PipelineStage,
  requestedBy: string,
  reason: string,
): { result: "PENDING" | "APPROVED" | "REJECTED"; reason: string } {
  if (requestedBy === "founder") {
    return { result: "APPROVED", reason: "Founder override — bypass gate." };
  }
  return { result: "PENDING", reason: `Override requested by ${requestedBy}: ${reason}` };
}

// ── Pipeline State per Strategy ──

export interface StrategyPipelineState {
  strategyId: string;
  currentStage: PipelineStage;
  status: StrategyStatus;
  consecutiveDemotions: number;
  metrics: StageMetrics;
  history: Array<{
    event: PipelineEvent;
    fromStage?: PipelineStage;
    toStage?: PipelineStage;
    reason: string;
    timestamp: string;
  }>;
}

// ── Compatibility with old Classification system ──

/**
 * Map pipeline stage back to old GOLD/SILVER/BRONZE for existing code.
 * Only FULL_LIVE and MICRO_LIVE translate to GOLD.
 */
export function stageToLegacyClassification(stage: PipelineStage): "GOLD" | "SILVER" | "BRONZE" | "SKELETON" | "QUARANTINED" {
  switch (stage) {
    case PipelineStage.FULL_LIVE:
    case PipelineStage.MICRO_LIVE:
      return "GOLD";
    case PipelineStage.PAPER:
    case PipelineStage.DEGRADATION:
    case PipelineStage.DEPENDENCY:
      return "SILVER";
    case PipelineStage.BACKTEST:
    case PipelineStage.VALIDATION:
      return "BRONZE";
    case PipelineStage.FAST_VALIDATION:
      return "SKELETON";
    case PipelineStage.IDEA:
    default:
      return "QUARANTINED";
  }
}
