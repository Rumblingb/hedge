#!/usr/bin/env python3
"""
Learning Loop for Self-Evolving Trading System

Tracks research source quality with Bayesian updating, adjusts search priorities,
and provides the learning/evolution mechanism for the hedge fund system.

Features:
- Bayesian Beta distribution tracking for source quality
- Priority adjustment based on quality and confidence scores
- Automatic updating from extraction/dispatch results
- CLI interface for manual updates and status reporting
- Persistent state storage in ~/.rumbling-hedge/learning/
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import math


class SourceTracker:
    """Tracks research source quality using Bayesian Beta distributions."""
    
    def __init__(self, state_dir: Optional[str] = None):
        if state_dir is None:
            state_dir = os.path.expanduser("~/.rumbling-hedge/learning")
        self.state_dir = state_dir
        self.sources_file = os.path.join(state_dir, "source-quality.json")
        self.summary_file = os.path.join(state_dir, "learning-summary.latest.json")
        
        # Ensure state directory exists
        os.makedirs(state_dir, exist_ok=True)
        
        # Load existing sources or initialize empty list
        self.sources = self._load_sources()
    
    def _load_sources(self) -> List[Dict]:
        """Load sources from state file or return empty list."""
        if not os.path.exists(self.sources_file):
            return []
        
        try:
            with open(self.sources_file, 'r') as f:
                data = json.load(f)
                # Ensure backward compatibility
                for source in data:
                    if 'alpha' not in source:
                        source['alpha'] = 1
                    if 'beta' not in source:
                        source['beta'] = 1
                    if 'discovery_date' not in source:
                        source['discovery_date'] = datetime.now(timezone.utc).isoformat()
                    if 'last_scanned' not in source:
                        source['last_scanned'] = None
                return data
        except (json.JSONDecodeError, IOError):
            return []
    
    def _save_sources(self):
        """Save sources to state file."""
        try:
            with open(self.sources_file, 'w') as f:
                json.dump(self.sources, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save sources: {e}", file=sys.stderr)
    
    def _get_source_index(self, name: str) -> Optional[int]:
        """Find index of source by name."""
        for i, source in enumerate(self.sources):
            if source.get('name') == name:
                return i
        return None
    
    def add_source(self, name: str, source_type: str, identifier: str, 
                   discovery_date: Optional[str] = None) -> bool:
        """Add a new source to track."""
        if self._get_source_index(name) is not None:
            return False  # Source already exists
        
        if discovery_date is None:
            discovery_date = datetime.now(timezone.utc).isoformat()
        
        new_source = {
            'name': name,
            'type': source_type,  # youtube/arxiv/twitter/paper
            'identifier': identifier,  # URL, arXiv category, Twitter handle, etc.
            'discovery_date': discovery_date,
            'alpha': 1,  # Beta(1,1) uniform prior
            'beta': 1,
            'quality': 0.5,
            'confidence': 2,
            'priority': 'MEDIUM',  # Will be calculated
            'last_scanned': None
        }
        
        self._update_source_stats(new_source)
        self.sources.append(new_source)
        self._save_sources()
        return True
    
    def update_source_result(self, name: str, result: str) -> bool:
        """Update source based on strategy test result."""
        idx = self._get_source_index(name)
        if idx is None:
            return False
        
        source = self.sources[idx]
        if result == 'win':
            source['alpha'] += 1
        elif result == 'loss':
            source['beta'] += 1
        # neutral -> no update
        
        self._update_source_stats(source)
        self._save_sources()
        return True
    
    def _update_source_stats(self, source: Dict):
        """Update quality, confidence, and priority for a source."""
        alpha = source['alpha']
        beta = source['beta']
        
        # Quality = alpha / (alpha + beta)
        source['quality'] = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5
        
        # Confidence = alpha + beta (more evidence = higher confidence)
        source['confidence'] = alpha + beta
        
        # Priority adjustment based on quality and confidence
        quality = source['quality']
        confidence = source['confidence']
        
        if quality > 0.65 and confidence > 5:
            source['priority'] = 'HIGH'
        elif quality < 0.35 and confidence > 10:
            if quality < 0.2 and confidence > 20:
                source['priority'] = 'PRUNE'
            else:
                source['priority'] = 'LOW'
        else:
            source['priority'] = 'MEDIUM'
    
    def get_sources_by_priority(self, priority: Optional[str] = None) -> List[Dict]:
        """Get sources filtered by priority."""
        if priority is None:
            return self.sources.copy()
        return [s for s in self.sources if s.get('priority') == priority]
    
    def get_source_summary(self) -> Dict:
        """Get summary statistics for all sources."""
        if not self.sources:
            return {
                'total_sources': 0,
                'high_priority': 0,
                'medium_priority': 0,
                'low_priority': 0,
                'prune_candidates': 0,
                'avg_quality': 0.0,
                'avg_confidence': 0.0
            }
        
        high = len([s for s in self.sources if s.get('priority') == 'HIGH'])
        medium = len([s for s in self.sources if s.get('priority') == 'MEDIUM'])
        low = len([s for s in self.sources if s.get('priority') == 'LOW'])
        prune = len([s for s in self.sources if s.get('priority') == 'PRUNE'])
        
        avg_quality = sum(s.get('quality', 0) for s in self.sources) / len(self.sources)
        avg_confidence = sum(s.get('confidence', 0) for s in self.sources) / len(self.sources)
        
        return {
            'total_sources': len(self.sources),
            'high_priority': high,
            'medium_priority': medium,
            'low_priority': low,
            'prune_candidates': prune,
            'avg_quality': round(avg_quality, 3),
            'avg_confidence': round(avg_confidence, 3)
        }
    
    def save_learning_summary(self):
        """Save learning summary to file."""
        summary = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source_summary': self.get_source_summary(),
            'sources': self.sources
        }
        
        try:
            with open(self.summary_file, 'w') as f:
                json.dump(summary, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save learning summary: {e}", file=sys.stderr)


def scan_for_results(tracker: SourceTracker):
    """Scan for new extraction/dispatch results and update sources."""
    research_dir = os.path.expanduser("~/.rumbling-hedge/research/extracted")
    dispatcher_dir = os.path.expanduser("~/.rumbling-hedge/dispatcher")
    
    # Track which sources we've updated to avoid double counting
    updated_sources = set()
    
    # Check extraction results (signals-*.json)
    if os.path.exists(research_dir):
        for filename in os.listdir(research_dir):
            if filename.startswith('signals-') and filename.endswith('.json'):
                filepath = os.path.join(research_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    
                    # Extract source information and results
                    # This is a simplified version - actual implementation would
                    # parse the extraction results to determine which source
                    # each strategy came from and whether it was profitable
                    if 'source' in data and 'results' in data:
                        source_name = data['source']
                        # For simplicity, we'll assume all results in a file
                        # have the same outcome - in reality this would be more complex
                        wins = sum(1 for r in data['results'] if r.get('profitable', False))
                        losses = sum(1 for r in data['results'] if not r.get('profitable', False) and r.get('tested', False))
                        
                        if wins > 0 and source_name not in updated_sources:
                            tracker.update_source_result(source_name, 'win')
                            updated_sources.add(source_name)
                        elif losses > 0 and source_name not in updated_sources:
                            tracker.update_source_result(source_name, 'loss')
                            updated_sources.add(source_name)
                            
                except (json.JSONDecodeError, IOError, KeyError):
                    continue  # Skip malformed files
    
    # Check dispatch results (dispatch-*.json)
    if os.path.exists(dispatcher_dir):
        for filename in os.listdir(dispatcher_dir):
            if filename.startswith('dispatch-') and filename.endswith('.json'):
                filepath = os.path.join(dispatcher_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    
                    # Similar to extraction results
                    if 'source' in data and 'performance' in data:
                        source_name = data['source']
                        performance = data['performance']
                        
                        if performance == 'profitable' and source_name not in updated_sources:
                            tracker.update_source_result(source_name, 'win')
                            updated_sources.add(source_name)
                        elif performance == 'unprofitable' and source_name not in updated_sources:
                            tracker.update_source_result(source_name, 'loss')
                            updated_sources.add(source_name)
                            
                except (json.JSONDecodeError, IOError, KeyError):
                    continue  # Skip malformed files


def print_status_table(tracker: SourceTracker):
    """Print a formatted table of source quality and priorities."""
    sources = tracker.sources
    
    if not sources:
        print("No sources tracked yet.")
        return
    
    # Header
    print(f"{'Name':<20} {'Type':<10} {'Quality':<8} {'Confidence':<10} {'Priority':<10} {'Last Scanned'}")
    print("-" * 80)
    
    # Sort by priority (HIGH first) then by quality descending
    priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'PRUNE': 3}
    sorted_sources = sorted(sources, key=lambda s: (
        priority_order.get(s.get('priority', 'MEDIUM'), 1),
        -s.get('quality', 0)
    ))
    
    for source in sorted_sources:
        name = source.get('name', 'Unknown')[:19]
        source_type = source.get('type', 'unknown')[:9]
        quality = f"{source.get('quality', 0):.3f}"
        confidence = str(source.get('confidence', 0))
        priority = source.get('priority', 'UNKNOWN')[:9]
        last_scanned = source.get('last_scanned') or 'Never'
        if last_scanned != 'Never':
            try:
                dt = datetime.fromisoformat(last_scanned.replace('Z', '+00:00'))
                last_scanned = dt.strftime('%m/%d %H:%M')
            except:
                pass
        
        print(f"{name:<20} {source_type:<10} {quality:<8} {confidence:<10} {priority:<10} {last_scanned}")


def main():
    parser = argparse.ArgumentParser(description='Learning Loop for Self-Evolving Trading System')
    parser.add_argument('--update-source', type=str, help='Update source with test result')
    parser.add_argument('--result', choices=['win', 'loss', 'neutral'], 
                       help='Test result for --update-source (win/loss/neutral)')
    parser.add_argument('--add-source', nargs=3, metavar=('NAME', 'TYPE', 'IDENTIFIER'),
                       help='Add a new source to track (name type identifier)')
    parser.add_argument('--status', action='store_true', help='Print current source quality table')
    parser.add_argument('--report', action='store_true', help='Print full analysis report')
    parser.add_argument('--auto', action='store_true', help='Automatic mode: scan for results and update')
    
    args = parser.parse_args()
    
    tracker = SourceTracker()
    
    if args.add_source:
        name, source_type, identifier = args.add_source
        if tracker.add_source(name, source_type, identifier):
            print(f"Added source: {name} ({source_type})")
        else:
            print(f"Source '{name}' already exists.", file=sys.stderr)
            sys.exit(1)
    
    elif args.update_source:
        if not args.result:
            print("--result is required with --update-source", file=sys.stderr)
            sys.exit(1)
        
        if tracker.update_source_result(args.update_source, args.result):
            print(f"Updated source '{args.update_source}' with result: {args.result}")
        else:
            print(f"Source '{args.update_source}' not found.", file=sys.stderr)
            sys.exit(1)
    
    elif args.status:
        print_status_table(tracker)
    
    elif args.report:
        print("=== LEARNING LOOP REPORT ===")
        print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
        print()
        
        summary = tracker.get_source_summary()
        print("SUMMARY:")
        print(f"  Total Sources: {summary['total_sources']}")
        print(f"  High Priority: {summary['high_priority']}")
        print(f"  Medium Priority: {summary['medium_priority']}")
        print(f"  Low Priority: {summary['low_priority']}")
        print(f"  Prune Candidates: {summary['prune_candidates']}")
        print(f"  Average Quality: {summary['avg_quality']}")
        print(f"  Average Confidence: {summary['avg_confidence']}")
        print()
        
        print("SOURCES:")
        print_status_table(tracker)
        
        # Save summary to file
        tracker.save_learning_summary()
        print(f"\nLearning summary saved to: {tracker.summary_file}")
    
    elif args.auto:
        print("Scanning for new results...")
        scan_for_results(tracker)
        print("Scan complete.")
        print_status_table(tracker)
    
    else:
        # Default behavior: show status
        print_status_table(tracker)


if __name__ == '__main__':
    main()