import { mkdir, stat, statfs, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import os from "node:os";
import { dirname, join, parse, resolve } from "node:path";

const execFileAsync = promisify(execFile);
const GIB = 1024 ** 3;

export type TimesFmReadinessStatus = "missing" | "blocked" | "ready";

export interface TimesFmPackageStatus {
  python: {
    ok: boolean;
    version: string | null;
    executable: string;
    error?: string;
  };
  timesfm: {
    installed: boolean;
    version: string | null;
  };
  torch: {
    installed: boolean;
    version: string | null;
    cudaAvailable: boolean;
    mpsAvailable: boolean;
  };
}

export interface TimesFmReadiness {
  command: "timesfm-status";
  ts: string;
  status: TimesFmReadinessStatus;
  role: "research-only";
  repo: {
    url: string;
    license: string;
    auditedAt: string;
    safetySummary: string;
  };
  model: {
    id: string;
    version: string;
    backend: "torch";
    requiresHuggingFaceWeights: boolean;
    weightsApproxGiB: number;
    cacheDir: string;
    cachePresent: boolean;
  };
  runtime: {
    python: TimesFmPackageStatus["python"];
    packages: {
      timesfm: TimesFmPackageStatus["timesfm"];
      torch: TimesFmPackageStatus["torch"];
    };
    memory: {
      totalGiB: number;
      freeGiB: number;
      recommendedGiB: number;
    };
    disk: {
      path: string;
      availableGiB: number;
      recommendedGiB: number;
    } | null;
  };
  config: {
    outputDir: string;
    defaultCsvPath: string;
    maxContext: number;
    horizon: number;
    batchSize: number;
    allowDownload: boolean;
  };
  blockers: string[];
  warnings: string[];
  nextCommands: string[];
  hermesSummary: string;
}

function round(value: number): number {
  return Number(value.toFixed(2));
}

function modelCacheDir(modelId: string, env: NodeJS.ProcessEnv): string {
  const hfHome = env.HF_HOME ?? join(os.homedir(), ".cache", "huggingface");
  const escaped = modelId.replace("/", "--");
  return resolve(hfHome, "hub", `models--${escaped}`);
}

async function directoryExists(path: string): Promise<boolean> {
  try {
    return (await stat(path)).isDirectory();
  } catch {
    return false;
  }
}

async function nearestExistingDir(path: string): Promise<string> {
  let target = resolve(path);
  const root = parse(target).root;
  while (!(await directoryExists(target)) && target !== root) {
    target = dirname(target);
  }
  return target;
}

async function diskFor(path: string, recommendedGiB: number): Promise<TimesFmReadiness["runtime"]["disk"]> {
  try {
    const target = await nearestExistingDir(path);
    const stats = await statfs(target);
    return {
      path: target,
      availableGiB: round((Number(stats.bavail) * Number(stats.bsize)) / GIB),
      recommendedGiB
    };
  } catch {
    return null;
  }
}

async function inspectPythonPackages(python: string): Promise<TimesFmPackageStatus> {
  const script = [
    "import importlib.metadata as md, importlib.util, json, sys",
    "def pkg(name):",
    "  installed = importlib.util.find_spec(name) is not None",
    "  version = None",
    "  if installed:",
    "    try: version = md.version(name)",
    "    except Exception: version = 'unknown'",
    "  return {'installed': installed, 'version': version}",
    "timesfm = pkg('timesfm')",
    "torch = pkg('torch')",
    "cuda = False",
    "mps = False",
    "if torch['installed']:",
    "  try:",
    "    import torch as _torch",
    "    cuda = bool(_torch.cuda.is_available())",
    "    mps = bool(getattr(getattr(_torch, 'backends', None), 'mps', None) and _torch.backends.mps.is_available())",
    "  except Exception:",
    "    pass",
    "print(json.dumps({'python': sys.version.split()[0], 'timesfm': timesfm, 'torch': {**torch, 'cudaAvailable': cuda, 'mpsAvailable': mps}}))"
  ].join("\n");

  try {
    const { stdout } = await execFileAsync(python, ["-c", script], { timeout: 5000 });
    const parsed = JSON.parse(stdout) as {
      python: string;
      timesfm: TimesFmPackageStatus["timesfm"];
      torch: TimesFmPackageStatus["torch"];
    };
    return {
      python: {
        ok: true,
        version: parsed.python,
        executable: python
      },
      timesfm: parsed.timesfm,
      torch: parsed.torch
    };
  } catch (error) {
    return {
      python: {
        ok: false,
        version: null,
        executable: python,
        error: error instanceof Error ? error.message : String(error)
      },
      timesfm: {
        installed: false,
        version: null
      },
      torch: {
        installed: false,
        version: null,
        cudaAvailable: false,
        mpsAvailable: false
      }
    };
  }
}

function pythonVersionOk(version: string | null): boolean {
  if (!version) return false;
  const [majorRaw, minorRaw] = version.split(".");
  const major = Number.parseInt(majorRaw ?? "0", 10);
  const minor = Number.parseInt(minorRaw ?? "0", 10);
  return major > 3 || (major === 3 && minor >= 10);
}

export async function inspectTimesFmReadiness(args: {
  env?: NodeJS.ProcessEnv;
  ts?: string;
  python?: string;
  outputDir?: string;
  defaultCsvPath?: string;
  modelId?: string;
  maxContext?: number;
  horizon?: number;
  batchSize?: number;
  allowDownload?: boolean;
} = {}): Promise<TimesFmReadiness> {
  const env = args.env ?? process.env;
  const ts = args.ts ?? new Date().toISOString();
  const python = args.python ?? env.BILL_TIMESFM_PYTHON ?? "python3";
  const modelId = args.modelId ?? env.BILL_TIMESFM_MODEL_ID ?? "google/timesfm-2.5-200m-pytorch";
  const outputDir = resolve(args.outputDir ?? env.BILL_TIMESFM_OUTPUT_DIR ?? ".rumbling-hedge/research/timesfm");
  const defaultCsvPath = resolve(args.defaultCsvPath ?? env.BILL_TIMESFM_DEFAULT_CSV_PATH ?? "data/free/ALL-6MARKETS-1m-10d-normalized.csv");
  const maxContext = args.maxContext ?? Number.parseInt(env.BILL_TIMESFM_MAX_CONTEXT ?? "512", 10);
  const horizon = args.horizon ?? Number.parseInt(env.BILL_TIMESFM_HORIZON ?? "24", 10);
  const batchSize = args.batchSize ?? Number.parseInt(env.BILL_TIMESFM_BATCH_SIZE ?? "4", 10);
  const allowDownload = args.allowDownload ?? env.BILL_TIMESFM_ALLOW_DOWNLOAD === "true";
  const cacheDir = modelCacheDir(modelId, env);
  const packageStatus = await inspectPythonPackages(python);
  const cachePresent = await directoryExists(cacheDir);
  const disk = await diskFor(cacheDir, 2);
  const blockers: string[] = [];
  const warnings: string[] = [];

  if (!packageStatus.python.ok) {
    blockers.push("python3 is not available for TimesFM checks");
  } else if (!pythonVersionOk(packageStatus.python.version)) {
    blockers.push(`TimesFM requires Python >=3.10; found ${packageStatus.python.version ?? "unknown"}`);
  }
  if (!packageStatus.timesfm.installed) {
    blockers.push("python package timesfm is not installed");
  }
  if (!packageStatus.torch.installed) {
    blockers.push("python package torch is not installed");
  }
  if (!cachePresent && !allowDownload) {
    blockers.push(`model weights are not cached locally for ${modelId}; first forecast would download from Hugging Face`);
  }
  if (os.totalmem() / GIB < 4) {
    blockers.push("system RAM is below the TimesFM 2.5 recommended minimum of 4GiB");
  }
  if (os.freemem() / GIB < 2) {
    warnings.push("available RAM is below 2GiB; keep TimesFM disabled until memory pressure is lower");
  }
  if (disk && disk.availableGiB < disk.recommendedGiB) {
    blockers.push(`Hugging Face cache disk has ${disk.availableGiB}GiB free; TimesFM needs about ${disk.recommendedGiB}GiB`);
  }
  if (allowDownload) {
    warnings.push("BILL_TIMESFM_ALLOW_DOWNLOAD=true; a forecast may download model weights from Hugging Face");
  }
  if (packageStatus.torch.installed && !packageStatus.torch.cudaAvailable && !packageStatus.torch.mpsAvailable) {
    warnings.push("Torch is CPU-only; use small batch/context settings for Mac mini stability");
  }

  const status: TimesFmReadinessStatus = blockers.length === 0
    ? "ready"
    : packageStatus.timesfm.installed || packageStatus.torch.installed || cachePresent
      ? "blocked"
      : "missing";

  return {
    command: "timesfm-status",
    ts,
    status,
    role: "research-only",
    repo: {
      url: "https://github.com/google-research/timesfm",
      license: "Apache-2.0",
      auditedAt: ts,
      safetySummary: "No malicious code found in static audit. Forecasting can download Hugging Face model weights; keep downloads disabled until approved."
    },
    model: {
      id: modelId,
      version: "2.5",
      backend: "torch",
      requiresHuggingFaceWeights: true,
      weightsApproxGiB: 1,
      cacheDir,
      cachePresent
    },
    runtime: {
      python: packageStatus.python,
      packages: {
        timesfm: packageStatus.timesfm,
        torch: packageStatus.torch
      },
      memory: {
        totalGiB: round(os.totalmem() / GIB),
        freeGiB: round(os.freemem() / GIB),
        recommendedGiB: 4
      },
      disk
    },
    config: {
      outputDir,
      defaultCsvPath,
      maxContext,
      horizon,
      batchSize,
      allowDownload
    },
    blockers,
    warnings,
    nextCommands: [
      "python3 -m pip install --user 'timesfm[torch]'",
      `HF_HOME=${dirname(dirname(cacheDir))} huggingface-cli download ${modelId}`,
      `python3 scripts/timesfm-forecast-local.py --csv ${defaultCsvPath} --out ${join(outputDir, "forecast.json")} --horizon ${horizon} --max-context ${maxContext}`
    ],
    hermesSummary: status === "ready"
      ? "TimesFM is ready for bounded research-only forecasts."
      : "TimesFM is not forecast-ready; keep it research-only and do not install packages or download weights without founder approval."
  };
}

export function renderTimesFmMarkdown(report: TimesFmReadiness): string {
  const lines = [
    "# TimesFM Readiness",
    "",
    `Updated: ${report.ts}`,
    "",
    `Status: ${report.status}`,
    "",
    "## Role",
    "",
    "TimesFM belongs in Bill's research layer as a zero-shot probabilistic forecaster for futures, crypto, macro, options context, and prediction-market time series. It is not execution authority.",
    "",
    "## Runtime",
    "",
    `- Python: ${report.runtime.python.ok ? report.runtime.python.version : "missing"}`,
    `- timesfm package: ${report.runtime.packages.timesfm.installed ? report.runtime.packages.timesfm.version : "missing"}`,
    `- torch package: ${report.runtime.packages.torch.installed ? report.runtime.packages.torch.version : "missing"}`,
    `- CUDA available: ${report.runtime.packages.torch.cudaAvailable ? "yes" : "no"}`,
    `- MPS available: ${report.runtime.packages.torch.mpsAvailable ? "yes" : "no"}`,
    `- RAM: ${report.runtime.memory.freeGiB}GiB free / ${report.runtime.memory.totalGiB}GiB total`,
    `- Model cache: ${report.model.cachePresent ? "present" : "missing"} at ${report.model.cacheDir}`,
    "",
    "## Blockers",
    "",
    ...(report.blockers.length > 0 ? report.blockers.map((item) => `- ${item}`) : ["- none"]),
    "",
    "## Warnings",
    "",
    ...(report.warnings.length > 0 ? report.warnings.map((item) => `- ${item}`) : ["- none"]),
    "",
    "## Safe Commands",
    "",
    ...report.nextCommands.map((command) => `- \`${command}\``),
    "",
    "## Hermes Instruction",
    "",
    `${report.hermesSummary} Hermes may monitor this report and escalate blockers, but must not install packages, download model weights, or run forecasts without founder approval.`
  ];
  return `${lines.join("\n")}\n`;
}

export async function writeTimesFmReadiness(args: {
  report: TimesFmReadiness;
  reportPath?: string;
  markdownPath?: string;
}): Promise<{ reportPath: string; markdownPath: string }> {
  const reportPath = resolve(args.reportPath ?? join(args.report.config.outputDir, "readiness.json"));
  const markdownPath = resolve(args.markdownPath ?? join(args.report.config.outputDir, "README.md"));
  await mkdir(dirname(reportPath), { recursive: true });
  await mkdir(dirname(markdownPath), { recursive: true });
  await writeFile(reportPath, `${JSON.stringify(args.report, null, 2)}\n`, "utf8");
  await writeFile(markdownPath, renderTimesFmMarkdown(args.report), "utf8");
  return { reportPath, markdownPath };
}
