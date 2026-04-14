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
  journalPath: "journals/prediction-fills.jsonl",
  onePerCandidate: true
};

export function buildExecutionConfigFromEnv(env: NodeJS.ProcessEnv = process.env): ExecutionConfig {
  const modeRaw = (env.BILL_PREDICTION_EXECUTION_MODE ?? "paper").toLowerCase();
  const mode = modeRaw === "live" ? "live" : "paper";
  const maxTotalStake = Number.parseFloat(env.BILL_PREDICTION_EXECUTION_MAX_STAKE ?? String(DEFAULT_CONFIG.maxTotalStake));
  const maxTotalMaxLoss = Number.parseFloat(
    env.BILL_PREDICTION_EXECUTION_MAX_MAX_LOSS ?? String(DEFAULT_CONFIG.maxTotalMaxLoss)
  );
  return {
    mode,
    maxTotalStake: Number.isFinite(maxTotalStake) && maxTotalStake > 0 ? maxTotalStake : DEFAULT_CONFIG.maxTotalStake,
    maxTotalMaxLoss:
      Number.isFinite(maxTotalMaxLoss) && maxTotalMaxLoss > 0 ? maxTotalMaxLoss : DEFAULT_CONFIG.maxTotalMaxLoss,
    stakeCurrency: env.BILL_PREDICTION_BANKROLL_CURRENCY ?? DEFAULT_CONFIG.stakeCurrency,
    journalPath: env.BILL_PREDICTION_FILLS_JOURNAL_PATH ?? DEFAULT_CONFIG.journalPath,
    onePerCandidate: (env.BILL_PREDICTION_EXECUTION_ONE_PER_CANDIDATE ?? "true").toLowerCase() !== "false"
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

  const alreadyPlaced = new Set(existingFills.map((fill) => fill.candidateId));

  for (const candidate of candidates) {
    if (!isExecutableCandidate(candidate)) {
      outcome.skipped.push({
        candidateId: candidate.candidateId,
        reason: `verdict=${candidate.verdict} sizing=${candidate.sizing ? "present" : "missing"}`
      });
      continue;
    }
    if (config.onePerCandidate && alreadyPlaced.has(candidate.candidateId)) {
      outcome.skipped.push({
        candidateId: candidate.candidateId,
        reason: "already-filled (one-per-candidate)"
      });
      continue;
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
    alreadyPlaced.add(candidate.candidateId);
  }

  return outcome;
}

export { appendFills };
