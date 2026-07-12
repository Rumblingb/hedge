#!/usr/bin/env python3
"""Parse COT TFF data and detect regime for ES and NQ."""
import csv
import statistics
import sys

ES_NAME = "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE"
NQ_NAME = "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE"

def load_records(csv_path, market_name):
    records = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Market_and_Exchange_Names"] == market_name:
                records.append(row)
    return records

def analyze(records, label):
    if not records:
        print(f"{label}: No records found")
        return
    last = records[-1]
    oi = float(last["Open_Interest_All"])
    d_long = float(last["Dealer_Positions_Long_All"])
    d_short = float(last["Dealer_Positions_Short_All"])
    am_long = float(last["Asset_Mgr_Positions_Long_All"])
    am_short = float(last["Asset_Mgr_Positions_Short_All"])
    lm_long = float(last["Lev_Money_Positions_Long_All"])
    lm_short = float(last["Lev_Money_Positions_Short_All"])

    net_dealer = (d_long - d_short) / oi * 100
    net_am = (am_long - am_short) / oi * 100
    net_lm = (lm_long - lm_short) / oi * 100

    print(f"\n=== {label} ===")
    print(f"Records: {len(records)}, Latest: {last['Report_Date_as_YYYY-MM-DD']}")
    print(f"Open Interest: {oi:,.0f}")
    print(f"Dealer: long={d_long:,.0f} short={d_short:,.0f} net={net_dealer:+.2f}%")
    print(f"Asset Manager: long={am_long:,.0f} short={am_short:,.0f} net={net_am:+.2f}%")
    print(f"Lev Money: long={lm_long:,.0f} short={lm_short:,.0f} net={net_lm:+.2f}%")

    # Dealer net z-score over full history
    net_pcts = []
    for r in records:
        oi = float(r["Open_Interest_All"])
        dl = float(r["Dealer_Positions_Long_All"])
        ds = float(r["Dealer_Positions_Short_All"])
        net_pcts.append((dl - ds) / oi)

    if len(net_pcts) > 1:
        mean = statistics.mean(net_pcts)
        std = statistics.stdev(net_pcts)
        z = (net_pcts[-1] - mean) / std
        print(f"Dealer net z-score: {z:+.2f}")
        if z < -2.0:
            print(f">>> BULLISH: Dealers extremely net short (contrarian long)")
        elif z < -1.5:
            print(f">> Mildly bullish: Dealers net short")
        elif z > 2.0:
            print(f">>> BEARISH: Dealers extremely net long (contrarian short)")
        elif z > 1.5:
            print(f">> Mildly bearish: Dealers net long")
        else:
            print(f">> Neutral")
        print(f"Position multiplier: {1.2 if z < -1.5 else (0.8 if z > 1.5 else 1.0):.1f}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/Users/brain/hedge/.rumbling-hedge/research/cot/tff-2026.csv"
    es = load_records(path, ES_NAME)
    nq = load_records(path, NQ_NAME)
    analyze(es, "E-MINI S&P 500 (ES)")
    analyze(nq, "NASDAQ-100 (NQ)")
