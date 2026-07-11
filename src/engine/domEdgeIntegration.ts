// Import the adjustment function
import { getDomEdgeAdjustment } from '../signals/domMicroEdge.js';

// Define the Shape of a StrategySignal (as per the existing system)
interface StrategySignal {
  confidence: number;
  contracts: number;
  meta: Record<string, any>;
}

/**
 * Applies DOM edge adjustment to a given signal.
 * @param signal The signal to adjust.
 * @returns A new signal with adjusted confidence and contracts, and domEdge meta added.
 */
export async function applyDomEdgeToSignal(signal: StrategySignal): Promise<StrategySignal> {
  const { confidenceBoost, sizingDelta } = await getDomEdgeAdjustment();

  // Create a copy of the signal to avoid mutating the original
  const adjustedSignal: StrategySignal = {
    ...signal,
    confidence: signal.confidence + confidenceBoost,
    contracts: signal.contracts + sizingDelta,
    meta: {
      ...signal.meta,
      domEdge: {
        confidenceBoost,
        sizingDelta,
        timestamp: new Date().toISOString(),
      },
    },
  };

  return adjustedSignal;
}
