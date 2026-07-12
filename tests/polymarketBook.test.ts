import { describe, expect, it } from "vitest";
import { quoteFromBook } from "../src/prediction/polymarketBook.js";

describe("polymarketBook", () => {
  it("extracts executable top-of-book quote fields", () => {
    const quote = quoteFromBook({
      bids: [
        { price: "0.61", size: "14" },
        { price: "0.63", size: "10" },
      ],
      asks: [
        { price: "0.68", size: "8" },
        { price: "0.66", size: "20" },
      ],
    });

    expect(quote.bestBid).toBe(0.63);
    expect(quote.bestAsk).toBe(0.66);
    expect(quote.bidSize).toBe(10);
    expect(quote.askSize).toBe(20);
    expect(quote.topBookDepth).toBe(30);
    expect(quote.spreadPct).toBe(3);
  });

  it("ignores malformed and non-positive levels", () => {
    const quote = quoteFromBook({
      bids: [
        { price: "nan", size: "5" },
        { price: "0.40", size: "0" },
        { price: "0.39", size: "6" },
      ],
      asks: [
        { price: "1.20", size: "8" },
        { price: "0.42", size: "7" },
      ],
    });

    expect(quote.bestBid).toBe(0.39);
    expect(quote.bestAsk).toBe(0.42);
    expect(quote.topBookDepth).toBe(13);
    expect(quote.spreadPct).toBe(3);
  });
});
