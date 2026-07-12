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

function splitPathList(value: string | undefined): string[] {
  return (value ?? "")
    .split(/[,\n]/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function resolveMarketDataPath(args: {
  importMetaUrl: string;
  path: string;
  cwd?: string;
  baseDir?: string;
  env?: NodeJS.ProcessEnv;
}): string {
  const requestedPath = args.path.trim();
  if (isAbsolute(requestedPath)) {
    return resolve(requestedPath);
  }

  const cwdPath = resolve(args.cwd ?? process.cwd(), requestedPath);
  if (existsSync(cwdPath)) {
    return cwdPath;
  }

  const repoPath = resolveRepoPathFromRoot({
    importMetaUrl: args.importMetaUrl,
    path: requestedPath,
    cwd: args.cwd,
    baseDir: args.baseDir,
    env: args.env
  });
  if (existsSync(repoPath)) {
    return repoPath;
  }

  const fileName = requestedPath.split(/[\\/]/).filter(Boolean).at(-1);
  if (!fileName) {
    return repoPath;
  }

  const fallbackRoots = [
    ...splitPathList(args.env?.BILL_DATA_FREE_FALLBACK_DIR),
    ...splitPathList(args.env?.BILL_FUTURES_COLD_DATA_ROOT),
    "/Users/brain/mnt/agentpay-hdd/datasets/rumbling-hedge/data/free/free",
    "/Users/brain/mnt/agentpay-hdd/cold-data/rumbling-hedge/data/free/free",
    "/Users/brain/mnt/agentpay-hdd/rumbling-hedge/data/free/free",
    "/Volumes/Seagate Expansion Drive/rumbling-hedge/data/free/free"
  ];

  for (const root of fallbackRoots) {
    const candidate = resolve(root, fileName);
    if (existsSync(candidate)) {
      return candidate;
    }
  }

  return repoPath;
}
