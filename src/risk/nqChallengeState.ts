// nqChallengeState.ts — Persistent state for NQ Challenge Engine.
//
// Reads/writes engine state from disk so the challenge engine survives
// across paper-loop runs. Used by the EOD report script and demo execution.

import * as fs from "node:fs";
import * as path from "node:path";
import type { NQChallengeState } from "./nqChallengeEngine.js";

const STATE_DIR = path.resolve(
  process.env.RH_STATE_DIR ?? ".rumbling-hedge/state"
);
const STATE_FILE = path.join(STATE_DIR, "nq-challenge.json");

export function loadNQChallengeState(): NQChallengeState | null {
  try {
    if (!fs.existsSync(STATE_FILE)) return null;
    const raw = fs.readFileSync(STATE_FILE, "utf-8");
    return JSON.parse(raw) as NQChallengeState;
  } catch {
    console.error(`[nq-challenge] Failed to load state from ${STATE_FILE}`);
    return null;
  }
}

export function saveNQChallengeState(state: NQChallengeState): void {
  try {
    if (!fs.existsSync(STATE_DIR)) {
      fs.mkdirSync(STATE_DIR, { recursive: true });
    }
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), "utf-8");
  } catch (err) {
    console.error(`[nq-challenge] Failed to save state: ${err}`);
  }
}

export function getStateFile(): string {
  return STATE_FILE;
}
