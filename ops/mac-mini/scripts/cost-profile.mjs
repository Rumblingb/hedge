import os from "node:os";

const asInt = (value, fallback) => {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const profile = {
  command: "bill-cost-profile",
  timestamp: new Date().toISOString(),
  host: {
    hostname: os.hostname(),
    platform: process.platform,
    arch: process.arch
  },
  models: {
    localLight: process.env.BILL_LOCAL_LIGHT_MODEL ?? "ollama/qwen2.5-coder:7b",
    localHeavy: process.env.BILL_LOCAL_HEAVY_MODEL ?? "ollama/qwen2.5-coder:14b",
    cloudProvider: process.env.BILL_CLOUD_PROVIDER ?? "openrouter",
    cloudBaseUrl: process.env.BILL_CLOUD_BASE_URL ?? "https://openrouter.ai/api/v1",
    cloudReview: process.env.BILL_CLOUD_REVIEW_MODEL ?? "deepseek/deepseek-v3.2",
    deepCloudReview: process.env.BILL_CLOUD_DEEP_REVIEW_MODEL ?? "deepseek/deepseek-v3.2-speciale"
  },
  limits: {
    maxHeavyJobs: asInt(process.env.BILL_MAX_HEAVY_JOBS, 1),
    maxCloudReviewsPerDay: asInt(process.env.BILL_MAX_CLOUD_REVIEWS_PER_DAY, 3),
    marketHoursPriorityOnly: process.env.BILL_MARKET_PRIORITY_ONLY !== "false"
  },
  schedulePolicy: {
    nativeJobsFirst: true,
    scheduledLlmLoop: process.env.BILL_SCHEDULED_LLM_LOOP ?? "weekly",
    predictionCollectEnabled: process.env.BILL_ENABLE_PREDICTION_COLLECT === "true",
    predictionScanEnabled: process.env.BILL_ENABLE_PREDICTION_SCAN === "true",
    paperLoopEnabled: process.env.BILL_ENABLE_PAPER_LOOP === "true"
  },
  recommendations: []
};

if (profile.limits.maxHeavyJobs > 1) {
  profile.recommendations.push("Set BILL_MAX_HEAVY_JOBS back to 1 unless the machine is upgraded.");
}

if (profile.limits.maxCloudReviewsPerDay > 6) {
  profile.recommendations.push("Cloud review budget is high; lower it unless live promotion work is active.");
}

if (profile.schedulePolicy.scheduledLlmLoop === "daily") {
  profile.recommendations.push("Daily scheduled LLM loops are likely wasteful when native Bill jobs are already active.");
}

console.log(JSON.stringify(profile, null, 2));
