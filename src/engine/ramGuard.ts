import { execFile } from "node:child_process";
import { access, mkdir, unlink, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export type MemoryPressureLevel = "normal" | "warn" | "critical" | "unknown";

export interface RamGuardResult {
  command: "ram-guard";
  checkedAt: string;
  pressureLevel: MemoryPressureLevel;
  flagPath: string;
  flagActive: boolean;
  action: "no-change" | "wrote-flag" | "cleared-flag";
}

export function defaultRamGuardFlagPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.BILL_RAM_GUARD_FLAG_PATH ?? env.OPENCLAW_MEMORY_PRESSURE_FLAG_PATH ?? `${env.HOME ?? "."}/.openclaw/memory-pressure.flag`);
}

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

export async function readMemoryPressureLevel(): Promise<MemoryPressureLevel> {
  try {
    const { stdout } = await execFileAsync("memory_pressure", [], { timeout: 5000, encoding: "utf8" });
    const match = /System-wide memory free percentage:\s*(\d+)%/.exec(stdout);
    if (!match) return "unknown";
    const freePct = Number.parseInt(match[1]!, 10);
    if (freePct < 5) return "critical";
    if (freePct < 20) return "warn";
    return "normal";
  } catch {
    return "unknown";
  }
}

export async function isMemoryPressureActive(flagPath: string = defaultRamGuardFlagPath()): Promise<boolean> {
  return exists(flagPath);
}

export async function runRamGuard(args: {
  env?: NodeJS.ProcessEnv;
  now?: () => string;
  flagPath?: string;
  pressureLevel?: MemoryPressureLevel;
} = {}): Promise<RamGuardResult> {
  const checkedAt = args.now?.() ?? new Date().toISOString();
  const flagPath = resolve(args.flagPath ?? defaultRamGuardFlagPath(args.env));
  const pressureLevel = args.pressureLevel ?? await readMemoryPressureLevel();
  const alreadyFlagged = await exists(flagPath);
  let action: RamGuardResult["action"] = "no-change";
  let flagActive = alreadyFlagged;

  if (pressureLevel === "critical" || pressureLevel === "warn") {
    if (!alreadyFlagged) {
      await mkdir(dirname(flagPath), { recursive: true });
      await writeFile(flagPath, `${pressureLevel}\n${checkedAt}\n`, "utf8");
      action = "wrote-flag";
    }
    flagActive = true;
  } else if (pressureLevel === "normal" && alreadyFlagged) {
    await unlink(flagPath);
    action = "cleared-flag";
    flagActive = false;
  }

  return {
    command: "ram-guard",
    checkedAt,
    pressureLevel,
    flagPath,
    flagActive,
    action
  };
}
