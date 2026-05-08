#!/usr/bin/env python3
"""Research Agent Track — Continuous arXiv paper collection and synthesis.
Separate track for Bill/Hedge research pipeline.
Usage: python3 scripts/research_agent.py [--collect] [--synthesize] [--report]
"""
import arxiv, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(".rumbling-hedge/state")
RESEARCH_DIR = Path(".rumbling-hedge/research/researcher")
LOG_PATH = RESEARCH_DIR / "research-agent-log.jsonl"

# Strategy gap queries — each maps to one of our 8 categories
RESEARCH_QUERIES = [
    ("ict-smart-money", "ti:liquidity ti:sweep ti:displacement ti:order ti:block ti:trading"),
    ("momentum-trend", "ti:momentum ti:trend ti:following ti:breakout ti:futures"),
    ("mean-reversion", "ti:mean ti:reversion ti:statistical ti:arbitrage ti:pairs"),
    ("pattern-recognition", "ti:candlestick ti:pattern ti:chart ti:technical ti:recognition"),
    ("event-macro", "ti:macroeconomic ti:event ti:announcement ti:reaction ti:trading"),
    ("volume-flow", "ti:order ti:flow ti:volume ti:imbalance ti:prediction"),
    ("options-volatility", "ti:options ti:volatility ti:surface ti:gamma ti:hedging"),
    ("quant-ml", "ti:machine ti:learning ti:deep ti:reinforcement ti:trading ti:futures"),
]

def collect_papers(max_per_query: int = 5) -> list:
    """Collect papers from arXiv for all strategy gaps."""
    client = arxiv.Client()
    all_papers = []
    
    for gap, query in RESEARCH_QUERIES:
        try:
            search = arxiv.Search(query=query, max_results=max_per_query, sort_by=arxiv.SortCriterion.SubmittedDate)
            results = list(client.results(search))
            for r in results:
                all_papers.append({
                    "gap": gap,
                    "title": r.title,
                    "url": r.pdf_url,
                    "published": r.published.isoformat(),
                    "summary": r.summary[:300],
                    "authors": [a.name for a in r.authors[:5]],
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })
            print(f"  {gap}: {len(results)} papers")
        except Exception as e:
            print(f"  {gap}: ERROR - {e}")
    
    return all_papers

def score_paper(paper: dict) -> dict:
    """Score paper relevance and novelty."""
    title_lower = paper["title"].lower()
    summary_lower = paper.get("summary", "").lower()
    
    # Relevance keywords
    relevant_keywords = [
        "trading", "futures", "strategy", "prediction", "forecasting",
        "portfolio", "risk", "execution", "market", "price", "return",
        "alpha", "signal", "backtest", "statistical", "hedge"
    ]
    relevance = sum(1 for kw in relevant_keywords if kw in title_lower + " " + summary_lower)
    
    # Novelty keywords
    novel_keywords = [
        "deep learning", "transformer", "reinforcement", "graph neural",
        "attention", "generative", "adversarial", "causal", "ensemble",
        "bayesian", "hidden markov", "hawkes", "signature", "optimal transport"
    ]
    novelty = sum(2 for kw in novel_keywords if kw in title_lower)
    
    score = min(10, relevance * 0.5 + novelty * 0.8)
    
    return {
        **paper,
        "relevance_score": round(relevance, 1),
        "novelty_score": round(novelty, 1),
        "total_score": round(score, 1),
        "high_signal": score >= 7,
    }

def synthesize_findings(papers: list) -> dict:
    """Synthesize research findings across gaps."""
    by_gap = {}
    for p in papers:
        gap = p.get("gap", "unknown")
        if gap not in by_gap:
            by_gap[gap] = []
        by_gap[gap].append(p)
    
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_papers": len(papers),
        "high_signal_count": sum(1 for p in papers if p.get("high_signal")),
        "gaps_covered": len(by_gap),
        "by_gap": {gap: len(pps) for gap, pps in by_gap.items()},
        "top_findings": sorted(papers, key=lambda p: p.get("total_score", 0), reverse=True)[:10],
    }

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--collect", action="store_true", help="Collect new papers")
    p.add_argument("--synthesize", action="store_true", help="Synthesize existing papers")
    p.add_argument("--report", action="store_true", help="Generate research report")
    args = p.parse_args()
    
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    
    if args.collect:
        print("Research Agent: Collecting papers...")
        papers = collect_papers(max_per_query=3)
        scored = [score_paper(p) for p in papers]
        
        # Log to JSONL
        with open(LOG_PATH, "a") as f:
            for s in scored:
                f.write(json.dumps(s) + "\n")
        
        # Generate latest report
        synthesis = synthesize_findings(scored)
        report_path = RESEARCH_DIR / "strategy-hypotheses.latest.json"
        with open(report_path, "w") as f:
            json.dump(synthesis, f, indent=2, default=str)
        
        print(f"\nCollected: {len(papers)} papers across {synthesis['gaps_covered']} gaps")
        print(f"High signal: {synthesis['high_signal_count']}")
        print(f"Report: {report_path}")
    
    elif args.synthesize:
        print("Research Agent: Synthesizing...")
        papers = []
        if LOG_PATH.exists():
            with open(LOG_PATH) as f:
                for line in f:
                    if line.strip():
                        papers.append(json.loads(line))
        synthesis = synthesize_findings(papers)
        report_path = RESEARCH_DIR / "strategy-hypotheses.latest.json"
        with open(report_path, "w") as f:
            json.dump(synthesis, f, indent=2, default=str)
        print(f"Synthesized {len(papers)} papers. Report: {report_path}")
    
    elif args.report:
        print("Research Agent Report")
        print("=" * 50)
        report_path = RESEARCH_DIR / "strategy-hypotheses.latest.json"
        if report_path.exists():
            with open(report_path) as f:
                r = json.load(f)
            print(f"Papers: {r['total_papers']}")
            print(f"High signal: {r['high_signal_count']}")
            print(f"\nBy gap:")
            for gap, count in r.get("by_gap", {}).items():
                print(f"  {gap}: {count}")
            print(f"\nTop findings:")
            for t in r.get("top_findings", [])[:5]:
                print(f"  [{t.get('total_score',0):.1f}] {t.get('title','')[:90]}")
    
    else:
        print("Usage: --collect | --synthesize | --report")

if __name__ == "__main__":
    main()
