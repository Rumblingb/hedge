import type { Bar, NewsScore } from "../domain.js";

export interface NewsGate {
  name: string;
  score(input: { symbol: string; ts: string; bar: Bar }): NewsScore;
}

export class NoopNewsGate implements NewsGate {
  public readonly name = "noop-news-gate";

  public score(): NewsScore {
    return {
      provider: this.name,
      direction: "flat",
      probability: 0.5,
      impact: "low",
      reason: "no external news provider configured"
    };
  }
}
