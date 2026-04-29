import { promises as fs } from "fs";
import { join } from "path";

const OUTBOX_PATH = join(process.cwd(), "OUTBOX.md");

export async function writeOutbox(label: string, payload: any) {
  const line = "## " + new Date().toISOString() + " — " + label + "\n" + JSON.stringify(payload, null, 2) + "\n";
  try {
    const existing = await fs.readFile(OUTBOX_PATH, "utf8");
    await fs.writeFile(OUTBOX_PATH, existing + line, "utf8");
  } catch {
    await fs.writeFile(OUTBOX_PATH, line, "utf8");
  }
  console.log("OUTBOX updated:", label);
}
