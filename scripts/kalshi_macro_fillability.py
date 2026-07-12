#!/usr/bin/env python3
"""Deeper fillability analysis for Kalshi macro/econ contracts (research-only)."""
from __future__ import annotations
import json, urllib.parse, urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".rumbling-hedge" / "state"
RESEARCH_DIR = ROOT / ".rumbling-hedge" / "research"
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"

MACRO_CATEGORIES: dict[str, list[str]] = {
    "fed-rates": ["KXFED","KXRATECUT","KXRATEHIKE","KXFEDDECISION","KXDOTPLOT",
        "KXTERMINALRATE","KXLOWESTRATE","KXFEDRATEMIN","KXEFFR","KXFOMCGUIDE",
        "KXFOMCDISSENTCOUNT","KXDXYFOMC","KXFWFOMC","KXSPXFOMC","KX2YFOMC",
        "KXFEDEND","KXTAPER","KXFTAPER","KXBALANCESHEET"],
    "cpi-inflation": ["KXCPI","KXCPICORE","KXCPICOREYOY","KXCPIYOY","KXACPI",
        "KXACPICORE","KXCOREUND","KXCPIUSEDCAR","KXCPIGAS","KXCPISHELTER",
        "KXCPIFOOD","KXCPIAPPAREL","KXECONSTATCPI","KXECONSTATCPICORE",
        "KXECONSTATCPIYOY","KXECONSTATCORECPIYOY","KXTRUFCPI","KXTRUFCPIYE",
        "KXTRUFGAS","KXTRUFHOUCPI","KXUSGASCPI","KXTOBACCPI","KXSHELTERCPI",
        "KXUSEDCARCPI","KXCPIEU","KXCPIUSEDCAR"],
    "pce-ppi": ["KXPCECORE","KXPPICPI","KXUSPPI","KXPPISEMI","KXPPIVSCPI","KXUSPPIYOY"],
    "gdp": ["KXGDP","KXGDPCN","KXGDPEU","KXGDPW","KXGDPYEAR","KXGDPNOM","KXGDPUSMAX",
        "KXGDPUSMIN","KXCHIPYOY","KXCHNGDP","KXCHINAUSGDP","KXCNUSGDP","KXBRAZILGDP",
        "KXDEGDPQOQF","KXDEGDPYOYF","KXESGDPQOQF","KXESGDPYOYF","KXFRGDPQOQP",
        "KXFRGDPYOYP","KXITGDPQOQA","KXITGDPYOYA","KXUKGDPMOM","KXSAGDPQOQ",
        "KXGDPSHAREMANU","KXCNGDP","KXINDIAVJAPAN"],
    "treasury-yields": ["KX10Y2Y","KX10Y3M","KX10YUSTSRY","KX30YUSTW","KX3MTBILL",
        "KXTNOTE","KXTNOTED","KXTNOTEW","KXNOTE10","KXNOTE30","KXNOTE10M",
        "KXNOTE10W","KXNOTE30W","KXUSTYLD","KXYINVERT","KXTREASURYMAX","KXTREASURYMAX5"],
    "mortgage-housing": ["KXFRM","KXFRMMAX","KXFRMMIN","KXFM30YMTG","KXHOME","KXHOMEUS",
        "KXHOUSESTART","KXHOUSINGSTART","KXHPI","KXEHSALES","KXNHSALES","KXMORTGAGERATE",
        "KXMORTGAGEDEF","KXNATLEMERGENCYHOUSING","KXRECAPGAINS"],
    "equity-index": ["KXINX","KXINXAB","KXINXB","KXINXM","KXINXU","KXINXW","KXINXY",
        "KXINXZ","KXINXEOYCLOSE","KXINXMAX","KXINXMAXM","KXINXMAXY","KXINXMINW",
        "KXINXMINY","KXNASDAQ100","KXNASDAQ100M","KXNASDAQ100U","KXNASDAQ100W",
        "KXNASDAQ100Y","KXNASDAQ100Z","KXDJIA","KXDJIAPOS","KXME"],
    "oil-commodities": ["KXWTI","KXWTIH","KXWTIMAX","KXWTIMIN","KXWTIMONTHLY","KXWTIW",
        "KXWTIVSBRENT","KXWHENWTI","KXBRENTD","KXBRENTMON","KXBRENTW","KXWTIMAXM","KXWTIMINM"],
    "jobs-unemployment": ["KXU3","KXU3MAX","KXU3MIN","KXUE","KXUSNFP","KXJOBSRELEASE",
        "KXPAYROLLSREV","KXNFPROD","KXUSDURABLE","KXYOUTHUN","KXUSIPMOM","KXMANUCON"],
    "retail-sentiment": ["KXRETAIL","KXUSRETAIL","KXUKRETAIL","KXSARETAIL","KXTRUFCCI",
        "KXCACPIYOY","KXJPCONCONF","KXDEGFK"],
    "tariffs-trade": ["KXTARIFFCHECKS","KXTARIFFDECISIONRELEASE","KXTARIFFENDGLOBAL",
        "KXTARIFFENDPRC","KXTARIFFLENGTHPRC","KXTARIFFRATEBR","KXTARIFFRATECA",
        "KXTARIFFRATECAN","KXTARIFFRATEEU","KXTARIFFRATEINDIA","KXTARIFFRATEJP",
        "KXTARIFFRATEKR","KXTARIFFRATEPRC","KXTARREBATE","KXTARIFFREFUND",
        "KXTARIFFREVENUE","KXAVGTARIFF","KXEFFTARIFF","KXTRADEDEFICIT","KXTRDDEFCN",
        "KXCOUNTRYTARIFF"],
    "foreign-implied": ["KXBOE","KXECBMENTION","KXEUROZONE","KXEZCPIYOYF","KXEZGDPQOQF",
        "KXEZGDPYOYF","KXCBDECISIONEU","KXCBDECISIONENGLAND","KXCBDECISIONJAPAN",
        "KXCBDECISIONCANADA","KXCBDECISIONCHINA","KXCBDECISIONMEXICO","KXCBDECISIONINDIA",
        "KXCBDECISIONKOREA","KXCBDECISIONAUSTRALIA","KXCBDISRAEL","KXCBDSA","KXWCPI-RU",
        "KXWCPI-TR","KXCHINACPI","KXCHRETAIL","KXCHNBSPMI","KXBRAZILINF","KXBRAZILTARIFFSIZE",
        "KXBRAZILU","KXARINFLATIONM","KXARMOMINF","KXCANTARIFFSIZE","KXCANRECESSION",
        "KXCANHOUSTART","KXUKCPIYOY","KXUKUNRATE","KXJPCPIYOY","KXJPMOMINF","KXSAMOMINF",
        "KXDECPIPREL","KXFRCPIPREL","KXITCPIPREL"],
}

def to_float(v):
    if isinstance(v,(int,float)) and v==v: return float(v)
    if isinstance(v,str):
        try: return float(v)
        except ValueError: return None
    return None

@dataclass
class MarketFill:
    ticker:str; series:str; category:str; title:str
    yesBid:float|None; yesAsk:float|None; noBid:float|None; noAsk:float|None
    spreadPct:float|None; topBookDepthDollars:float; liquidityDollars:float
    openInterestDollars:float; volume24hDollars:float; lifetimeVolumeDollars:float
    twoSided:bool; bucket:str; executable:bool; reason:str

def bucket_for_spread(s):
    if s is None: return "no-book"
    if s<=2: return "tight"
    if s<=5: return "usable"
    if s<=15: return "wide"
    return "too-wide"

def fill_from_market(mkt, category):
    ticker=str(mkt.get("ticker") or "unknown")
    series=ticker.split("-",1)[0]
    title=str(mkt.get("title") or mkt.get("subtitle") or ticker)
    yb=to_float(mkt.get("yes_bid_dollars")); ya=to_float(mkt.get("yes_ask_dollars"))
    nb=to_float(mkt.get("no_bid_dollars")); na=to_float(mkt.get("no_ask_dollars"))
    yb_sz=to_float(mkt.get("yes_bid_size_fp")) or 0.0
    ya_sz=to_float(mkt.get("yes_ask_size_fp")) or 0.0
    nb_sz=to_float(mkt.get("no_bid_size_fp")) or 0.0
    na_sz=to_float(mkt.get("no_ask_size_fp")) or 0.0
    top_depth=yb_sz+ya_sz+nb_sz+na_sz
    liq=to_float(mkt.get("liquidity_dollars")) or 0.0
    oi=to_float(mkt.get("open_interest_fp")) or 0.0
    v24=to_float(mkt.get("volume_24h_fp")) or 0.0
    vol=to_float(mkt.get("volume_fp")) or 0.0
    yes_two=yb is not None and ya is not None and 0<yb<=ya<1
    no_two=nb is not None and na is not None and 0<nb<=na<1
    two_sided=yes_two or no_two
    spread=None
    if yes_two: spread=round((ya-yb)*100,3)
    elif no_two: spread=round((na-nb)*100,3)
    bucket=bucket_for_spread(spread)
    executable=two_sided and bucket in {"tight","usable"} and top_depth>=100.0
    if not two_sided: reason="no two-sided book"
    elif bucket not in {"tight","usable"}: reason=f"spread bucket {bucket}"
    elif top_depth<100.0: reason=f"thin top-of-book depth ${top_depth:.0f}"
    else: reason="fillable two-sided book"
    return MarketFill(ticker,series,category,title,yb,ya,nb,na,spread,
        round(top_depth,2),round(liq,2),round(oi,2),round(v24,2),round(vol,2),
        two_sided,bucket,executable,reason)

def fetch_open(series, limit=200):
    out=[]; cursor=None
    while True:
        params=urllib.parse.urlencode({"status":"open","series_ticker":series,
            "limit":str(limit),**( {"cursor":cursor} if cursor else {})})
        req=urllib.request.Request(f"{KALSHI_BASE}/markets?{params}",
            headers={"accept":"application/json","user-agent":"bill-hermes-macro-fill/1.0"})
        with urllib.request.urlopen(req,timeout=20) as r:
            payload=json.loads(r.read().decode("utf-8"))
        page=payload.get("markets") or []
        out.extend(page); cursor=payload.get("cursor")
        if not cursor or not page: break
    return out

def main():
    rows=[]; errors=[]; series_seen=set()
    for cat, sl in MACRO_CATEGORIES.items():
        for s in sl:
            try: mkts=fetch_open(s)
            except Exception as exc:
                errors.append({"series":s,"category":cat,"error":f"{type(exc).__name__}: {exc}"}); continue
            if not mkts: continue
            series_seen.add(s)
            rows.extend(fill_from_market(m,cat) for m in mkts)
    by_cat={}
    for cat in MACRO_CATEGORIES:
        cr=[r for r in rows if r.category==cat]; n=len(cr)
        two=sum(1 for r in cr if r.twoSided); ex=sum(1 for r in cr if r.executable)
        spreads=[r.spreadPct for r in cr if r.spreadPct is not None]
        depth=[r.topBookDepthDollars for r in cr if r.executable]
        liq=[r.liquidityDollars for r in cr]; oi=[r.openInterestDollars for r in cr]
        by_cat[cat]={"openMarkets":n,"seriesWithOpenMarkets":len({r.series for r in cr}),
            "twoSidedBooks":two,"twoSidedPct":round(100*two/n,1) if n else 0.0,
            "executable":ex,"executablePct":round(100*ex/n,1) if n else 0.0,
            "medianSpreadPct":round(sorted(spreads)[len(spreads)//2],2) if spreads else None,
            "totalExecutableDepthDollars":round(sum(depth),2),
            "totalLiquidityDollars":round(sum(liq),2),
            "totalOpenInterestDollars":round(sum(oi),2)}
    n_total=len(rows); ex_total=sum(1 for r in rows if r.executable)
    two_total=sum(1 for r in rows if r.twoSided)
    side_pairs=sum(1 for r in rows if r.executable and r.yesBid is not None and r.yesAsk is not None)+sum(1 for r in rows if r.executable and r.noBid is not None and r.noAsk is not None)
    snap={"command":"kalshi-macro-fillability","generatedAt":datetime.now(timezone.utc).isoformat(),
        "researchOnly":True,"writesOrders":False,"touchesBroker":False,"requiresAuth":False,
        "promotedForExecution":False,"tradableSignal":False,"source":"Kalshi public market API v2",
        "macroCategoriesQueried":len(MACRO_CATEGORIES),"seriesWithOpenMarkets":len(series_seen),
        "openMacroMarkets":n_total,"twoSidedBooks":two_total,
        "twoSidedPct":round(100*two_total/n_total,1) if n_total else 0.0,
        "executableMarkets":ex_total,"executablePct":round(100*ex_total/n_total,1) if n_total else 0.0,
        "executableSidePairs":side_pairs,"byCategory":by_cat,"seriesErrors":errors,
        "topExecutable":[asdict(r) for r in sorted([r for r in rows if r.executable],
            key=lambda r:(-r.topBookDepthDollars,r.spreadPct or 999))[:25]],
        "decision":"research-only fillability evidence; not alpha, not tradable",
        "nextActions":["Join fillable macro series to resolved-outcome history before any paper candidate.",
            "Per hard rules: compare like-with-like (Fed decision vs Fed decision, not CPI prints).",
            "No paper/live route from this artifact."]}
    STATE_DIR.mkdir(parents=True,exist_ok=True); RESEARCH_DIR.mkdir(parents=True,exist_ok=True)
    (STATE_DIR/"kalshi-macro-fillability.latest.json").write_text(json.dumps(snap,indent=2)+"\n")
    (RESEARCH_DIR/"kalshi-macro-fillability-detail.json").write_text(json.dumps([asdict(r) for r in rows],indent=2)+"\n")
    print(json.dumps({"openMacroMarkets":n_total,"twoSided":two_total,"executable":ex_total,
        "executableSidePairs":side_pairs,"seriesWithOpenMarkets":len(series_seen),
        "byCategoryExecPct":{k:v["executablePct"] for k,v in by_cat.items()}},indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
