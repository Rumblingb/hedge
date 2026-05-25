#!/usr/bin/env python3
"""
Strategy Dispatcher for Hedge Trading System
Routes extracted strategies to the correct engine for testing/execution.
"""

import json
import os
import sys
import hashlib
import uuid
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Set, Optional

# Configuration paths
HOME = Path.home()
RUMBLING_HEDGE_DIR = HOME / ".rumbling-hedge"
EXTRACTED_DIR = RUMBLING_HEDGE_DIR / "research" / "extracted"
DISPATCHER_DIR = RUMBLING_HEDGE_DIR / "dispatcher"
TARGETS_DIR = DISPATCHER_DIR / "targets"
HISTORY_FILE = DISPATCHER_DIR / "dispatch-history.jsonl"
SEEN_HASHES_FILE = DISPATCHER_DIR / "seen-hashes.json"

# Ensure directories exist
for directory in [EXTRACTED_DIR, DISPATCHER_DIR, TARGETS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


class StrategyDispatcher:
    def __init__(self):
        self.seen_hashes: Set[str] = self._load_seen_hashes()
        self.dispatch_history: List[Dict] = self._load_dispatch_history()
    
    def _load_seen_hashes(self) -> Set[str]:
        """Load previously seen signal hashes to avoid duplicates."""
        if SEEN_HASHES_FILE.exists():
            try:
                with open(SEEN_HASHES_FILE, 'r') as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, IOError):
                return set()
        return set()
    
    def _save_seen_hashes(self):
        """Save seen hashes to file."""
        with open(SEEN_HASHES_FILE, 'w') as f:
            json.dump(list(self.seen_hashes), f, indent=2)
    
    def _load_dispatch_history(self) -> List[Dict]:
        """Load dispatch history from JSONL file."""
        history = []
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            history.append(json.loads(line))
            except (json.JSONDecodeError, IOError):
                pass
        return history
    
    def _append_to_history(self, dispatch_record: Dict):
        """Append a dispatch record to history file."""
        with open(HISTORY_FILE, 'a') as f:
            f.write(json.dumps(dispatch_record) + '\n')
        self.dispatch_history.append(dispatch_record)
    
    def _generate_signal_hash(self, signal: Dict) -> str:
        """Generate a unique hash for a signal based on signal_name and source_url."""
        signal_name = signal.get('signal_name', '')
        source_url = signal.get('source_url', '')
        hash_string = f"{signal_name}:{source_url}"
        return hashlib.md5(hash_string.encode()).hexdigest()
    
    def _route_strategy(self, signal: Dict) -> Optional[str]:
        """
        Route a signal to the appropriate engine.
        Returns the target engine name or None if no match.
        """
        instrument_type = signal.get('instrument_type', '').lower()
        
        # Bill TS Engine (futures strategies)
        if (instrument_type == 'futures' and 
            signal.get('entry_condition') and 
            signal.get('exit_condition')):
            return 'bill-ts'
        
        # Gengar / Polymarket (prediction market)
        if instrument_type in ['prediction_market', 'crypto']:
            return 'gengar'
        
        # Python Arsenal (signal generators)
        if signal.get('description') and ('signal' in signal.get('description', '').lower() or 
                                          'formula' in signal.get('description', '').lower()):
            return 'python-arsenal'
        
        # TradingAgents / AI Debate (regime/macro-level insights)
        if (signal.get('regime') or 
            signal.get('market_logic', '').lower().find('macro') != -1 or
            signal.get('market_logic', '').lower().find('sentiment') != -1 or
            len(signal.get('related_instruments', [])) > 1):
            return 'ai-debate'
        
        # Default to Python Arsenal for unclassified signals
        return 'python-arsenal'
    
    def _prepare_dispatch_data(self, signal: Dict, target: str) -> Dict:
        """Prepare data for dispatch based on target engine."""
        base_data = {
            "signal_name": signal.get('signal_name', ''),
            "entry_condition": signal.get('entry_condition', ''),
            "exit_condition": signal.get('exit_condition', ''),
            "direction": signal.get('direction', ''),
            "timeframe": signal.get('timeframe', ''),
            "market_logic": signal.get('market_logic', ''),
            "source_url": signal.get('source_url', ''),
            "confidence": signal.get('confidence', 0.0)
        }
        
        # Remove empty fields
        return {k: v for k, v in base_data.items() if v != '' and v != 0.0}
    
    def _write_target_file(self, target: str, data: Dict):
        """Write data to the appropriate target file."""
        target_files = {
            'bill-ts': 'bill-ts-pending.json',
            'gengar': 'gengar-pending.json',
            'python-arsenal': 'python-arsenal-pending.json',
            'ai-debate': 'ai-debate-pending.json'
        }
        
        if target not in target_files:
            raise ValueError(f"Unknown target: {target}")
        
        target_file = TARGETS_DIR / target_files[target]
        
        # Read existing data or initialize empty list
        existing_data = []
        if target_file.exists():
            try:
                with open(target_file, 'r') as f:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        existing_data = []
            except (json.JSONDecodeError, IOError):
                existing_data = []
        
        # Append new data and write back
        existing_data.append(data)
        with open(target_file, 'w') as f:
            json.dump(existing_data, f, indent=2)
    
    def process_extraction_file(self, filepath: Path) -> Dict[str, List]:
        """Process a single extraction file and return routed signals."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading {filepath}: {e}")
            return {}
        
        # Handle different possible structures
        signals = []
        if isinstance(data, list):
            signals = data
        elif isinstance(data, dict):
            if 'signals' in data:
                signals = data['signals']
            elif 'strategies' in data:
                signals = data['strategies']
            else:
                # Treat the dict as a single signal
                signals = [data]
        
        routes = {
            'bill-ts': [],
            'gengar': [],
            'python-arsenal': [],
            'ai-debate': []
        }
        
        for signal in signals:
            if not isinstance(signal, dict):
                continue
            
            # Check for duplicates
            signal_hash = self._generate_signal_hash(signal)
            if signal_hash in self.seen_hashes:
                continue
            
            # Route the signal
            target = self._route_strategy(signal)
            if target is None:
                continue
            
            # Prepare dispatch data
            dispatch_data = self._prepare_dispatch_data(signal, target)
            if not dispatch_data:
                continue
            
            # Add to seen hashes and routes
            self.seen_hashes.add(signal_hash)
            routes[target].append(dispatch_data)
            
            # Write to target file
            self._write_target_file(target, dispatch_data)
        
        return routes
    
    def process_date(self, target_date: str) -> Dict:
        """Process all extraction files for a specific date."""
        date_pattern = f"signals-{target_date}.json"
        extraction_files = list(EXTRACTED_DIR.glob(date_pattern))
        
        if not extraction_files:
            print(f"No extraction files found for date {target_date}")
            return {
                "date": target_date,
                "extractions_processed": 0,
                "routes": {
                    "bill-ts": [],
                    "gengar": [],
                    "python-arsenal": [],
                    "ai-debate": []
                },
                "total_dispatched": 0
            }
        
        all_routes = {
            "bill-ts": [],
            "gengar": [],
            "python-arsenal": [],
            "ai-debate": []
        }
        total_processed = 0
        
        for filepath in extraction_files:
            print(f"Processing {filepath.name}...")
            routes = self.process_extraction_file(filepath)
            total_processed += 1
            
            for target in all_routes:
                all_routes[target].extend(routes[target])
        
        # Generate dispatch ID
        dispatch_id = str(uuid.uuid4())
        
        # Create dispatch record
        dispatch_record = {
            "dispatch_id": dispatch_id,
            "date": target_date,
            "timestamp": datetime.now().isoformat(),
            "extractions_processed": total_processed,
            "routes": all_routes,
            "total_dispatched": sum(len(strategies) for strategies in all_routes.values())
        }
        
        # Save to history
        self._append_to_history(dispatch_record)
        
        # Create daily dispatch file
        daily_file = DISPATCHER_DIR / f"dispatch-{target_date}.json"
        with open(daily_file, 'w') as f:
            json.dump({
                "date": target_date,
                "extractions_processed": total_processed,
                "routes": all_routes,
                "total_dispatched": dispatch_record["total_dispatched"]
            }, f, indent=2)
        
        return {
            "date": target_date,
            "extractions_processed": total_processed,
            "routes": all_routes,
            "total_dispatched": dispatch_record["total_dispatched"]
        }
    
    def process_all_undispatched(self) -> Dict:
        """Process all extraction files that haven't been dispatched yet."""
        extraction_files = list(EXTRACTED_DIR.glob("signals-*.json"))
        
        if not extraction_files:
            print("No extraction files found")
            return {
                "date": "all",
                "extractions_processed": 0,
                "routes": {
                    "bill-ts": [],
                    "gengar": [],
                    "python-arsenal": [],
                    "ai-debate": []
                },
                "total_dispatched": 0
            }
        
        all_routes = {
            "bill-ts": [],
            "gengar": [],
            "python-arsenal": [],
            "ai-debate": []
        }
        total_processed = 0
        dates_processed = set()
        
        for filepath in extraction_files:
            # Extract date from filename
            filename = filepath.name
            if filename.startswith("signals-") and filename.endswith(".json"):
                date_str = filename[8:-5]  # Remove "signals-" and ".json"
                dates_processed.add(date_str)
            
            print(f"Processing {filename}...")
            routes = self.process_extraction_file(filepath)
            total_processed += 1
            
            for target in all_routes:
                all_routes[target].extend(routes[target])
        
        # Generate dispatch ID
        dispatch_id = str(uuid.uuid4())
        today = date.today().isoformat()
        
        # Create dispatch record
        dispatch_record = {
            "dispatch_id": dispatch_id,
            "date": today,
            "timestamp": datetime.now().isoformat(),
            "extractions_processed": total_processed,
            "routes": all_routes,
            "total_dispatched": sum(len(strategies) for strategies in all_routes.values())
        }
        
        # Save to history
        self._append_to_history(dispatch_record)
        
        # Update seen hashes
        self._save_seen_hashes()
        
        return {
            "date": "all",
            "extractions_processed": total_processed,
            "routes": all_routes,
            "total_dispatched": dispatch_record["total_dispatched"]
        }
    
    def show_target_pending(self, target: str):
        """Show pending dispatches for a target."""
        target_files = {
            'bill-ts': 'bill-ts-pending.json',
            'gengar': 'gengar-pending.json',
            'python-arsenal': 'python-arsenal-pending.json',
            'ai-debate': 'ai-debate-pending.json'
        }
        
        if target not in target_files:
            print(f"Unknown target: {target}")
            return
        
        target_file = TARGETS_DIR / target_files[target]
        if not target_file.exists():
            print(f"No pending dispatches for {target}")
            return
        
        try:
            with open(target_file, 'r') as f:
                data = json.load(f)
                print(f"Pending dispatches for {target}:")
                print(json.dumps(data, indent=2))
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading {target_file}: {e}")
    
    def show_status(self):
        """Show dispatch summary by target."""
        print("Dispatch Summary:")
        print("=" * 50)
        
        # Count from history
        target_counts = {
            'bill-ts': 0,
            'gengar': 0,
            'python-arsenal': 0,
            'ai-debate': 0
        }
        
        for record in self.dispatch_history:
            for target in target_counts:
                target_counts[target] += len(record.get('routes', {}).get(target, []))
        
        for target, count in target_counts.items():
            print(f"{target}: {count} dispatches")
        
        print(f"\nTotal dispatches: {sum(target_counts.values())}")
        print(f"Unique signals seen: {len(self.seen_hashes)}")
    
    def update_hashes_from_history(self):
        """Update seen-hashes from dispatch history."""
        print("Updating seen-hashes from dispatch history...")
        new_hashes = set()
        
        for record in self.dispatch_history:
            for target in ['bill-ts', 'gengar', 'python-arsenal', 'ai-debate']:
                for signal in record.get('routes', {}).get(target, []):
                    # Reconstruct hash from signal data
                    signal_name = signal.get('signal_name', '')
                    source_url = signal.get('source_url', '')
                    hash_string = f"{signal_name}:{source_url}"
                    signal_hash = hashlib.md5(hash_string.encode()).hexdigest()
                    new_hashes.add(signal_hash)
        
        self.seen_hashes = new_hashes
        self._save_seen_hashes()
        print(f"Updated seen-hashes with {len(self.seen_hashes)} unique signals")


def main():
    parser = argparse.ArgumentParser(description='Strategy Dispatcher for Hedge Trading System')
    parser.add_argument('--date', help='Process specific date (YYYY-MM-DD)')
    parser.add_argument('--target', help='Show pending dispatches for a target (bill-ts, gengar, python-arsenal, ai-debate)')
    parser.add_argument('--status', action='store_true', help='Show dispatch summary by target')
    parser.add_argument('--hashes', action='store_true', help='Update seen-hashes from history')
    
    args = parser.parse_args()
    
    dispatcher = StrategyDispatcher()
    
    if args.hashes:
        dispatcher.update_hashes_from_history()
        return
    
    if args.status:
        dispatcher.show_status()
        return
    
    if args.target:
        dispatcher.show_target_pending(args.target)
        return
    
    if args.date:
        # Validate date format
        try:
            datetime.strptime(args.date, '%Y-%m-%d')
            result = dispatcher.process_date(args.date)
            print(f"\nDispatch completed for {args.date}:")
            print(json.dumps(result, indent=2))
        except ValueError:
            print("Error: Date must be in YYYY-MM-DD format")
            sys.exit(1)
    else:
        # Process all undispatched extractions
        result = dispatcher.process_all_undispatched()
        print(f"\nDispatch completed:")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()