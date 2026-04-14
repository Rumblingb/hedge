import type { PredictionFeeConfig } from "./types.js";

export const DEFAULT_PREDICTION_FEES: PredictionFeeConfig = {
  venueAFeePct: 2,
  venueBFeePct: 2,
  slippagePct: 0.5,
  minDisplayedSize: 100,
  watchThresholdPct: 3
};
