import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export interface GraveyardEntry {
  id: string;
  title: string;
  status: "dead" | "cooling";
  reason: string;
  mechanics: string[];
  mechanicsHash?: string;
  parentId?: string;
  variantOf?: string;
  killedAt: string;
  killedBy: "proposals" | "manual" | "oos-failure";
  reviewAfter?: string;
}

export interface HypothesisGraveyard {
  version: 1;
  updatedAt: string;
  entries: GraveyardEntry[];
}

export function graveyardPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.BILL_GRAVEYARD_PATH ?? ".rumbling-hedge/research/graveyard.json");
}

export async function loadGraveyard(path?: string): Promise<HypothesisGraveyard> {
  try {
    const raw = await readFile(resolve(path ?? graveyardPath()), "utf8");
    return JSON.parse(raw) as HypothesisGraveyard;
  } catch {
    return { version: 1, updatedAt: new Date(0).toISOString(), entries: [] };
  }
}

export async function writeGraveyard(
  graveyard: HypothesisGraveyard,
  path?: string
): Promise<void> {
  const target = resolve(path ?? graveyardPath());
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify(graveyard, null, 2)}\n`, "utf8");
}

export async function buryHypothesis(args: {
  id: string;
  title: string;
  reason: string;
  mechanics?: string[];
  mechanicsHash?: string;
  parentId?: string;
  variantOf?: string;
  status?: "dead" | "cooling";
  killedBy?: GraveyardEntry["killedBy"];
  coolingDays?: number;
  graveyardFilePath?: string;
}): Promise<void> {
  const graveyard = await loadGraveyard(args.graveyardFilePath);
  const existingIdx = graveyard.entries.findIndex((e) => e.id === args.id);
  const now = new Date().toISOString();
  const status = args.status ?? "cooling";
  const reviewAfter =
    status === "cooling"
      ? new Date(Date.now() + (args.coolingDays ?? 30) * 86_400_000).toISOString()
      : undefined;

  const entry: GraveyardEntry = {
    id: args.id,
    title: args.title,
    status,
    reason: args.reason,
    mechanics: args.mechanics ?? [],
    ...(args.mechanicsHash ? { mechanicsHash: args.mechanicsHash } : {}),
    ...(args.parentId ? { parentId: args.parentId } : {}),
    ...(args.variantOf ? { variantOf: args.variantOf } : {}),
    killedAt: now,
    killedBy: args.killedBy ?? "manual",
    ...(reviewAfter ? { reviewAfter } : {})
  };

  if (existingIdx >= 0) {
    graveyard.entries[existingIdx] = entry;
  } else {
    graveyard.entries.push(entry);
  }
  graveyard.updatedAt = now;
  await writeGraveyard(graveyard, args.graveyardFilePath);
}

export function isInGraveyard(id: string, graveyard: HypothesisGraveyard): boolean {
  const entry = graveyard.entries.find((e) => e.id === id);
  if (!entry) return false;
  if (entry.status === "dead") return true;
  if (entry.status === "cooling" && entry.reviewAfter && new Date(entry.reviewAfter) > new Date()) {
    return true;
  }
  return false;
}

export function getGraveyardContextBlock(graveyard: HypothesisGraveyard): string {
  const active = graveyard.entries.filter((e) => {
    if (e.status === "dead") return true;
    if (e.status === "cooling" && e.reviewAfter && new Date(e.reviewAfter) > new Date()) {
      return true;
    }
    return false;
  });
  if (active.length === 0) return "";
  const lines = active
    .map(
      (e) =>
        `- "${e.title}" [${e.status}${e.reviewAfter ? `, review after ${e.reviewAfter.slice(0, 10)}` : ""}]: ${e.reason}`
    )
    .join("\n");
  return (
    "\nThe following hypotheses have been tested and found to have no demonstrable edge, or are in a cooling-off period after failure. " +
    "Do NOT re-propose them unless you articulate a materially different mechanism:\n" +
    lines +
    "\n"
  );
}
