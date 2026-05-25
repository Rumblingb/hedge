#!/usr/bin/env python3
"""
Automated research collection module for a self-evolving trading system.
Scans multiple sources for new trading research content daily.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import time

# Configuration
BASE_DIR = Path.home() / '.rumbling-hedge'
RESEARCH_DIR = BASE_DIR / 'research'
DAILY_DIR = RESEARCH_DIR / 'daily'
PROCESSED_IDS_FILE = RESEARCH_DIR / 'processed-ids.json'
SCANNER_STATUS_FILE = RESEARCH_DIR / 'scanner-status.json'
YOUTUBE_SOURCES_FILE = RESEARCH_DIR / 'sources' / 'youtube-sources.json'

# Default YouTube channels to monitor
DEFAULT_YOUTUBE_CHANNELS = [
    'Better System Trader',
    'Quantpedia',
    'Chat With Traders',
    'The Trading Channel',
    'Trade Ideas',
    'CIY Capital',
    'Brain Truffle',
    'Trading Fanatic',
    'Faiz SMC'
]

# Search topics for SearXNG/web search
SEARCH_TOPICS = [
    'trading strategy edge',
    'NQ futures strategy',
    'quantitative trading research',
    'machine learning trading',
    'order flow analysis',
    'market microstructure',
    'institutional trading patterns'
]

# arXiv categories for quant finance
ARXIV_CATEGORIES = ['q-fin.*']
ARXIV_QUERIES = [
    'trading strategy',
    'market microstructure',
    'portfolio optimization',
    'volatility forecasting',
    'algorithmic trading'
]

def ensure_directories():
    """Ensure all required directories exist."""
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    (RESEARCH_DIR / 'sources').mkdir(parents=True, exist_ok=True)
    (RESEARCH_DIR / 'processed').mkdir(parents=True, exist_ok=True)

def load_processed_ids():
    """Load previously seen content IDs for deduplication."""
    if PROCESSED_IDS_FILE.exists():
        try:
            with open(PROCESSED_IDS_FILE, 'r') as f:
                return set(json.load(f))
        except (json.JSONDecodeError, IOError):
            return set()
    return set()

def save_processed_ids(processed_ids):
    """Save processed content IDs to file."""
    try:
        with open(PROCESSED_IDS_FILE, 'w') as f:
            json.dump(list(processed_ids), f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save processed IDs: {e}")

def load_youtube_sources():
    """Load additional YouTube sources from config file."""
    if YOUTUBE_SOURCES_FILE.exists():
        try:
            with open(YOUTUBE_SOURCES_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and 'channels' in data:
                    return data['channels']
        except (json.JSONDecodeError, IOError):
            pass
    return []

def get_youtube_channels():
    """Get combined list of YouTube channels to monitor."""
    channels = DEFAULT_YOUTUBE_CHANNELS.copy()
    channels.extend(load_youtube_sources())
    # Remove duplicates while preserving order
    seen = set()
    result = []
    for channel in channels:
        if channel not in seen:
            seen.add(channel)
            result.append(channel)
    return result

def is_searxng_available():
    """Check if SearXNG instance is available at localhost:4000."""
    try:
        req = urllib.request.Request('http://localhost:4000/health')
        response = urllib.request.urlopen(req, timeout=5)
        return response.getcode() == 200
    except Exception:
        return False

def search_searxng(query, category=None):
    """Search using SearXNG instance."""
    params = {
        'q': query,
        'format': 'json'
    }
    if category:
        params['categories'] = category
    
    url = f"http://localhost:4000/search?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ResearchCollector/1.0'})
        response = urllib.request.urlopen(req, timeout=10)
        data = json.loads(response.read().decode())
        return data.get('results', [])
    except Exception as e:
        print(f"SearXNG search error for '{query}': {e}")
        return []

def search_web_fallback(query):
    """Fallback web search using site:youtube.com."""
    # This would normally use a search API, but for simplicity we'll simulate
    # In a real implementation, you might use DuckDuckGo instant answer API or similar
    print(f"Web search fallback for: {query} (site:youtube.com)")
    # Return empty list as placeholder - would integrate with actual search in production
    return []

def search_youtube_videos(topics, use_searxng=True):
    """Search for recent YouTube videos on trading topics."""
    videos = []
    
    print(f"Searching YouTube via {'SearXNG' if use_searxng and is_searxng_available() else 'Web Fallback'}...")
    
    for topic in topics:
        try:
            if use_searxng and is_searxng_available():
                results = search_searxng(f"{topic} site:youtube.com", category='videos')
            else:
                results = search_web_fallback(f"{topic} site:youtube.com")
                
            for result in results[:3]:  # Limit results per topic
                video = {
                    'source_type': 'youtube',
                    'source_name': result.get('channel', 'Unknown Channel'),
                    'title': result.get('title', ''),
                    'url': result.get('url', ''),
                    'description': result.get('content', '')[:200],
                    'content_preview': '',  # Would need transcript fetching
                    'discovered_at': datetime.utcnow().isoformat() + 'Z',
                    'content_id': result.get('id', result.get('url', '')),
                    'processed': False
                }
                videos.append(video)
            time.sleep(0.5)  # Be respectful to the search service
        except Exception as e:
            print(f"Error searching for topic '{topic}': {e}")
    
    return videos

def search_arxiv_papers():
    """Search arXiv for recent quant finance papers."""
    papers = []
    base_url = "http://export.arxiv.org/api/query?"
    
    print("Searching arXiv for quant finance papers...")
    
    for query in ARXIV_QUERIES:
        try:
            params = {
                'search_query': f'cat:{ARXIV_CATEGORIES[0]} AND "{query}"',
                'start': 0,
                'max_results': 10,
                'sortBy': 'submittedDate',
                'sortOrder': 'descending'
            }
            url = base_url + urllib.parse.urlencode(params)
            
            req = urllib.request.Request(url, headers={'User-Agent': 'ResearchCollector/1.0'})
            response = urllib.request.urlopen(req, timeout=15)
            data = response.read().decode()
            
            # Simple XML parsing for entry elements
            entries = data.split('<entry>')[1:]  # Skip first split before first entry
            
            for entry in entries[:5]:  # Limit papers per query
                try:
                    # Extract title
                    title_start = entry.find('<title>') + 7
                    title_end = entry.find('</title>', title_start)
                    title = entry[title_start:title_end].strip() if title_start > 6 and title_end > title_start else "Unknown Title"
                    
                    # Extract URL (usually the id field)
                    id_start = entry.find('<id>') + 4
                    id_end = entry.find('</id>', id_start)
                    url = entry[id_start:id_end].strip() if id_start > 3 and id_end > id_start else ""
                    
                    # Extract summary/abstract
                    summary_start = entry.find('<summary>') + 9
                    summary_end = entry.find('</summary>', summary_start)
                    summary = entry[summary_start:summary_end].strip() if summary_start > 8 and summary_end > summary_start else ""
                    
                    # Extract published date
                    published_start = entry.find('<published>') + 11
                    published_end = entry.find('</published>', published_start)
                    published = entry[published_start:published_end].strip() if published_start > 10 and published_end > published_start else ""
                    
                    paper = {
                        'source_type': 'arxiv',
                        'source_name': 'arXiv Quantitative Finance',
                        'title': title,
                        'url': url,
                        'description': summary[:200],
                        'content_preview': summary[:500],
                        'discovered_at': datetime.utcnow().isoformat() + 'Z',
                        'content_id': url.split('/')[-1] if url else f"arxiv-{hash(title)}",
                        'processed': False
                    }
                    papers.append(paper)
                except Exception as e:
                    # Skip malformed entries
                    continue
                    
            time.sleep(1)  # Be respectful to arXiv API
            
        except Exception as e:
            print(f"Error searching arXiv for query '{query}': {e}")
    
    return papers

def check_xurl_available():
    """Check if xurl CLI is available for Twitter/X search."""
    try:
        subprocess.run(['xurl', '--help'], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def search_twitter_x():
    """Search Twitter/X for trading edge content (placeholder)."""
    # This would integrate with xurl or Twitter API if available
    if not check_xurl_available():
        print("xurl CLI not available, skipping Twitter/X search")
        return []
    
    print("Twitter/X search would be performed here with xurl")
    # Placeholder implementation
    return []

def update_scanner_status(source_name, success=True, error_msg=None):
    """Update scanner status file."""
    status = {}
    if SCANNER_STATUS_FILE.exists():
        try:
            with open(SCANNER_STATUS_FILE, 'r') as f:
                status = json.load(f)
        except (json.JSONDecodeError, IOError):
            status = {}
    
    status[source_name] = {
        'last_scan': datetime.utcnow().isoformat() + 'Z',
        'success': success,
        'error': error_msg,
        'scan_count': status.get(source_name, {}).get('scan_count', 0) + 1
    }
    
    try:
        with open(SCANNER_STATUS_FILE, 'w') as f:
            json.dump(status, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not update scanner status: {e}")

def save_daily_results(results, dry_run=False):
    """Save results to JSONL file for today."""
    if not results:
        print("No new content found to save.")
        return
    
    today = datetime.utcnow().strftime('%Y-%m-%d')
    output_file = DAILY_DIR / f'daily-scan-{today}.jsonl'
    
    if dry_run:
        print(f"[DRY RUN] Would save {len(results)} items to {output_file}")
        for result in results[:3]:  # Show first 3 as examples
            print(f"  - {result['source_type']}: {result['title'][:50]}...")
        return
    
    try:
        with open(output_file, 'a') as f:
            for result in results:
                f.write(json.dumps(result) + '\n')
        print(f"Saved {len(results)} new items to {output_file}")
    except IOError as e:
        print(f"Error saving results: {e}")

def scan_sources(sources_to_scan=None, dry_run=False):
    """Scan specified sources for new research content."""
    if sources_to_scan is None:
        sources_to_scan = ['youtube', 'arxiv', 'twitter']
    
    print(f"Starting research scan for sources: {', '.join(sources_to_scan)}")
    if dry_run:
        print("*** DRY RUN MODE - No data will be saved ***")
    
    ensure_directories()
    processed_ids = load_processed_ids()
    all_new_content = []
    
    # Scan YouTube
    if 'youtube' in sources_to_scan:
        try:
            youtube_videos = search_youtube_videos(SEARCH_TOPICS, use_searxng=True)
            new_videos = []
            for video in youtube_videos:
                if video['content_id'] not in processed_ids:
                    new_videos.append(video)
                    processed_ids.add(video['content_id'])
            
            print(f"YouTube: Found {len(youtube_videos)} videos, {len(new_videos)} new")
            all_new_content.extend(new_videos)
            update_scanner_status('youtube', success=True)
        except Exception as e:
            print(f"YouTube scan failed: {e}")
            update_scanner_status('youtube', success=False, error_msg=str(e))
    
    # Scan arXiv
    if 'arxiv' in sources_to_scan:
        try:
            arxiv_papers = search_arxiv_papers()
            new_papers = []
            for paper in arxiv_papers:
                if paper['content_id'] not in processed_ids:
                    new_papers.append(paper)
                    processed_ids.add(paper['content_id'])
            
            print(f"arXiv: Found {len(arxiv_papers)} papers, {len(new_papers)} new")
            all_new_content.extend(new_papers)
            update_scanner_status('arxiv', success=True)
        except Exception as e:
            print(f"arXiv scan failed: {e}")
            update_scanner_status('arxiv', success=False, error_msg=str(e))
    
    # Scan Twitter/X
    if 'twitter' in sources_to_scan:
        try:
            twitter_content = search_twitter_x()
            new_twitter = []
            for item in twitter_content:
                if item['content_id'] not in processed_ids:
                    new_twitter.append(item)
                    processed_ids.add(item['content_id'])
            
            print(f"Twitter/X: Found {len(twitter_content)} items, {len(new_twitter)} new")
            all_new_content.extend(new_twitter)
            update_scanner_status('twitter', success=True)
        except Exception as e:
            print(f"Twitter/X scan failed: {e}")
            update_scanner_status('twitter', success=False, error_msg=str(e))
    
    # Save processed IDs for next run
    save_processed_ids(processed_ids)
    
    # Save results
    save_daily_results(all_new_content, dry_run=dry_run)
    
    return all_new_content

def show_status():
    """Show scanner status and health information."""
    print("=== Research Collector Status ===")
    
    # Show processed IDs count
    processed_ids = load_processed_ids()
    print(f"Processed content IDs: {len(processed_ids)}")
    
    # Show scanner status
    if SCANNER_STATUS_FILE.exists():
        try:
            with open(SCANNER_STATUS_FILE, 'r') as f:
                status = json.load(f)
            
            print("\nScanner Health:")
            for source, info in status.items():
                success_str = "✓ OK" if info.get('success', False) else "✗ FAILED"
                last_scan = info.get('last_scan', 'Never')
                scan_count = info.get('scan_count', 0)
                error = info.get('error', '')
                print(f"  {source}: {success_str} | Last scan: {last_scan} | Count: {scan_count}")
                if error:
                    print(f"    Error: {error}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading scanner status: {e}")
    else:
        print("No scanner status file found.")
    
    # Show YouTube channels
    print(f"\nYouTube Channels to Monitor ({len(get_youtube_channels())}):")
    for channel in get_youtube_channels():
        print(f"  - {channel}")
    
    # Show search topics
    print(f"\nSearch Topics ({len(SEARCH_TOPICS)}):")
    for topic in SEARCH_TOPICS:
        print(f"  - {topic}")
    
    # Show SearXNG availability
    searxng_status = "Available" if is_searxng_available() else "Not Available"
    print(f"\nSearXNG (localhost:4000): {searxng_status}")
    
    # Show xurl availability
    xurl_status = "Available" if check_xurl_available() else "Not Available"
    print(f"xurl CLI for Twitter/X: {xurl_status}")

def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(description='Automated research collection for trading system')
    parser.add_argument('--sources', type=str, help='Comma-separated list of sources to scan (youtube,arxiv,twitter)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be scanned without saving')
    parser.add_argument('--status', action='store_true', help='Show source health and last scan times')
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
        return
    
    # Parse sources
    sources_to_scan = None
    if args.sources:
        sources_to_scan = [s.strip() for s in args.sources.split(',')]
        valid_sources = {'youtube', 'arxiv', 'twitter'}
        invalid = set(sources_to_scan) - valid_sources
        if invalid:
            print(f"Error: Invalid sources specified: {invalid}")
            print(f"Valid sources are: {', '.join(valid_sources)}")
            sys.exit(1)
    
    # Run the scan
    try:
        scan_sources(sources_to_scan=sources_to_scan, dry_run=args.dry_run)
        print("Scan completed successfully.")
    except KeyboardInterrupt:
        print("\nScan interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Scan failed with error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()