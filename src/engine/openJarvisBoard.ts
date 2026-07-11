import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { OpenJarvisStatus } from "./openJarvis.js";

export const DEFAULT_OPENJARVIS_BOARD_HTML_PATH = ".rumbling-hedge/state/openjarvis-board.html";
export const DEFAULT_OPENJARVIS_BOARD_MARKDOWN_PATH = ".rumbling-hedge/state/openjarvis-board.md";

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function bucketTone(status: string): string {
  switch (status) {
    case "ready":
      return "good";
    case "building":
      return "warm";
    default:
      return "cool";
  }
}

function postureTone(status: string): string {
  switch (status) {
    case "actionable":
    case "execute":
      return "good";
    case "shadow":
    case "collecting":
    case "collect":
    case "research":
      return "warm";
    case "setup-debt":
    case "configure":
      return "risk";
    default:
      return "cool";
  }
}

export function renderOpenJarvisBoardMarkdown(status: OpenJarvisStatus): string {
  const actionLines = status.actionQueue.slice(0, 6).map((action) =>
    `- [${action.owner}] ${action.summary} (${action.stage})`
  );
  const trackLines = status.bill.trackBoard.map((track) =>
    `- ${track.id}: ${track.mode} / ${track.posture} / next: ${track.nextAction}`
  );
  const bucketLines = status.bill.fundPlan.buckets.map((bucket) =>
    `- ${bucket.label}: target ${bucket.targetPct}% / deployed ${bucket.deployedPct}% / ${bucket.status}`
  );
  const autonomyLines = status.autonomy
    ? [
        `- status: ${status.autonomy.status}`,
        `- mode: ${status.autonomy.mode}`,
        `- heavy compute: ${status.autonomy.compute.posture} / max ${status.autonomy.compute.maxHeavyJobs}`,
        `- quant autonomy: ${status.autonomy.artifacts.quantAutonomy.summary}`,
        `- strategy iteration: ${status.autonomy.artifacts.strategyIteration.summary}`,
        `- voice input: ${status.autonomy.trustBoundary.voiceInputMode} / ${status.autonomy.trustBoundary.operatorIntent.summary}`,
        `- fork cards: ${status.autonomy.artifacts.forkIntake.summary}`,
        `- strategy lab: ${status.autonomy.artifacts.strategyLab.summary}`,
        `- paper gates: live disabled=${status.autonomy.paperGates.liveTradingDisabled}, futures demo disabled=${status.autonomy.paperGates.futuresDemoExecutionDisabled}`
      ]
    : ["- autonomy status is missing; run npm run bill:autonomy-status"];

  return [
    "# OpenJarvis Fund Board",
    "",
    `- generated: ${status.timestamp}`,
    `- founder posture: ${status.founder.posture}`,
    `- routing owner: ${status.founder.routingOwner}`,
    `- next action: ${status.founder.nextAction}`,
    `- runtime health: ${status.runtimeHealth.status}`,
    "",
    "## Fund Plan",
    `- mode: ${status.bill.fundPlan.mode}`,
    `- next capital move: ${status.bill.fundPlan.nextCapitalMove}`,
    `- reserve policy: ${status.bill.fundPlan.reservePolicy}`,
    ...bucketLines,
    "",
    "## Tracks",
    ...trackLines,
    "",
    "## Action Queue",
    ...actionLines,
    "",
    "## Bill/Hedge Autonomy",
    ...autonomyLines,
    "",
    "## Approvals",
    `- pending approvals: ${status.approvalQueue.count}`,
    ...status.approvalQueue.requests.slice(0, 5).map((request) => `- ${request.requestedAction}`),
    "",
    "## Runtime Warnings",
    ...(status.runtimeHealth.summaryLines.length > 0
      ? status.runtimeHealth.summaryLines.map((line) => `- ${line}`)
      : ["- none"]),
    ""
  ].join("\n");
}

export function renderOpenJarvisBoardHtml(status: OpenJarvisStatus): string {
  const bucketCards = status.bill.fundPlan.buckets.map((bucket) => `
      <article class="card bucket ${bucketTone(bucket.status)}">
        <div class="eyebrow">${escapeHtml(bucket.label)}</div>
        <div class="metric">${bucket.deployedPct}%</div>
        <div class="submetric">target ${bucket.targetPct}%</div>
        <p>${escapeHtml(bucket.mandate)}</p>
      </article>
  `).join("");

  const trackCards = status.bill.trackBoard.map((track) => `
      <article class="card track ${postureTone(track.posture)}">
        <div class="row">
          <h3>${escapeHtml(track.id)}</h3>
          <span class="pill">${escapeHtml(track.mode)}</span>
        </div>
        <div class="row">
          <span class="pill">${escapeHtml(track.posture)}</span>
          <span class="pill subtle">${escapeHtml(track.trackedSymbols.slice(0, 4).join(", ") || "no symbols")}</span>
        </div>
        <p>${escapeHtml(track.nextAction)}</p>
      </article>
  `).join("");

  const actionItems = status.actionQueue.slice(0, 8).map((action) => `
      <li>
        <span class="pill ${postureTone(action.stage)}">${escapeHtml(action.stage)}</span>
        <strong>${escapeHtml(action.owner)}</strong>
        <span>${escapeHtml(action.summary)}</span>
      </li>
  `).join("");

  const ladderItems = status.bill.fundPlan.growthLadder.map((step) => `
      <li class="${step.status}">
        <strong>${escapeHtml(step.title)}</strong>
        <span>${escapeHtml(step.condition)}</span>
        <em>${escapeHtml(step.action)}</em>
      </li>
  `).join("");

  const warningItems = (status.runtimeHealth.summaryLines.length > 0 ? status.runtimeHealth.summaryLines : ["No active runtime warnings."])
    .map((line) => `<li>${escapeHtml(line)}</li>`).join("");
  const autonomyItems = status.autonomy
    ? [
        `mode: ${status.autonomy.mode}`,
        `heavy compute: ${status.autonomy.compute.posture} / max ${status.autonomy.compute.maxHeavyJobs}`,
        `quant autonomy: ${status.autonomy.artifacts.quantAutonomy.summary}`,
        `strategy iteration: ${status.autonomy.artifacts.strategyIteration.summary}`,
        `voice input: ${status.autonomy.trustBoundary.voiceInputMode} / ${status.autonomy.trustBoundary.operatorIntent.summary}`,
        `fork intake: ${status.autonomy.artifacts.forkIntake.summary}`,
        `strategy lab: ${status.autonomy.artifacts.strategyLab.summary}`,
        `paper gates: live disabled=${status.autonomy.paperGates.liveTradingDisabled}, futures demo disabled=${status.autonomy.paperGates.futuresDemoExecutionDisabled}`,
        ...status.autonomy.warnings.slice(0, 3)
      ].map((line) => `<li>${escapeHtml(line)}</li>`).join("")
    : "<li>Autonomy status is missing; run npm run bill:autonomy-status.</li>";

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>OpenJarvis Fund Board</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f5efe3;
        --panel: rgba(255, 252, 246, 0.9);
        --ink: #17231f;
        --muted: #5c6b65;
        --line: rgba(23, 35, 31, 0.12);
        --good: #1f6a52;
        --warm: #9a5d18;
        --risk: #923131;
        --cool: #405b63;
        --shadow: 0 20px 40px rgba(23, 35, 31, 0.08);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Avenir Next", "Segoe UI", sans-serif;
        background:
          radial-gradient(circle at top right, rgba(31,106,82,0.08), transparent 28%),
          radial-gradient(circle at left center, rgba(154,93,24,0.08), transparent 24%),
          var(--bg);
        color: var(--ink);
      }
      .shell {
        max-width: 1360px;
        margin: 0 auto;
        padding: 32px 24px 48px;
      }
      .hero {
        display: grid;
        grid-template-columns: 1.4fr 1fr;
        gap: 18px;
        margin-bottom: 18px;
      }
      .card {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 24px;
        box-shadow: var(--shadow);
        padding: 20px;
      }
      h1, h2, h3 {
        font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
        margin: 0;
      }
      h1 { font-size: clamp(2rem, 4vw, 3.4rem); line-height: 1; }
      h2 { font-size: 1.2rem; margin-bottom: 14px; }
      h3 { font-size: 1.05rem; }
      .eyebrow {
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-size: 0.72rem;
        color: var(--muted);
        margin-bottom: 10px;
      }
      .lede {
        font-size: 1.05rem;
        line-height: 1.55;
        color: var(--muted);
        margin: 14px 0 0;
      }
      .metric {
        font-size: 2.3rem;
        line-height: 1;
        margin-top: 8px;
      }
      .submetric, .mini {
        color: var(--muted);
        font-size: 0.92rem;
      }
      .grid-4 {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 18px;
        margin-bottom: 18px;
      }
      .grid-3 {
        display: grid;
        grid-template-columns: 1.2fr 1fr 1fr;
        gap: 18px;
      }
      .track-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 18px;
        margin-bottom: 18px;
      }
      .row {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        align-items: center;
        margin-bottom: 10px;
      }
      .pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        border-radius: 999px;
        padding: 6px 10px;
        border: 1px solid currentColor;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      .pill.subtle {
        color: var(--muted);
        border-color: var(--line);
      }
      .good { color: var(--good); }
      .warm { color: var(--warm); }
      .risk { color: var(--risk); }
      .cool { color: var(--cool); }
      ul {
        list-style: none;
        padding: 0;
        margin: 0;
        display: grid;
        gap: 12px;
      }
      li {
        border-top: 1px solid var(--line);
        padding-top: 12px;
      }
      li:first-child { border-top: 0; padding-top: 0; }
      li strong, li span, li em { display: block; }
      li em, p { color: var(--muted); line-height: 1.5; }
      .bucket p, .track p { margin: 10px 0 0; }
      @media (max-width: 1080px) {
        .hero, .grid-4, .grid-3, .track-grid { grid-template-columns: 1fr 1fr; }
      }
      @media (max-width: 720px) {
        .hero, .grid-4, .grid-3, .track-grid { grid-template-columns: 1fr; }
        .shell { padding: 20px 14px 32px; }
      }
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="hero">
        <article class="card">
          <div class="eyebrow">OpenJarvis Founder Board</div>
          <h1>${escapeHtml(status.founder.nextAction)}</h1>
          <p class="lede">${escapeHtml(status.bill.fundPlan.nextCapitalMove)}</p>
        </article>
        <article class="card">
          <div class="eyebrow">Current Posture</div>
          <div class="metric">${escapeHtml(status.founder.posture)}</div>
          <div class="submetric">Routing owner: ${escapeHtml(status.founder.routingOwner)}</div>
          <p>${escapeHtml(status.bill.fundPlan.reservePolicy)}</p>
        </article>
      </section>

      <section class="grid-4">
        ${bucketCards}
      </section>

      <section class="track-grid">
        ${trackCards}
      </section>

      <section class="grid-3">
        <article class="card">
          <h2>Growth Ladder</h2>
          <ul>${ladderItems}</ul>
        </article>
        <article class="card">
          <h2>Action Queue</h2>
          <ul>${actionItems}</ul>
        </article>
        <article class="card">
          <h2>Runtime Health</h2>
          <div class="mini">status: ${escapeHtml(status.runtimeHealth.status)}</div>
          <ul>${warningItems}</ul>
        </article>
      </section>

      <section class="grid-3" style="margin-top: 18px;">
        <article class="card">
          <h2>Bill/Hedge Autonomy</h2>
          <div class="mini">status: ${escapeHtml(status.autonomy?.status ?? "missing")}</div>
          <ul>${autonomyItems}</ul>
        </article>
        <article class="card">
          <h2>Disk + Git</h2>
          <ul>
            <li>SSD free: ${escapeHtml(String(status.autonomy?.disk.freeGb ?? "unknown"))}GB</li>
            <li>source dirty: ${escapeHtml(String(status.autonomy?.git.sourceDirty ?? "unknown"))}</li>
            <li>runtime dirty: ${escapeHtml(String(status.autonomy?.git.runtimeDirty ?? "unknown"))}</li>
          </ul>
        </article>
        <article class="card">
          <h2>Next Actions</h2>
          <ul>${(status.autonomy?.nextActions.length ? status.autonomy.nextActions : ["Keep paper-only gates on and refresh status."]).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>
        </article>
      </section>
    </main>
  </body>
</html>`;
}

export async function writeOpenJarvisBoardArtifacts(args: {
  status: OpenJarvisStatus;
  htmlPath?: string;
  markdownPath?: string;
}): Promise<{ htmlPath: string; markdownPath: string }> {
  const htmlPath = resolve(args.htmlPath ?? DEFAULT_OPENJARVIS_BOARD_HTML_PATH);
  const markdownPath = resolve(args.markdownPath ?? DEFAULT_OPENJARVIS_BOARD_MARKDOWN_PATH);
  await mkdir(dirname(htmlPath), { recursive: true });
  await mkdir(dirname(markdownPath), { recursive: true });
  await Promise.all([
    writeFile(htmlPath, renderOpenJarvisBoardHtml(args.status), "utf8"),
    writeFile(markdownPath, renderOpenJarvisBoardMarkdown(args.status), "utf8")
  ]);
  return { htmlPath, markdownPath };
}
