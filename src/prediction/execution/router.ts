import { appendFile, mkdir, readFile } from "node:fs/promises";
import { dirname } from "node:path";
import type { PredictionCandidate } from "../types.js";
import { evaluateLiveGate } from "./liveGate.js";
import {
  isExecutableCandidate,
  sizingToFill,
  type ExecutionConfig,
  type ExecutionOutcome,
  type PaperFill
} from "./types.js";

const DEFAULT_CONFIG: ExecutionConfig = {
  mode: "paper",
  maxTotalStake: 100,
  maxTotalMaxLoss: 50,
  stakeCurrency: "GBP",
  journalPath: ".rumbling-hedge/runtime/prediction/fills.jsonl",
  onePerCandidate: true,
  repeatFillCooldownHours: 24,
  demoSeedFill: false,
  demoStake: 1
};

export function buildExecutionConfigFromEnv(env: NodeJS.ProcessEnv = process.env): ExecutionConfig {
  const modeRaw = (env.BILL_PREDICTION_EXECUTION_MODE ?? "paper").toLowerCase();
  const mode = modeRaw === "live" ? "live" : "paper";
  const maxTotalStake = Number.parseFloat(env.BILL_PREDICTION_EXECUTION_MAX_STAKE ?? String(DEFAULT_CONFIG.maxTotalStake));
  const maxTotalMaxLoss = Number.parseFloat(
    env.BILL_PREDICTION_EXECUTION_MAX_MAX_LOSS ?? String(DEFAULT_CONFIG.maxTotalMaxLoss)
  );
  const demoStakeRaw = Number.parseFloat(env.BILL_PREDICTION_DEMO_SEED_STAKE ?? String(DEFAULT_CONFIG.demoStake));
  const repeatFillCooldownHoursRaw = Number.parseFloat(
    env.BILL_PREDICTION_EXECUTION_REPEAT_FILL_HOURS ?? String(DEFAULT_CONFIG.repeatFillCooldownHours)
  );
  const demoSeedFill =
    mode === "paper" && (env.BILL_PREDICTION_DEMO_SEED_FILL ?? "false").toLowerCase() === "true";
  return {
    mode,
    maxTotalStake: Number.isFinite(maxTotalStake) && maxTotalStake > 0 ? maxTotalStake : DEFAULT_CONFIG.maxTotalStake,
    maxTotalMaxLoss:
      Number.isFinite(maxTotalMaxLoss) && maxTotalMaxLoss > 0 ? maxTotalMaxLoss : DEFAULT_CONFIG.maxTotalMaxLoss,
    stakeCurrency: env.BILL_PREDICTION_BANKROLL_CURRENCY ?? DEFAULT_CONFIG.stakeCurrency,
    journalPath: env.BILL_PREDICTION_FILLS_JOURNAL_PATH ?? DEFAULT_CONFIG.journalPath,
    onePerCandidate: (env.BILL_PREDICTION_EXECUTION_ONE_PER_CANDIDATE ?? "true").toLowerCase() !== "false",
    repeatFillCooldownHours:
      Number.isFinite(repeatFillCooldownHoursRaw) && repeatFillCooldownHoursRaw >= 0
        ? repeatFillCooldownHoursRaw
        : DEFAULT_CONFIG.repeatFillCooldownHours,
    demoSeedFill,
    demoStake: Number.isFinite(demoStakeRaw) && demoStakeRaw > 0 ? demoStakeRaw : DEFAULT_CONFIG.demoStake
  };
}

export async function readFillsJournal(path: string): Promise<PaperFill[]> {
  try {
    const raw = await readFile(path, "utf8");
    return raw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line) as PaperFill);
  } catch {
    return [];
  }
}

async function appendFills(path: string, fills: PaperFill[]): Promise<void> {
  if (fills.length === 0) return;
  await mkdir(dirname(path), { recursive: true });
  const payload = fills.map((fill) => JSON.stringify(fill)).join("\n");
  await appendFile(path, `${payload}\n`, "utf8");
}

export interface RouteOptions {
  config?: ExecutionConfig;
  env?: NodeJS.ProcessEnv;
  now?: () => Date;
  existingFills?: PaperFill[];
}

/**
 * Stage fills from the top candidates. Paper mode always proceeds (subject to
 * config caps). Live mode requires every check in `evaluateLiveGate` to pass;
 * otherwise every candidate is skipped with a gate-refused reason.
 *
 * Returns an outcome with placed + skipped entries and totals. Callers should
 * persist `placed` via `appendFills` when they want fills durable.
 */
export function routePredictionCandidates(
  candidates: PredictionCandidate[],
  options: RouteOptions = {}
): ExecutionOutcome {
  const config = options.config ?? DEFAULT_CONFIG;
  const env = options.env ?? process.env;
  const now = options.now ?? (() => new Date());
  const existingFills = options.existingFills ?? [];

  const outcome: ExecutionOutcome = {
    placed: [],
    skipped: [],
    totalStake: 0,
    totalMaxLoss: 0,
    mode: config.mode
  };

  if (config.mode === "live") {
    const gate = evaluateLiveGate(env);
    if (!gate.ok) {
      for (const candidate of candidates) {
        outcome.skipped.push({
          candidateId: candidate.candidateId,
          reason: `live gate refused: ${gate.failures.join("; ")}`
        });
      }
      return outcome;
    }
  }

  const latestFillByCandidate = new Map();
  for (const fill of existingFills) {
    const fillTs = Date.parse(fill.ts);
    const current = latestFillByCandidate.get(fill.candidateId);
    if (!current || fillTs > current.tsMs) {
      latestFillByCandidate.set(fill.candidateId, { tsMs: fillTs });
    }
  }
  const cooldownMs = Math.max(0, Number(config.repeatFillCooldownHours ?? 0)) * 60 * 60 * 1000;

  for (const candidate of candidates) {
    if (!isExecutableCandidate(candidate)) {
      outcome.skipped.push({
        candidateId: candidate.candidateId,
        reason: `verdict=${candidate.verdict} sizing=${candidate.sizing ? "present" : "missing"}`
      });
      continue;
    }
    if (config.onePerCandidate) {
      const latestFill = latestFillByCandidate.get(candidate.candidateId);
      if (latestFill) {
        if (cooldownMs === 0) {
          outcome.skipped.push({
            candidateId: candidate.candidateId,
            reason: "already-filled (one-per-candidate)"
          });
          continue;
        }
        const ageMs = now().getTime() - latestFill.tsMs;
        if (ageMs < cooldownMs) {
          outcome.skipped.push({
            candidateId: candidate.candidateId,
            reason: `already-filled within ${config.repeatFillCooldownHours}h cooldown`
          });
          continue;
        }
      }
    }
    const sizing = candidate.sizing!;
    if (outcome.totalStake + sizing.recommendedStake > config.maxTotalStake) {
      outcome.skipped.push({
        candidateId: candidate.candidateId,
        reason: `stake ceiling ${config.maxTotalStake} ${config.stakeCurrency} would be breached`
      });
      continue;
    }
    if (outcome.totalMaxLoss + sizing.maxLoss > config.maxTotalMaxLoss) {
      outcome.skipped.push({
        candidateId: candidate.candidateId,
        reason: `max-loss ceiling ${config.maxTotalMaxLoss} ${config.stakeCurrency} would be breached`
      });
      continue;
    }

    const fill = sizingToFill(candidate, sizing, config.mode, now());
    outcome.placed.push(fill);
    outcome.totalStake += fill.stake;
    outcome.totalMaxLoss += fill.maxLoss;
    latestFillByCandidate.set(candidate.candidateId, { tsMs: Date.parse(fill.ts) });
  }

  if (
    config.mode === "paper" &&
    config.demoSeedFill &&
    outcome.placed.length === 0 &&
    candidates.length > 0
  ) {
    const seed = [...candidates].sort((a, b) => (b.matchScore ?? 0) - (a.matchScore ?? 0))[0];
    const stake = Math.min(config.demoStake ?? DEFAULT_CONFIG.demoStake ?? 1, config.maxTotalStake);
    if (stake > 0 && !latestFillByCandidate.has(seed.candidateId)) {
      const ts = now();
      const price = seed.sizing?.entryPrice ?? 0.5;
      const refPrice = seed.sizing?.referencePrice ?? price;
      const consensus = seed.sizing?.consensusPrice ?? (price + refPrice) / 2;
      const fill: PaperFill = {
        fillId: `${seed.candidateId}-demo-${ts.toISOString()}`,
        ts: ts.toISOString(),
        mode: "paper",
        candidateId: seed.candidateId,
        venue: seed.sizing?.venue ?? seed.venueA,
        referenceVenue: seed.sizing?.referenceVenue ?? seed.venueB,
        marketQuestion: seed.eventTitleA ?? seed.eventTitleB ?? seed.candidateId,
        outcomeLabel: seed.outcomeA ?? seed.outcomeB ?? "yes",
        side: "yes",
        price,
        referencePrice: refPrice,
        consensusPrice: consensus,
        stake,
        stakeCurrency: seed.sizing?.bankrollCurrency ?? config.stakeCurrency,
        impliedEdgePct: seed.sizing?.impliedEdgePct ?? seed.netEdgePct,
        expectedValue: seed.sizing?.expectedValue ?? 0,
        maxLoss: stake,
        rewardRiskRatio: seed.sizing?.rewardRiskRatio ?? 0,
        reasons: [...(seed.reasons ?? []), "demo-seed-fill"],
        demo: true
      };
      outcome.placed.push(fill);
      outcome.totalStake += fill.stake;
      outcome.totalMaxLoss += fill.maxLoss;
    }
  }

  return outcome;
}

export { appendFills };
