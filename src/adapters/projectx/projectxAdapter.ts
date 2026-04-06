import type { StrategySignal } from "../../domain.js";
import { HARD_GUARDRAIL_BOUNDS } from "../../risk/guardrails.js";
import { pointsToTicks, ticksToDollars } from "../../utils/markets.js";
import type { ExecutionAdapter, ExecutionReceipt } from "../topstep/topstepAdapter.js";

export interface ProjectXOrderSpec {
  accountId: string;
  symbol: string;
  side: "buy" | "sell";
  contracts: number;
  limitPrice: number;
  stopPrice: number;
  targetPrice: number;
  stopDistanceTicks: number;
  stopDistanceDollars: number;
  strategyTag: string;
}

export function buildProjectXOrderSpec(args: {
  signal: StrategySignal;
  accountId: string;
}): ProjectXOrderSpec {
  const { signal, accountId } = args;
  if (!Number.isInteger(signal.contracts) || signal.contracts <= 0) {
    throw new Error(`ProjectX order spec has invalid contracts: ${signal.contracts}`);
  }

  if (signal.contracts > HARD_GUARDRAIL_BOUNDS.maxContracts) {
    throw new Error(`ProjectX order spec breaches hard max contracts: ${signal.contracts}`);
  }

  const stopDistancePoints = Math.max(0.000001, Math.abs(signal.entry - signal.stop));
  const stopDistanceTicks = pointsToTicks(signal.symbol, stopDistancePoints);
  const stopDistanceDollars = ticksToDollars(signal.symbol, stopDistanceTicks, signal.contracts);

  return {
    accountId,
    symbol: signal.symbol,
    side: signal.side === "long" ? "buy" : "sell",
    contracts: signal.contracts,
    limitPrice: signal.entry,
    stopPrice: signal.stop,
    targetPrice: signal.target,
    stopDistanceTicks: Number(stopDistanceTicks.toFixed(4)),
    stopDistanceDollars: Number(stopDistanceDollars.toFixed(2)),
    strategyTag: signal.strategyId
  };
}

export class ProjectXLiveAdapter implements ExecutionAdapter {
  public constructor(private readonly config: { enabled: boolean; baseUrl?: string; accountId?: string; apiKey?: string }) {}

  private assertReady(): void {
    if (!this.config.enabled) {
      throw new Error("ProjectX live execution is disabled.");
    }

    if (!this.config.baseUrl || !this.config.accountId || !this.config.apiKey) {
      throw new Error("ProjectX live adapter is missing required credentials.");
    }
  }

  public async submit(signal: StrategySignal): Promise<ExecutionReceipt> {
    this.assertReady();
    throw new Error(`ProjectX submit is intentionally not implemented yet. Wire your reviewed client before trading ${signal.symbol}.`);
  }

  public async flattenAll(): Promise<void> {
    this.assertReady();
    throw new Error("ProjectX flatten is intentionally not implemented yet.");
  }
}