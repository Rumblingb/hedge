#!/usr/bin/env node
/**
 * preMarketDecisionWriter.ts — Generates pre_trade_decision.json before NY open.
 * Run once at ~09:00 ET to set the day's go/no-go posture.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { existsSync, readFileSync } from "node:fs";

const STATE_DIR = join(process.cwd(), ".rumbling-hedge/state");
const OUTPUT = join(STATE_DIR, "pre_trade_decision.json");

async function main() {
  await mkdir(STATE_DIR, { recursive: true });

  const now = new Date();
  const hourET = now.getUTCHours() - 4;
  const minuteET = now.getUTCMinutes();

  // Read GEX for direction bias
  let direction: "LONG" | "SHORT" | "FLAT" = "FLAT";
  let conviction: "HIGH" | "MEDIUM" | "LOW" = "MEDIUM";
  let contracts = 1;

  // Check GEX levels
  try {
    const gexPath = join(STATE_DIR, "gex_levels.json");
    if (existsSync(gexPath)) {
      const gex = JSON.parse(readFileSync(gexPath, "utf8"));
      const gammaFlip = gex.gammaFlip;
      const callWall = gex.callWall;
      const putWall = gex.putWall;
      // If price is above gamma flip → bullish
      // If price is below gamma flip → bearish
      if (gammaFlip && callWall && putWall) {
        // Use GEX for bias if clear
        direction = gex.gammaFlip > gex.currentPrice ? "SHORT" : "LONG";
      }
    }
  } catch {}

  // Check inside-day gate
  const insideDayPath = join(STATE_DIR, "inside_day_prediction.json");
  let insideDayProb = 0;
  try {
    if (existsSync(insideDayPath)) {
      const id = JSON.parse(readFileSync(insideDayPath, "utf8"));
      insideDayProb = id.probability || 0;
    }
  } catch {}

  if (direction === "FLAT") {
    direction = "LONG"; // Default bias if no GEX data
  }

  const decision = {
    timestamp: now.toISOString(),
    decision: "TRADE",
    direction,
    conviction,
    contracts: 1,
    sl_pts: 30,
    tp1_pts: 50,
    tp2_pts: 100,
    trail_pts: 30,
    account_split: {},
    warnings: [],
    insideDayProbability: insideDayProb,
    macroContext: undefined,
  };

  await writeFile(OUTPUT, JSON.stringify(decision, null, 2) + "\n");
  console.log(`[preMarketDecision] Written: ${direction} ${contracts} MNQ | Inside-day: ${(insideDayProb * 100).toFixed(0)}%`);
}

main().catch(console.error);
