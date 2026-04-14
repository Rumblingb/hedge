import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");
const historyPath = path.resolve(repoRoot, process.env.BILL_PREDICTION_CYCLE_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-cycle-history.jsonl");
const limitArg = Number(process.argv[2] ?? "10");
const limit = Number.isFinite(limitArg) && limitArg > 0 ? Math.floor(limitArg) : 10;

let items = [];
if (existsSync(historyPath)) {
  const raw = await readFile(historyPath, "utf8");
  items = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .slice(-limit);
}

console.log(JSON.stringify({
  command: "prediction-iterations",
  historyPath,
  count: items.length,
  items
}, null, 2));
