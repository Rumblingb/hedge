#!/usr/bin/env python3
"""
Signal Extractor for Hedge Trading System
Extracts actionable trading strategies from raw research content.
"""

import json
import os
import re
import glob
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

# Paths
HOME = os.path.expanduser("~")
RESEARCH_DIR = os.path.join(HOME, ".rumbling-hedge", "research")
DAILY_DIR = os.path.join(RESEARCH_DIR, "daily")
EXTRACTED_DIR = os.path.join(RESEARCH_DIR, "extracted")

# Ensure extracted directory exists
os.makedirs(EXTRACTED_DIR, exist_ok=True)

# Classification keywords
GOLD_KEYWORDS = [
    'entry', 'exit', 'stop loss', 'take profit', 'signal', 'backtest', 
    'win rate', 'profit factor', 'formula', 'indicator', 'RSI', 'MACD', 
    'volume', 'breakout', 'pattern', 'support', 'resistance', 'order flow', 
    'institutional', 'trap', 'manipulation', 'liquidity'
]

SILVER_KEYWORDS = [
    'trading', 'strategy', 'edge', 'opportunity', 'inefficiency', 
    'profit', 'return', 'market', 'price', 'trend', 'setup', 
    'setup', 'advantage', 'bias', 'expectation'
]

def classify_content(content: str) -> Tuple[str, float]:
    """
    Classify content as GOLD, SILVER, or BAD.
    Returns (classification, confidence_score)
    """
    content_lower = content.lower()
    
    # Check for gold keywords
    gold_matches = sum(1 for kw in GOLD_KEYWORDS if kw in content_lower)
    if gold_matches > 0:
        # Confidence based on number of gold keywords found (capped at 5 for normalization)
        confidence = min(gold_matches / 5.0, 1.0)
        return "GOLD", confidence
    
    # Check for silver keywords
    silver_matches = sum(1 for kw in SILVER_KEYWORDS if kw in content_lower)
    if silver_matches > 0:
        confidence = min(silver_matches / 5.0, 1.0)
        return "SILVER", confidence
    
    return "BAD", 0.0

def extract_strategy(content: str, source_info: Dict) -> Optional[Dict]:
    """
    Extract structured strategy from GOLD content.
    Returns a dictionary with strategy fields or None if extraction fails.
    """
    # Initialize extraction with default values
    extraction = {
        "signal_name": "Unnamed Strategy",
        "instrument_type": "any",
        "timeframe": "any",
        "entry_condition": "",
        "exit_condition": "",
        "direction_rule": "FLAT",
        "position_sizing": "",
        "confidence_score": 0.5,
        "market_logic": "",
        "source_attribution": {}
    }
    
    content_lower = content.lower()
    lines = content.split('\n')
    
    # Extract signal name - look for quotes or capitalized phrases
    # Simple heuristic: first line that looks like a title
    for line in lines[:3]:  # Check first few lines
        line = line.strip()
        if len(line) > 5 and len(line) < 100 and not line.startswith(('http', 'www')):
            # Avoid URLs and very long lines
            if line.isupper() or (line[0].isupper() and '.' not in line):
                extraction["signal_name"] = line
                break
    
    # Instrument type
    if 'future' in content_lower:
        extraction["instrument_type"] = "futures"
    elif 'option' in content_lower:
        extraction["instrument_type"] = "options"
    elif 'crypto' in content_lower or 'bitcoin' in content_lower or 'ethereum' in content_lower:
        extraction["instrument_type"] = "crypto"
    elif 'stock' in content_lower or 'equity' in content_lower:
        extraction["instrument_type"] = "stocks"
    elif 'prediction' in content_lower:
        extraction["instrument_type"] = "prediction_market"
    
    # Timeframe - look for patterns like 1m, 5m, 1h, 1d, etc.
    timeframe_pattern = r'\b(\d+)(m|h|d|w)\b'
    match = re.search(timeframe_pattern, content_lower)
    if match:
        num, unit = match.groups()
        unit_map = {'m': 'm', 'h': 'h', 'd': 'd', 'w': 'w'}
        extraction["timeframe"] = f"{num}{unit_map.get(unit, unit)}"
    else:
        # Check for words
        if 'intraday' in content_lower or 'day trade' in content_lower:
            extraction["timeframe"] = "intraday"
        elif 'daily' in content_lower:
            extraction["timeframe"] = "1d"
        elif 'weekly' in content_lower or 'per week' in content_lower:
            extraction["timeframe"] = "1w"
        elif 'monthly' in content_lower:
            extraction["timeframe"] = "1M"
    
    # Entry condition
    entry_patterns = [
        r'entry[:\s]+([^.]+)',
        r'buy[:\s]+([^.]+)',
        r'long[:\s]+([^.]+)',
        r'enter[:\s]+([^.]+)'
    ]
    for pattern in entry_patterns:
        match = re.search(pattern, content_lower)
        if match:
            extraction["entry_condition"] = match.group(1).strip()
            break
    
    # Exit condition
    exit_patterns = [
        r'exit[:\s]+([^.]+)',
        r'sell[:\s]+([^.]+)',
        r'stop loss[:\s]+([^.]+)',
        r'take profit[:\s]+([^.]+)',
        r'tp[:\s]+([^.]+)',
        r'sl[:\s]+([^.]+)'
    ]
    for pattern in exit_patterns:
        match = re.search(pattern, content_lower)
        if match:
            extraction["exit_condition"] = match.group(1).strip()
            break
    
    # Direction rule
    if 'long' in content_lower and 'short' in content_lower:
        extraction["direction_rule"] = "BOTH"
    elif 'long' in content_lower or 'buy' in content_lower:
        extraction["direction_rule"] = "LONG"
    elif 'short' in content_lower or 'sell' in content_lower:
        extraction["direction_rule"] = "SHORT"
    
    # Position sizing
    sizing_patterns = [
        r'position sizing[:\s]+([^.]+)',
        r'risk[:\s]+([^.]+)',
        r'capital[:\s]+([^.]+)',
        r'percent[:\s]+([^.]+)'
    ]
    for pattern in sizing_patterns:
        match = re.search(pattern, content_lower)
        if match:
            extraction["position_sizing"] = match.group(1).strip()
            break
    
    # Market logic - look for sentences explaining why
    logic_indicators = ['because', 'due to', 'since', 'as a result', 'reason', 'rationale', 'edge']
    sentences = re.split(r'[.!?]+', content)
    for sentence in sentences:
        sentence = sentence.strip()
        if any(indicator in sentence.lower() for indicator in logic_indicators):
            if 10 < len(sentence) < 200:  # Reasonable length
                extraction["market_logic"] = sentence
                break
    
    # Source attribution
    extraction["source_attribution"] = {
        "source": source_info.get("file", "unknown"),
        "line": source_info.get("line", 0),
        "id": source_info.get("id", "unknown")
    }
    
    # Adjust confidence based on how much we extracted
    filled_fields = sum(1 for k in ["entry_condition", "exit_condition", "market_logic"] 
                       if extraction[k])
    extraction["confidence_score"] = min(0.3 + (filled_fields * 0.2), 0.9)
    
    # If we have no entry or exit, it's probably not a real strategy
    if not extraction["entry_condition"] and not extraction["exit_condition"]:
        return None
    
    return extraction

def process_file(filepath: str, date_str: Optional[str] = None) -> Tuple[List[Dict], Dict[str, int]]:
    """
    Process a single JSONL file.
    Returns (extractions, counts) where counts is a dict of classification counts.
    """
    extractions = []
    counts = {"GOLD": 0, "SILVER": 0, "BAD": 0, "total": 0}
    lines_to_update = []
    
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return extractions, counts
    
    # Process each line
    updated_lines = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            updated_lines.append(line)
            continue
        
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            print(f"Warning: Invalid JSONL in {filepath}:{i+1}")
            updated_lines.append(line)
            continue
        
        # Skip if already processed (unless we're forcing reprocess for summary?)
        if record.get("processed", False) and date_str is None:
            updated_lines.append(line)
            # Still count for summary if needed
            classification = record.get("classification", "UNKNOWN")
            if classification in counts:
                counts[classification] += 1
            counts["total"] += 1
            continue
        
        # Get content - assume it's in a 'content' or 'text' field
        content = record.get("content", record.get("text", ""))
        if not content:
            updated_lines.append(line)
            continue
        
        # Classify
        classification, confidence = classify_content(content)
        counts[classification] += 1
        counts["total"] += 1
        
        # Prepare source info
        source_info = {
            "file": os.path.basename(filepath),
            "line": i + 1,
            "id": record.get("id", f"{os.path.basename(filepath)}:{i+1}")
        }
        
        extraction = None
        if classification == "GOLD":
            counts["GOLD"] += 1  # Already incremented above, but keep for clarity
            extraction = extract_strategy(content, source_info)
            if extraction:
                extraction["confidence_score"] = confidence  # Override with classification confidence
                extractions.append(extraction)
                record["extracted"] = True
            else:
                # If extraction failed, treat as silver?
                classification = "SILVER"
                counts["SILVER"] += 1
                counts["GOLD"] -= 1
        elif classification == "SILVER":
            counts["SILVER"] += 1
        
        # Update record
        record["processed"] = True
        record["classification"] = classification
        updated_lines.append(json.dumps(record))
    
    # Write back updated lines
    try:
        with open(filepath, 'w') as f:
            f.write('\n'.join(updated_lines) + ('\n' if updated_lines else ''))
    except Exception as e:
        print(f"Error writing {filepath}: {e}")
    
    return extractions, counts

def write_daily_extracts(date_str: str, extractions: List[Dict]):
    """
    Write extractions to the daily signals file.
    """
    if not extractions:
        return
    
    output_file = os.path.join(EXTRACTED_DIR, f"signals-{date_str}.json")
    
    # Load existing if any
    existing_data = {"date": date_str, "total_content_scanned": 0, 
                     "gold_count": 0, "silver_count": 0, "bad_count": 0, 
                     "extractions": []}
    
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r') as f:
                existing_data = json.load(f)
        except Exception:
            pass  # If corrupt, start fresh
    
    # Append new extractions
    existing_data["extractions"].extend(extractions)
    existing_data["date"] = date_str
    
    # Write back
    with open(output_file, 'w') as f:
        json.dump(existing_data, f, indent=2)

def show_summary():
    """
    Show classification summary across all dates.
    """
    print("=== Classification Summary Across All Dates ===")
    
    # Find all daily scan files
    pattern = os.path.join(DAILY_DIR, "daily-scan-*.jsonl")
    files = glob.glob(pattern)
    
    if not files:
        print("No daily scan files found.")
        return
    
    total_counts = {"GOLD": 0, "SILVER": 0, "BAD": 0, "total": 0}
    
    for filepath in files:
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        classification = record.get("classification", "UNKNOWN")
                        if classification in total_counts:
                            total_counts[classification] += 1
                        else:
                            total_counts["BAD"] += 1  # Treat unknown as bad
                        total_counts["total"] += 1
                    except json.JSONDecodeError:
                        pass  # Skip invalid lines
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
    
    print(f"Total content scanned: {total_counts['total']}")
    print(f"GOLD: {total_counts['GOLD']} ({total_counts['GOLD']/max(total_counts['total'],1)*100:.1f}%)")
    print(f"SILVER: {total_counts['SILVER']} ({total_counts['SILVER']/max(total_counts['total'],1)*100:.1f}%)")
    print(f"BAD: {total_counts['BAD']} ({total_counts['BAD']/max(total_counts['total'],1)*100:.1f}%)")

def list_gold():
    """
    List all gold extractions from extracted files.
    """
    print("=== All Gold Extractions ===")
    
    pattern = os.path.join(EXTRACTED_DIR, "signals-*.json")
    files = glob.glob(pattern)
    
    if not files:
        print("No extracted signals files found.")
        return
    
    all_extractions = []
    for filepath in files:
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                all_extractions.extend(data.get("extractions", []))
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
    
    if not all_extractions:
        print("No gold extractions found.")
        return
    
    for i, ext in enumerate(all_extractions, 1):
        print(f"\n{i}. {ext.get('signal_name', 'Unnamed')}")
        print(f"   Instrument: {ext.get('instrument_type', 'any')}")
        print(f"   Timeframe: {ext.get('timeframe', 'any')}")
        print(f"   Direction: {ext.get('direction_rule', 'FLAT')}")
        print(f"   Entry: {ext.get('entry_condition', 'N/A')}")
        print(f"   Exit: {ext.get('exit_condition', 'N/A')}")
        print(f"   Confidence: {ext.get('confidence_score', 0):.2f}")
        print(f"   Market Logic: {ext.get('market_logic', 'N/A')}")
        source = ext.get('source_attribution', {})
        print(f"   Source: {source.get('file', 'unknown')}:{source.get('line', '?')}")

def main():
    parser = argparse.ArgumentParser(description="Extract trading signals from research content.")
    parser.add_argument("--date", help="Process specific date (YYYY-MM-DD)")
    parser.add_argument("--summary", action="store_true", help="Show classification summary across all dates")
    parser.add_argument("--list-gold", action="store_true", help="Show all gold extractions")
    
    args = parser.parse_args()
    
    if args.summary:
        show_summary()
        return
    
    if args.list_gold:
        list_gold()
        return
    
    # Determine date to process
    if args.date:
        date_str = args.date
        # Validate date format
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print("Error: Date must be in YYYY-MM-DD format")
            return
        
        # Process specific date file
        filename = f"daily-scan-{date_str}.jsonl"
        filepath = os.path.join(DAILY_DIR, filename)
        
        if not os.path.exists(filepath):
            print(f"No research file found for date {date_str}")
            return
        
        print(f"Processing {filepath}...")
        extractions, counts = process_file(filepath, date_str)
        
        print(f"Scanned: {counts['total']} | GOLD: {counts['GOLD']} | SILVER: {counts['SILVER']} | BAD: {counts['BAD']}")
        print(f"Extracted: {len(extractions)} strategies")
        
        if extractions:
            write_daily_extracts(date_str, extractions)
            print(f"Written to {os.path.join(EXTRACTED_DIR, f'signals-{date_str}.json')}")
    
    else:
        # Process all unprocessed content
        print("Processing all unprocessed research content...")
        
        pattern = os.path.join(DAILY_DIR, "daily-scan-*.jsonl")
        files = glob.glob(pattern)
        
        if not files:
            print("No daily scan files found.")
            return
        
        total_extractions = []
        overall_counts = {"GOLD": 0, "SILVER": 0, "BAD": 0, "total": 0}
        
        for filepath in files:
            filename = os.path.basename(filepath)
            # Extract date from filename if possible
            date_match = re.search(r'\d{4}-\d{2}-\d{2}', filename)
            date_str = date_match.group(0) if date_match else None
            
            print(f"Processing {filename}...")
            extractions, counts = process_file(filepath, date_str)
            total_extractions.extend(extractions)
            
            for k in overall_counts:
                overall_counts[k] += counts.get(k, 0)
            
            # Write extractions for this file's date
            if date_str and extractions:
                write_daily_extracts(date_str, extractions)
                print(f"  -> Extracted {len(extractions)} strategies")
        
        print("\n=== Overall Results ===")
        print(f"Total content scanned: {overall_counts['total']}")
        print(f"GOLD: {overall_counts['GOLD']}")
        print(f"SILVER: {overall_counts['SILVER']}")
        print(f"BAD: {overall_counts['BAD']}")
        print(f"Total strategies extracted: {len(total_extractions)}")

if __name__ == "__main__":
    main()