import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

export interface KillSwitchState {
  active: boolean;
  activatedAt: string | null;
  reason: string | null;
}

const DEFAULT_KILL_SWITCH_STATE: KillSwitchState = {
  active: false,
  activatedAt: null,
  reason: null
};

export async function readKillSwitch(path: string): Promise<KillSwitchState> {
  try {
    const raw = await readFile(path, "utf8");
    const parsed = JSON.parse(raw) as Partial<KillSwitchState>;
    return {
      active: parsed.active === true,
      activatedAt: parsed.activatedAt ?? null,
      reason: parsed.reason ?? null
    };
  } catch {
    return { ...DEFAULT_KILL_SWITCH_STATE };
  }
}

export async function writeKillSwitch(args: {
  path: string;
  active: boolean;
  reason?: string;
}): Promise<KillSwitchState> {
  const nextState: KillSwitchState = args.active
    ? {
        active: true,
        activatedAt: new Date().toISOString(),
        reason: args.reason?.trim() || "Manual force kill activated."
      }
    : {
        active: false,
        activatedAt: null,
        reason: args.reason?.trim() || null
      };

  await mkdir(dirname(args.path), { recursive: true });
  await writeFile(args.path, `${JSON.stringify(nextState, null, 2)}\n`, "utf8");
  return nextState;
}
