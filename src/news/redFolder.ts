import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import type { MockHeadline } from "./mockNewsGate.js";

export interface RedFolderLoadResult {
  path: string;
  events: MockHeadline[];
  warnings: string[];
}

function normalizeEvent(raw: unknown): MockHeadline | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  const symbol = typeof item.symbol === "string" ? item.symbol.trim().toUpperCase() : "";
  const ts = typeof item.ts === "string"
    ? item.ts
    : typeof item.timestamp === "string"
      ? item.timestamp
      : "";
  const headline = typeof item.headline === "string"
    ? item.headline
    : typeof item.label === "string"
      ? item.label
      : typeof item.event === "string"
        ? item.event
        : "";
  const direction = item.direction === "long" || item.direction === "short" ? item.direction : "flat";
  const impact = item.impact === "high" || item.impact === "medium" || item.impact === "low" ? item.impact : "high";
  const probability = typeof item.probability === "number" && Number.isFinite(item.probability)
    ? item.probability
    : Number(item.probability ?? 0.75);

  if (!symbol || !ts || !headline || Number.isNaN(Date.parse(ts))) {
    return null;
  }

  return {
    symbol,
    ts,
    direction,
    probability: Math.max(0, Math.min(1, probability)),
    impact,
    headline
  };
}

function parseJsonEvents(raw: string): unknown[] {
  const parsed = JSON.parse(raw) as unknown;
  if (Array.isArray(parsed)) return parsed;
  if (parsed && typeof parsed === "object" && Array.isArray((parsed as Record<string, unknown>).events)) {
    return (parsed as { events: unknown[] }).events;
  }
  return [];
}

function parseJsonlEvents(raw: string): unknown[] {
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as unknown);
}

export async function loadRedFolderEvents(path?: string): Promise<RedFolderLoadResult> {
  const resolvedPath = resolve(path ?? process.env.BILL_RED_FOLDER_EVENTS_PATH ?? ".rumbling-hedge/research/news/red-folder-events.json");
  try {
    const raw = await readFile(resolvedPath, "utf8");
    const records = resolvedPath.endsWith(".jsonl") ? parseJsonlEvents(raw) : parseJsonEvents(raw);
    const events = records
      .map(normalizeEvent)
      .filter((event): event is MockHeadline => Boolean(event));
    const warnings = events.length === records.length
      ? []
      : [`ignored ${records.length - events.length} malformed red-folder event(s)`];
    return { path: resolvedPath, events, warnings };
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    return {
      path: resolvedPath,
      events: [],
      warnings: code === "ENOENT" ? [] : [`could not load red-folder events: ${(error as Error).message}`]
    };
  }
}
