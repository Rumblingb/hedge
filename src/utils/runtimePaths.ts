import { existsSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

function looksLikeRepoRoot(path: string): boolean {
  return existsSync(join(path, "package.json")) && existsSync(join(path, "src"));
}

function findRepoRoot(startDir: string): string | null {
  let current = resolve(startDir);
  while (true) {
    if (looksLikeRepoRoot(current)) {
      return current;
    }

    const parent = dirname(current);
    if (parent === current) {
      return null;
    }
    current = parent;
  }
}

export function resolveRuntimeRepoRoot(args: {
  importMetaUrl: string;
  cwd?: string;
  explicitBaseDir?: string;
  env?: NodeJS.ProcessEnv;
}): string {
  if (args.explicitBaseDir) {
    return resolve(args.explicitBaseDir);
  }

  const envRoot = args.env?.BILL_ROOT ?? args.env?.HEDGE_REPO_ROOT;
  if (typeof envRoot === "string" && envRoot.trim().length > 0) {
    return resolve(envRoot);
  }

  const cwdRoot = findRepoRoot(args.cwd ?? process.cwd());
  if (cwdRoot) {
    return cwdRoot;
  }

  const moduleRoot = findRepoRoot(dirname(fileURLToPath(args.importMetaUrl)));
  if (moduleRoot) {
    return moduleRoot;
  }

  return resolve(dirname(fileURLToPath(args.importMetaUrl)), "..");
}

export function resolveRepoPathFromRoot(args: {
  importMetaUrl: string;
  path: string;
  cwd?: string;
  baseDir?: string;
  env?: NodeJS.ProcessEnv;
}): string {
  if (isAbsolute(args.path)) {
    return resolve(args.path);
  }

  return resolve(
    resolveRuntimeRepoRoot({
      importMetaUrl: args.importMetaUrl,
      cwd: args.cwd,
      explicitBaseDir: args.baseDir,
      env: args.env
    }),
    args.path
  );
}
