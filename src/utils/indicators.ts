import type { Bar } from "../domain.js";

export function trueRange(current: Bar, previous?: Bar): number {
  if (!previous) {
    return current.high - current.low;
  }

  return Math.max(
    current.high - current.low,
    Math.abs(current.high - previous.close),
    Math.abs(current.low - previous.close)
  );
}

export function averageTrueRange(history: Bar[], period = 14): number {
  if (history.length === 0) {
    return 0;
  }

  const tail = history.slice(-period);
  let total = 0;

  for (let index = 0; index < tail.length; index += 1) {
    total += trueRange(tail[index]!, tail[index - 1]);
  }

  return total / tail.length;
}
