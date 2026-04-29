import { execFile, spawn } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const FIRECRAWL_HEALTH_TTL_MS = 30_000;
const firecrawlHealthCache = new Map<string, { healthy: boolean; expiresAt: number }>();

export interface FetchedPage {
  url: string;
  title?: string;
  markdown: string;
  source: "firecrawl" | "native" | "github" | "arxiv";
  statusCode?: number;
}

export interface CrawlerConfig {
  firecrawlBaseUrl?: string;
  firecrawlApiKey?: string;
  userAgent: string;
  timeoutMs: number;
}

export function buildCrawlerConfigFromEnv(env: NodeJS.ProcessEnv = process.env): CrawlerConfig {
  const timeoutRaw = Number.parseInt(env.RESEARCHER_CRAWL_TIMEOUT_MS ?? "30000", 10);
  return {
    firecrawlBaseUrl: env.FIRECRAWL_BASE_URL ?? env.RESEARCHER_FIRECRAWL_URL,
    firecrawlApiKey: env.FIRECRAWL_API_KEY,
    userAgent: env.RESEARCHER_USER_AGENT ?? "ResearcherBot/1.0 (+openclaw)",
    timeoutMs: Number.isFinite(timeoutRaw) && timeoutRaw > 0 ? timeoutRaw : 30_000
  };
}

export async function firecrawlHealthy(config: CrawlerConfig): Promise<boolean> {
  if (!config.firecrawlBaseUrl) return false;
  const cacheKey = `${config.firecrawlBaseUrl}|${config.firecrawlApiKey ? "keyed" : "anon"}`;
  const cached = firecrawlHealthCache.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.healthy;
  }
  const probes = config.firecrawlApiKey
    ? [
        {
          url: `${config.firecrawlBaseUrl}/v1/team/credit-usage`,
          headers: { Authorization: `Bearer ${config.firecrawlApiKey}` }
        },
        {
          url: `${config.firecrawlBaseUrl}/health`
        }
      ]
    : [
        {
          url: `${config.firecrawlBaseUrl}/health`
        }
      ];

  for (const probe of probes) {
    try {
      const res = await fetch(probe.url, {
        headers: probe.headers,
        signal: AbortSignal.timeout(2000)
      });
      if (res.ok) {
        firecrawlHealthCache.set(cacheKey, {
          healthy: true,
          expiresAt: Date.now() + FIRECRAWL_HEALTH_TTL_MS
        });
        return true;
      }
    } catch {
      // Try the next probe before marking Firecrawl unavailable.
    }
  }
  firecrawlHealthCache.set(cacheKey, {
    healthy: false,
    expiresAt: Date.now() + FIRECRAWL_HEALTH_TTL_MS
  });
  return false;
}

export async function firecrawlScrape(
  url: string,
  config: CrawlerConfig
): Promise<FetchedPage | null> {
  if (!config.firecrawlBaseUrl) return null;
  try {
    const res = await fetch(`${config.firecrawlBaseUrl}/v1/scrape`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(config.firecrawlApiKey ? { Authorization: `Bearer ${config.firecrawlApiKey}` } : {})
      },
      body: JSON.stringify({
        url,
        formats: ["markdown"],
        onlyMainContent: true
      }),
      signal: AbortSignal.timeout(config.timeoutMs)
    });
    if (!res.ok) return null;
    const json = (await res.json()) as {
      data?: { markdown?: string; metadata?: { title?: string; statusCode?: number } };
      success?: boolean;
    };
    const md = json.data?.markdown;
    if (!md) return null;
    return {
      url,
      title: json.data?.metadata?.title,
      markdown: md,
      source: "firecrawl",
      statusCode: json.data?.metadata?.statusCode
    };
  } catch {
    return null;
  }
}

export function stripHtmlToMarkdown(html: string): { title?: string; markdown: string } {
  const titleMatch = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const title = titleMatch?.[1]?.replace(/\s+/g, " ").trim();
  let body = html
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<nav[\s\S]*?<\/nav>/gi, "")
    .replace(/<footer[\s\S]*?<\/footer>/gi, "")
    .replace(/<header[\s\S]*?<\/header>/gi, "");
  body = body
    .replace(/<h([1-6])[^>]*>([\s\S]*?)<\/h\1>/gi, (_m, n: string, inner: string) => {
      const level = Number.parseInt(n, 10);
      return `\n\n${"#".repeat(level)} ${inner.replace(/<[^>]+>/g, "").trim()}\n\n`;
    })
    .replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, (_m, inner: string) => `- ${inner.replace(/<[^>]+>/g, "").trim()}\n`)
    .replace(/<p[^>]*>/gi, "\n\n")
    .replace(/<br\s*\/?>(\s*)/gi, "\n")
    .replace(/<code[^>]*>([\s\S]*?)<\/code>/gi, (_m, inner: string) => `\`${inner}\``)
    .replace(/<pre[^>]*>([\s\S]*?)<\/pre>/gi, (_m, inner: string) => `\n\n\`\`\`\n${inner.replace(/<[^>]+>/g, "")}\n\`\`\`\n\n`)
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return { title, markdown: body };
}

export async function nativeScrape(
  url: string,
  config: CrawlerConfig
): Promise<FetchedPage | null> {
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": config.userAgent, Accept: "text/html,application/xhtml+xml" },
      signal: AbortSignal.timeout(config.timeoutMs),
      redirect: "follow"
    });
    if (!res.ok) return null;
    const ct = res.headers.get("content-type") ?? "";
    if (ct.includes("application/pdf")) {
      return { url, markdown: "", source: "native", statusCode: res.status };
    }
    const html = await res.text();
    const { title, markdown } = stripHtmlToMarkdown(html);
    return { url, title, markdown, source: "native", statusCode: res.status };
  } catch {
    return null;
  }
}

async function curlScrape(
  url: string,
  config: CrawlerConfig
): Promise<FetchedPage | null> {
  try {
    const { stdout } = await execFileAsync("curl", [
      "--silent",
      "--show-error",
      "--location",
      "--max-time",
      String(Math.max(2, Math.ceil(config.timeoutMs / 1000))),
      "--user-agent",
      config.userAgent,
      "--header",
      "Accept: text/html,application/xhtml+xml",
      url
    ], {
      timeout: config.timeoutMs,
      maxBuffer: 2_000_000
    });
    const { title, markdown } = stripHtmlToMarkdown(stdout);
    if (!markdown) {
      return null;
    }
    return {
      url,
      title,
      markdown,
      source: "native"
    };
  } catch {
    return null;
  }
}

export async function scrape(url: string, config: CrawlerConfig): Promise<FetchedPage | null> {
  if (config.firecrawlBaseUrl && (await firecrawlHealthy(config))) {
    const fc = await firecrawlScrape(url, config);
    if (fc && fc.markdown.length > 0) return fc;
  }
  const native = await nativeScrape(url, config);
  if (native && native.markdown.length > 0) {
    return native;
  }
  return curlScrape(url, config);
}

function ghExec(args: string[], timeoutMs: number): Promise<{ stdout: string; code: number }> {
  return new Promise((resolve, reject) => {
    const child = spawn("gh", args);
    const chunks: Buffer[] = [];
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, timeoutMs);
    child.stdout.on("data", (d) => chunks.push(Buffer.from(d)));
    child.stderr.on("data", () => undefined);
    child.on("error", (e) => {
      clearTimeout(timer);
      reject(e);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (timedOut) {
        reject(new Error(`gh ${args.join(" ")} timed out`));
        return;
      }
      resolve({ stdout: Buffer.concat(chunks).toString("utf8"), code: code ?? 0 });
    });
  });
}

export interface GithubRepoDigest {
  owner: string;
  repo: string;
  description?: string;
  stars?: number;
  readme: string;
  docs: Array<{ path: string; content: string }>;
  topics: string[];
}

function parseRepoSlug(url: string): { owner: string; repo: string } | null {
  const m = url.match(/github\.com[/:]([^/]+)\/([^/#?]+?)(?:\.git)?(?:\/.*)?$/i);
  if (!m) return null;
  return { owner: m[1], repo: m[2] };
}

export async function digestGithubRepo(
  url: string,
  config: CrawlerConfig,
  options: { docGlobs?: string[]; maxDocs?: number } = {}
): Promise<GithubRepoDigest | null> {
  const slug = parseRepoSlug(url);
  if (!slug) return null;
  const { owner, repo } = slug;
  try {
    const repoMeta = await ghExec(
      ["api", `repos/${owner}/${repo}`, "-H", "Accept: application/vnd.github+json"],
      config.timeoutMs
    );
    if (repoMeta.code !== 0) return null;
    const meta = JSON.parse(repoMeta.stdout) as {
      description?: string;
      stargazers_count?: number;
      topics?: string[];
      default_branch?: string;
    };
    const branch = meta.default_branch ?? "main";

    const readmeRes = await ghExec(
      ["api", `repos/${owner}/${repo}/readme`, "-H", "Accept: application/vnd.github.raw"],
      config.timeoutMs
    );
    const readme = readmeRes.code === 0 ? readmeRes.stdout : "";

    const docs: Array<{ path: string; content: string }> = [];
    const maxDocs = options.maxDocs ?? 8;
    try {
      const treeRes = await ghExec(
        [
          "api",
          `repos/${owner}/${repo}/git/trees/${branch}?recursive=1`,
          "-H",
          "Accept: application/vnd.github+json"
        ],
        config.timeoutMs
      );
      if (treeRes.code === 0) {
        const tree = JSON.parse(treeRes.stdout) as {
          tree: Array<{ path: string; type: string; size?: number }>;
        };
        const candidates = tree.tree
          .filter(
            (n) =>
              n.type === "blob" &&
              (n.size ?? 0) < 200_000 &&
              /\.(md|mdx|rst|txt)$/i.test(n.path) &&
              !/node_modules|vendor|dist|build/i.test(n.path) &&
              n.path.toLowerCase() !== "readme.md"
          )
          .slice(0, maxDocs);
        for (const c of candidates) {
          const rawUrl = `https://raw.githubusercontent.com/${owner}/${repo}/${branch}/${c.path}`;
          const res = await fetch(rawUrl, {
            headers: { "User-Agent": config.userAgent },
            signal: AbortSignal.timeout(config.timeoutMs)
          }).catch(() => null);
          if (res && res.ok) {
            const content = await res.text();
            if (content.length > 200 && content.length < 200_000) {
              docs.push({ path: c.path, content });
            }
          }
        }
      }
    } catch {
      // tree walk best-effort
    }

    return {
      owner,
      repo,
      description: meta.description,
      stars: meta.stargazers_count,
      readme,
      docs,
      topics: meta.topics ?? []
    };
  } catch {
    return null;
  }
}

export interface ArxivEntry {
  id: string;
  title: string;
  summary: string;
  authors: string[];
  published: string;
  link: string;
}

export async function searchArxiv(
  query: string,
  limit: number,
  config: CrawlerConfig
): Promise<ArxivEntry[]> {
  const url = `http://export.arxiv.org/api/query?search_query=${encodeURIComponent(
    query
  )}&start=0&max_results=${limit}&sortBy=submittedDate&sortOrder=descending`;
  const res = await fetch(url, {
    headers: { "User-Agent": config.userAgent },
    signal: AbortSignal.timeout(config.timeoutMs)
  });
  if (!res.ok) return [];
  const xml = await res.text();
  const entries: ArxivEntry[] = [];
  const entryRe = /<entry>([\s\S]*?)<\/entry>/g;
  let m: RegExpExecArray | null;
  while ((m = entryRe.exec(xml)) !== null) {
    const body = m[1];
    const title = (body.match(/<title>([\s\S]*?)<\/title>/)?.[1] ?? "").replace(/\s+/g, " ").trim();
    const summary = (body.match(/<summary>([\s\S]*?)<\/summary>/)?.[1] ?? "").trim();
    const id = (body.match(/<id>([\s\S]*?)<\/id>/)?.[1] ?? "").trim();
    const published = (body.match(/<published>([\s\S]*?)<\/published>/)?.[1] ?? "").trim();
    const authors = Array.from(body.matchAll(/<name>([\s\S]*?)<\/name>/g)).map((x) => x[1].trim());
    if (title && summary) {
      entries.push({ id, title, summary, authors, published, link: id });
    }
  }
  return entries;
}
