import { execFile } from "node:child_process";
import { mkdtemp, readFile, readdir, rm, stat } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { URL } from "node:url";
import { promisify } from "node:util";
import { buildChunk, type CorpusChunk } from "./corpus.js";
import type { ResearcherPolicy, Target } from "./pipeline.js";
import {
  extractStrategyHypothesesFromTranscript,
  type StrategyHypothesis
} from "./strategyHypotheses.js";

export interface YouTubeTarget extends Target {
  kind: "youtube-transcript";
  query?: string;
  videos?: string[];
  language?: string;
}

interface YouTubeVideoCandidate {
  videoId: string;
  title: string;
  channel?: string;
  url: string;
}

interface YouTubeTranscriptSegment {
  start: number;
  duration: number;
  text: string;
}

interface YouTubeTranscriptDocument {
  video: YouTubeVideoCandidate;
  language?: string;
  transcriptText: string;
  segments: YouTubeTranscriptSegment[];
}

const DEFAULT_INVIDIOUS_INSTANCES = [
  "https://yewtu.be",
  "https://vid.puffyan.us",
  "https://invidious.privacyredirect.com"
];
const DEFAULT_TRANSCRIPT_PROVIDER_TIMEOUT_MS = 8_000;
const GEMINI_TRANSCRIPT_MODEL = "gemini-2.5-flash";
const GEMINI_INLINE_AUDIO_LIMIT_BYTES = 19 * 1024 * 1024;
const GEMINI_SEGMENT_SECONDS = 15 * 60;
const execFileAsync = promisify(execFile);

export interface YouTubeCollectionResult {
  chunks: CorpusChunk[];
  hypotheses: StrategyHypothesis[];
  transcriptArtifactsDeleted: number;
  videosProcessed: number;
}

export function isYouTubeTarget(target: Target): target is YouTubeTarget {
  return target.kind === "youtube-transcript";
}

function listLine(label: string, values: string[], fallback = "not specified"): string {
  return `${label}: ${values.length > 0 ? values.join("; ") : fallback}`;
}

function strategyCardText(hypothesis: StrategyHypothesis, source: YouTubeTranscriptDocument): string {
  return [
    `# Strategy hypothesis: ${hypothesis.title}`,
    `Source: ${source.video.title}`,
    source.video.channel ? `Channel: ${source.video.channel}` : undefined,
    `Video: ${source.video.url}`,
    `Market: ${hypothesis.market}`,
    listLine("Symbols", hypothesis.symbols),
    listLine("Timeframes", hypothesis.timeframes),
    listLine("Sessions", hypothesis.sessions),
    `Automation readiness: ${hypothesis.automationReadiness}`,
    `Confidence: ${hypothesis.confidence.toFixed(2)}`,
    "",
    "Setup:",
    hypothesis.setupSummary || "not specified",
    "",
    listLine("Bias rules", hypothesis.biasRules),
    listLine("Entry rules", hypothesis.entryRules),
    listLine("Stop rules", hypothesis.stopRules),
    listLine("Target rules", hypothesis.targetRules),
    listLine("Risk rules", hypothesis.riskRules),
    listLine("Confluence", hypothesis.confluence),
    listLine("Invalidation", hypothesis.invalidationRules),
    listLine("Evidence", hypothesis.evidence.slice(0, 5))
  ].filter((value): value is string => typeof value === "string" && value.length > 0).join("\n");
}

function shouldStoreStrategyCard(hypothesis: StrategyHypothesis): boolean {
  const hasTradingShape = hypothesis.entryRules.length > 0
    && hypothesis.stopRules.length > 0
    && hypothesis.riskRules.length > 0
    && hypothesis.evidence.length > 0;
  return hypothesis.confidence >= 0.45 && hasTradingShape;
}

export async function collectYouTubeTranscriptTarget(
  target: YouTubeTarget,
  args: {
    runId: string;
    policy: ResearcherPolicy;
  }
): Promise<YouTubeCollectionResult> {
  const videos = await discoverVideos(target);
  const chunks: CorpusChunk[] = [];
  const hypotheses: StrategyHypothesis[] = [];
  let transcriptArtifactsDeleted = 0;
  const failures: string[] = [];

  for (const video of videos) {
    try {
      const transcript = await fetchTranscript(video, target.language);
      transcriptArtifactsDeleted += 1;

      const extracted = await extractStrategyHypothesesFromTranscript(
        {
          targetId: target.id,
          videoId: video.videoId,
          title: video.title,
          channel: video.channel,
          url: video.url,
          language: transcript.language,
          transcriptText: transcript.transcriptText
        },
        args.policy
      );
      hypotheses.push(...extracted.hypotheses);
      if (process.env.BILL_YOUTUBE_STORE_RAW_TRANSCRIPTS === "1") {
        chunks.push(
          buildChunk({
            runId: args.runId,
            sourceId: target.id,
            sourceKind: "web",
            url: video.url,
            title: `${video.title} transcript`,
            text: [
              `# ${video.title}`,
              video.channel ? `Channel: ${video.channel}` : undefined,
              `Video: ${video.url}`,
              "",
              transcript.transcriptText
            ].filter(Boolean).join("\n"),
            tags: ["youtube", "transcript", "raw-transcript", ...(target.tags ?? [])]
          })
        );
      }
      for (const hypothesis of extracted.hypotheses.filter(shouldStoreStrategyCard)) {
        chunks.push(
          buildChunk({
            runId: args.runId,
            sourceId: target.id,
            sourceKind: "web",
            url: video.url,
            title: `${hypothesis.title} strategy card`,
            text: strategyCardText(hypothesis, transcript),
            tags: ["youtube", "strategy-card", "transcript-derived", ...(target.tags ?? [])]
          })
        );
      }
    } catch (error) {
      failures.push(`${video.videoId}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (videos.length > 0 && chunks.length === 0 && failures.length > 0) {
    throw new Error(`all youtube transcript candidates failed for ${target.id}: ${failures.slice(0, 3).join(" | ")}`);
  }

  return {
    chunks,
    hypotheses,
    transcriptArtifactsDeleted,
    videosProcessed: videos.length
  };
}

async function discoverVideos(target: YouTubeTarget): Promise<YouTubeVideoCandidate[]> {
  const imported = await import("youtubei.js");
  const yt = await imported.Innertube.create({
    lang: "en",
    location: "US"
  });

  const limit = Math.max(1, target.limit ?? 12);
  const candidates: YouTubeVideoCandidate[] = [];
  const seen = new Set<string>();

  for (const value of target.videos ?? []) {
    const videoId = extractVideoId(value);
    if (!videoId || seen.has(videoId)) continue;
    const info = await yt.getBasicInfo(videoId);
    const details = info.basic_info ?? {};
    const title = stringOrFallback(details.title, videoId);
    const channel = stringOrUndefined(details.author);
    candidates.push({
      videoId,
      title,
      channel,
      url: `https://www.youtube.com/watch?v=${videoId}`
    });
    seen.add(videoId);
    if (candidates.length >= limit) return candidates;
  }

  if (target.query) {
    let search = await yt.search(target.query, {});
    while (true) {
      for (const entry of search.videos ?? []) {
        const videoId = stringOrUndefined((entry as { id?: string; video_id?: string }).id)
          ?? stringOrUndefined((entry as { video_id?: string }).video_id);
        if (!videoId || seen.has(videoId)) continue;
        const title = titleText((entry as { title?: unknown }).title) ?? videoId;
        const channel = stringOrUndefined((entry as { author?: { name?: string } }).author?.name);
        candidates.push({
          videoId,
          title,
          channel,
          url: `https://www.youtube.com/watch?v=${videoId}`
        });
        seen.add(videoId);
        if (candidates.length >= limit) return candidates;
      }
      if (!("has_continuation" in search) || !(search as { has_continuation?: boolean }).has_continuation) {
        break;
      }
      search = await search.getContinuation();
    }
  }

  return candidates;
}

async function fetchTranscript(video: YouTubeVideoCandidate, language?: string): Promise<YouTubeTranscriptDocument> {
  const failures: string[] = [];
  if (process.env.BILL_YOUTUBE_TRANSCRIPT_SKIP_FREE !== "1") {
    try {
      return await fetchTranscriptViaTranscriptLibrary(video, language);
    } catch (error) {
      failures.push(error instanceof Error ? error.message : String(error));
    }
  }
  if (process.env.YOUTUBE_TRANSCRIPT_DEV_API_KEY) {
    try {
      return await fetchTranscriptViaService(video, language);
    } catch (error) {
      failures.push(error instanceof Error ? error.message : String(error));
    }
  }
  try {
    return await fetchTranscriptViaWatchPage(video, language);
  } catch (error) {
    failures.push(error instanceof Error ? error.message : String(error));
  }
  if (process.env.GEMINI_API_KEY) {
    try {
      return await fetchTranscriptViaGeminiAudio(video, language);
    } catch (error) {
      failures.push(error instanceof Error ? error.message : String(error));
    }
  }
  throw new Error(`transcript fetch failed for ${video.videoId}: ${failures.join(" | ")}`);
}

async function fetchTranscriptViaTranscriptLibrary(
  video: YouTubeVideoCandidate,
  language?: string
): Promise<YouTubeTranscriptDocument> {
  const imported = await import("@playzone/youtube-transcript/dist/enhanced-api/index.js");
  const instanceUrls = (process.env.BILL_YOUTUBE_TRANSCRIPT_INVIDIOUS_URLS ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const api = new imported.EnhancedYouTubeTranscriptApi(
    {},
    {
      enabled: true,
      instanceUrls: instanceUrls.length > 0 ? instanceUrls : DEFAULT_INVIDIOUS_INSTANCES,
      timeout: Number.parseInt(
        process.env.BILL_YOUTUBE_TRANSCRIPT_PROVIDER_TIMEOUT_MS ?? `${DEFAULT_TRANSCRIPT_PROVIDER_TIMEOUT_MS}`,
        10
      )
    }
  );
  const fetched = await api.fetch(video.videoId, language ? [language, "en"] : ["en"], true) as {
    snippets?: Array<{ text?: string; start?: number; duration?: number }>;
    language?: string;
    languageCode?: string;
  };
  const segments = Array.isArray(fetched?.snippets)
    ? fetched.snippets
      .map((snippet) => ({
        start: typeof snippet.start === "number" ? snippet.start : 0,
        duration: typeof snippet.duration === "number" ? snippet.duration : 0,
        text: typeof snippet.text === "string" ? snippet.text.trim() : ""
      }))
      .filter((snippet) => snippet.text.length > 0)
    : [];
  if (segments.length === 0) {
    throw new Error(`free transcript provider returned no transcript rows for ${video.videoId}`);
  }

  return {
    video,
    language: fetched.languageCode ?? fetched.language ?? language,
    transcriptText: segments.map((segment) => segment.text).join(" "),
    segments
  };
}

async function fetchTranscriptViaService(
  video: YouTubeVideoCandidate,
  language?: string
): Promise<YouTubeTranscriptDocument> {
  const response = await fetch("https://youtubetranscript.dev/api/v2/transcribe", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.YOUTUBE_TRANSCRIPT_DEV_API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      video: video.videoId,
      ...(language ? { language } : {}),
      format: "timestamp"
    })
  });
  if (!response.ok) {
    throw new Error(`transcript service failed for ${video.videoId}: ${response.status}`);
  }
  const json = await response.json() as {
    data?: {
      language?: string;
      transcript?: Array<{ start?: number; duration?: number; text?: string }>;
    };
  };
  const transcriptRows = Array.isArray(json.data?.transcript) ? json.data?.transcript ?? [] : [];
  const segments = transcriptRows
    .map((row) => ({
      start: typeof row.start === "number" ? row.start : 0,
      duration: typeof row.duration === "number" ? row.duration : 0,
      text: typeof row.text === "string" ? row.text.trim() : ""
    }))
    .filter((row) => row.text.length > 0);
  if (segments.length === 0) {
    throw new Error(`transcript service returned no transcript rows for ${video.videoId}`);
  }
  return {
    video,
    language: json.data?.language ?? language,
    transcriptText: segments.map((segment) => segment.text).join(" "),
    segments
  };
}

async function fetchTranscriptViaWatchPage(
  video: YouTubeVideoCandidate,
  language?: string
): Promise<YouTubeTranscriptDocument> {
  const response = await fetch(video.url, {
    headers: {
      "User-Agent": "Mozilla/5.0"
    }
  });
  if (!response.ok) {
    throw new Error(`youtube watch page failed for ${video.videoId}: ${response.status}`);
  }
  const html = await response.text();
  const captionTracks = parseCaptionTracks(html);
  if (captionTracks.length === 0) {
    throw new Error(
      `no transcript available for ${video.videoId}; set YOUTUBE_TRANSCRIPT_DEV_API_KEY for reliable transcript ingestion`
    );
  }
  const selected = selectCaptionTrack(captionTracks, language);
  const timedText = await fetch(selected.baseUrl, {
    headers: {
      "User-Agent": "Mozilla/5.0"
    }
  });
  const raw = await timedText.text();
  if (!timedText.ok || raw.trim().length === 0) {
    throw new Error(
      `youtube caption track was empty for ${video.videoId}; set YOUTUBE_TRANSCRIPT_DEV_API_KEY for reliable transcript ingestion`
    );
  }

  const segments = extractXmlSegments(raw);
  if (segments.length === 0) {
    throw new Error(`transcript parse produced zero segments for ${video.videoId}`);
  }
  return {
    video,
    language: selected.languageCode ?? language,
    transcriptText: segments.map((segment) => segment.text).join(" "),
    segments
  };
}

async function fetchTranscriptViaGeminiAudio(
  video: YouTubeVideoCandidate,
  language?: string
): Promise<YouTubeTranscriptDocument> {
  const ytDlpPath = await resolveBinaryPath(
    [
      process.env.BILL_YT_DLP_PATH,
      process.env.YT_DLP_PATH,
      join(homedir(), ".local", "bin", "yt-dlp"),
      "yt-dlp"
    ],
    ["--version"]
  );
  if (!ytDlpPath) {
    throw new Error(`gemini transcript fallback unavailable for ${video.videoId}: yt-dlp not found`);
  }

  const ffmpegPath = await resolveBinaryPath(
    [
      process.env.BILL_FFMPEG_PATH,
      "/opt/homebrew/bin/ffmpeg",
      "ffmpeg"
    ],
    ["-version"]
  );
  if (!ffmpegPath) {
    throw new Error(`gemini transcript fallback unavailable for ${video.videoId}: ffmpeg not found`);
  }

  const workDir = await mkdtemp(join(tmpdir(), "bill-youtube-transcript-"));
  try {
    const audioPath = await downloadYouTubeAudio(video, ytDlpPath, workDir);
    const optimizedAudioPath = await optimizeAudioForTranscript(audioPath, ffmpegPath, workDir);
    const chunkPaths = await splitAudioForTranscript(optimizedAudioPath, ffmpegPath, workDir);
    const aggregatedSegments: YouTubeTranscriptSegment[] = [];
    let detectedLanguage = language;

    for (const [index, chunkPath] of chunkPaths.entries()) {
      const baseOffsetSeconds = index * GEMINI_SEGMENT_SECONDS;
      const chunk = await transcribeAudioChunkWithGemini(chunkPath, baseOffsetSeconds, language);
      detectedLanguage ??= chunk.language;
      aggregatedSegments.push(...chunk.segments);
    }

    const segments = aggregatedSegments
      .map((segment) => ({
        start: Number.isFinite(segment.start) ? Number(segment.start.toFixed(3)) : 0,
        duration: Number.isFinite(segment.duration) ? Number(segment.duration.toFixed(3)) : 0,
        text: segment.text.trim()
      }))
      .filter((segment) => segment.text.length > 0);
    if (segments.length === 0) {
      throw new Error(`gemini transcript fallback returned no transcript rows for ${video.videoId}`);
    }

    return {
      video,
      language: detectedLanguage ?? language,
      transcriptText: segments.map((segment) => segment.text).join(" "),
      segments
    };
  } finally {
    await rm(workDir, { recursive: true, force: true });
  }
}

async function resolveBinaryPath(
  candidates: Array<string | undefined>,
  versionArgs: string[]
): Promise<string | undefined> {
  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      await execFileAsync(candidate, versionArgs);
      return candidate;
    } catch {
      continue;
    }
  }
  return undefined;
}

async function downloadYouTubeAudio(
  video: YouTubeVideoCandidate,
  ytDlpPath: string,
  workDir: string
): Promise<string> {
  await execFileAsync(
    ytDlpPath,
    [
      "--js-runtimes",
      "node",
      "--extract-audio",
      "--audio-format",
      "mp3",
      "--audio-quality",
      "5",
      "--output",
      join(workDir, "%(id)s.%(ext)s"),
      video.url
    ],
    {
      maxBuffer: 32 * 1024 * 1024
    }
  );
  const entries = await readdir(workDir);
  const audioPath = entries
    .filter((entry) => basename(entry).startsWith(video.videoId))
    .map((entry) => resolve(workDir, entry))
    .find((entry) => /\.(mp3|m4a|webm|opus|wav)$/i.test(entry));
  if (!audioPath) {
    throw new Error(`yt-dlp did not emit an audio artifact for ${video.videoId}`);
  }
  return audioPath;
}

async function optimizeAudioForTranscript(
  inputPath: string,
  ffmpegPath: string,
  workDir: string
): Promise<string> {
  const outputPath = join(workDir, "transcript-input.mp3");
  await execFileAsync(
    ffmpegPath,
    [
      "-y",
      "-i",
      inputPath,
      "-vn",
      "-ac",
      "1",
      "-ar",
      "16000",
      "-b:a",
      "24k",
      outputPath
    ],
    {
      maxBuffer: 32 * 1024 * 1024
    }
  );
  return outputPath;
}

async function splitAudioForTranscript(
  inputPath: string,
  ffmpegPath: string,
  workDir: string
): Promise<string[]> {
  const inputStats = await stat(inputPath);
  if (inputStats.size <= GEMINI_INLINE_AUDIO_LIMIT_BYTES) {
    return [inputPath];
  }

  const outputPattern = join(workDir, "transcript-part-%03d.mp3");
  await execFileAsync(
    ffmpegPath,
    [
      "-y",
      "-i",
      inputPath,
      "-f",
      "segment",
      "-segment_time",
      `${GEMINI_SEGMENT_SECONDS}`,
      "-c",
      "copy",
      outputPattern
    ],
    {
      maxBuffer: 32 * 1024 * 1024
    }
  );

  const chunkPaths = (await readdir(workDir))
    .filter((entry) => /^transcript-part-\d{3}\.mp3$/i.test(entry))
    .sort()
    .map((entry) => resolve(workDir, entry));
  if (chunkPaths.length === 0) {
    throw new Error(`ffmpeg did not emit transcript chunks for ${basename(inputPath)}`);
  }
  return chunkPaths;
}

async function transcribeAudioChunkWithGemini(
  audioPath: string,
  baseOffsetSeconds: number,
  language?: string
): Promise<{ language?: string; segments: YouTubeTranscriptSegment[] }> {
  const rawAudio = await readFile(audioPath);
  if (rawAudio.length > GEMINI_INLINE_AUDIO_LIMIT_BYTES) {
    throw new Error(`gemini inline audio payload is still too large for ${basename(audioPath)}`);
  }

  const prompt = [
    "Transcribe this trading education audio into JSON.",
    "Return only JSON with shape {\"language\":\"...\",\"segments\":[{\"start\":0,\"duration\":0,\"text\":\"...\"}]}",
    "Each segment should be 20 to 60 seconds when possible.",
    "Use numeric seconds relative to the start of this audio chunk.",
    "Do not omit spoken words, and do not add commentary.",
    language ? `Prefer transcript language ${language}.` : "Infer the spoken language."
  ].join(" ");
  const model = process.env.BILL_YOUTUBE_TRANSCRIPT_MODEL ?? GEMINI_TRANSCRIPT_MODEL;
  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(process.env.GEMINI_API_KEY ?? "")}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        generationConfig: {
          responseMimeType: "application/json"
        },
        contents: [{
          parts: [
            { text: prompt },
            {
              inline_data: {
                mime_type: "audio/mpeg",
                data: rawAudio.toString("base64")
              }
            }
          ]
        }]
      })
    }
  );
  if (!response.ok) {
    const details = await response.text();
    throw new Error(`gemini transcript fallback failed for ${basename(audioPath)}: ${response.status} ${details.slice(0, 240)}`);
  }

  const json = await response.json() as {
    candidates?: Array<{
      content?: {
        parts?: Array<{ text?: string }>;
      };
    }>;
  };
  const responseText = json.candidates?.[0]?.content?.parts?.map((part) => part.text ?? "").join("").trim() ?? "";
  const parsed = parseGeminiTranscriptResponse(responseText);
  const segments = parsed.segments
    .map((segment) => ({
      start: baseOffsetSeconds + (Number.isFinite(segment.start) ? segment.start : 0),
      duration: Number.isFinite(segment.duration) ? segment.duration : 0,
      text: typeof segment.text === "string" ? segment.text.replace(/\s+/g, " ").trim() : ""
    }))
    .filter((segment) => segment.text.length > 0);
  if (segments.length === 0) {
    throw new Error(`gemini transcript fallback returned empty JSON for ${basename(audioPath)}`);
  }
  return {
    language: parsed.language,
    segments
  };
}

function parseGeminiTranscriptResponse(value: string): {
  language?: string;
  segments: Array<{ start: number; duration: number; text: string }>;
} {
  const normalized = value.trim();
  const jsonCandidate = normalized.startsWith("{")
    ? normalized
    : normalized.slice(normalized.indexOf("{"), normalized.lastIndexOf("}") + 1);
  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonCandidate);
  } catch {
    throw new Error("gemini transcript fallback returned non-JSON content");
  }
  const root = parsed as {
    language?: unknown;
    segments?: Array<{ start?: unknown; duration?: unknown; text?: unknown }>;
  };
  const segments = Array.isArray(root.segments)
    ? root.segments.map((segment) => ({
      start: typeof segment.start === "number" ? segment.start : Number(segment.start ?? 0),
      duration: typeof segment.duration === "number" ? segment.duration : Number(segment.duration ?? 0),
      text: typeof segment.text === "string" ? segment.text : ""
    }))
    : [];
  return {
    language: typeof root.language === "string" ? root.language : undefined,
    segments
  };
}

function parseCaptionTracks(html: string): Array<{ baseUrl: string; languageCode?: string; kind?: string }> {
  const match = html.match(/"captionTracks":(\[[\s\S]*?\])/);
  if (!match) return [];
  const decoded = match[1].replace(/\\u0026/g, "&").replace(/\\"/g, "\"");
  try {
    const parsed = JSON.parse(decoded) as Array<{ baseUrl: string; languageCode?: string; kind?: string }>;
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function selectCaptionTrack(
  tracks: Array<{ baseUrl: string; languageCode?: string; kind?: string }>,
  language?: string
): { baseUrl: string; languageCode?: string; kind?: string } {
  if (language) {
    const exact = tracks.find((track) => track.languageCode === language);
    if (exact) return exact;
  }
  return tracks.find((track) => track.kind !== "asr") ?? tracks[0]!;
}

function extractXmlSegments(xml: string): YouTubeTranscriptSegment[] {
  const matches = [...xml.matchAll(/<text start="([^"]+)" dur="([^"]+)"[^>]*>([\s\S]*?)<\/text>/g)];
  return matches
    .map((match) => ({
      start: Number(match[1]),
      duration: Number(match[2]),
      text: decodeHtml(match[3] ?? "").replace(/\s+/g, " ").trim()
    }))
    .filter((segment) => segment.text.length > 0);
}

function decodeHtml(value: string): string {
  return value
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, "\"")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&#10;/g, " ")
    .replace(/&#xa;/gi, " ");
}

function extractVideoId(value: string): string | undefined {
  try {
    const url = new URL(value);
    if (url.hostname === "youtu.be") return url.pathname.replace(/^\/+/, "") || undefined;
    if (url.hostname.endsWith("youtube.com")) return url.searchParams.get("v") ?? undefined;
  } catch {
    if (/^[a-zA-Z0-9_-]{6,}$/.test(value)) return value;
  }
  return undefined;
}

function titleText(value: unknown): string | undefined {
  if (typeof value === "string") return value.trim() || undefined;
  if (value && typeof value === "object") {
    const asText = value as { text?: string; toString?: () => string };
    if (typeof asText.text === "string" && asText.text.trim().length > 0) return asText.text.trim();
    if (typeof asText.toString === "function") {
      const rendered = asText.toString();
      if (typeof rendered === "string" && rendered.trim().length > 0) return rendered.trim();
    }
  }
  return undefined;
}

function stringOrUndefined(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

function stringOrFallback(value: unknown, fallback: string): string {
  return stringOrUndefined(value) ?? fallback;
}
