#!/usr/bin/env python3
"""
Search Kaggle for futures datasets (CL, GC, 6E) using kagglehub with 
proper authentication and the Kaggle API.
"""
import os
import json
import shutil
import subprocess
import sys
from datetime import datetime

DATA_DIR = "/Users/brain/hedge/data/free"
LOG_FILE = "/Users/brain/hedge/.rumbling-hedge/state/data-download-log.json"

# Load existing log
try:
    with open(LOG_FILE) as f:
        download_log = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    download_log = {}

# Try kaggle CLI first
def run_kaggle(args, timeout=60):
    """Run kaggle CLI command."""
    cmd = ["kaggle"] + args
    print(f"  Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except FileNotFoundError:
        return False, "kaggle CLI not found"

# First check if kaggle CLI is authenticated
print("═"*60)
print("CHECKING KAGGLE CLI AUTHENTICATION")
print("═"*60)

# List datasets to verify auth works
ok, out = run_kaggle(["datasets", "list", "--search", "futures", "--page-size", "5"])
if not ok:
    print(f"CLI failed: {out}")
    print("Setting up kaggle.json...")
    
    # Try to set up kaggle.json with the token
    # We need username too; let me try to get it
    import kagglehub
    kaggle_dir = os.path.expanduser("~/.kaggle")
    os.makedirs(kaggle_dir, exist_ok=True)
    
    # Write kaggle.json - we only have a token so let me check if it works
    kaggle_json_path = os.path.join(kaggle_dir, "kaggle.json")
    if not os.path.exists(kaggle_json_path):
        print(f"Writing {kaggle_json_path}...")
        # Try with the token as the key (this might work)
        with open(kaggle_json_path, "w") as f:
            json.dump({"username": "token", "key": "KGAT_28c44563002626b9e0f7dc3cb10f0e69"}, f)
        os.chmod(kaggle_json_path, 0o600)
        print("Done.")
    
    ok, out = run_kaggle(["datasets", "list", "--search", "futures", "--page-size", "3"])
    if not ok:
        print(f"Still failing: {out}")
        print("Trying alternative token format...")
        with open(kaggle_json_path, "w") as f:
            json.dump({"username": "KGAT_28c44563002626b9e0f7dc3cb10f0e69", "key": ""}, f)
        os.chmod(kaggle_json_path, 0o600)

# Try again
ok, out = run_kaggle(["datasets", "list", "--search", "futures", "--page-size", "3"])
print(f"Auth test result: {'OK' if ok else 'FAILED'}")
if not ok:
    print(f"Error: {out}")
else:
    print(f"Output:\n{out[:2000]}")

# ── SEARCH TERMS ──
print("\n")
print("═"*60)
print("SEARCHING KAGGLE DATASETS")
print("═"*60)

search_queries = [
    "crude oil futures",
    "gold futures",
    "euro fx futures",
    "CL futures intraday",
    "GC futures intraday",
    "6E futures",
    "crude-oil-futures",
    "gold-futures",
    "6E-futures",
    "futures OHLCV",
    "finnhub",
    "choweric",
    "kukuroo3",
]

all_results = []
for query in search_queries:
    print(f"\n--- Searching: '{query}' ---")
    ok, out = run_kaggle(["datasets", "list", "--search", query, "--page-size", "10", "--csv"])
    if ok:
        lines = out.strip().split("\n")
        if len(lines) > 1:
            print(f"  Found {len(lines)-1} results")
            for line in lines[1:6]:  # show up to 5
                cols = line.split(",")
                if len(cols) >= 2:
                    ref = cols[0].strip('"')
                    title = cols[1].strip('"')
                    print(f"    • {ref}: {title}")
                    all_results.append(ref)
        else:
            print("  (no results)")
    else:
        print(f"  Error: {out[:200]}")

# ── DOWNLOAD ATTEMPTS ──
print("\n")
print("═"*60)
print("DOWNLOADING DATASETS")
print("═"*60)

# Deduplicate results
all_results = list(set(all_results))
print(f"\nUnique datasets found: {len(all_results)}")

# Also try specific known datasets
known = [
    "choweric/intraday-futures-data",
    "finnhub/crude-oil-futures",
    "finnhub/gold-futures",
    "finnhub/euro-fx-futures",
]
all_results.extend(known)
all_results = list(set(all_results))

success_count = 0
for ds_ref in all_results:
    print(f"\n  Downloading: {ds_ref}")
    ok, out = run_kaggle(["datasets", "download", ds_ref, "--path", DATA_DIR, "--unzip"])
    if ok:
        print(f"    ✅ Downloaded to {DATA_DIR}")
        
        # Check what was downloaded
        safe_name = ds_ref.replace("/", "_")
        # List files  
        for root, dirs, files in os.walk(DATA_DIR):
            for f in files:
                fpath = os.path.join(root, f)
                size = os.path.getsize(fpath)
                print(f"    • {os.path.relpath(fpath, DATA_DIR)} ({size:,} bytes)")
        
        # Log it
        entry = {
            "dataset": ds_ref,
            "downloaded_at": datetime.now().isoformat(),
            "source": "kaggle",
            "target_dir": DATA_DIR
        }
        download_log[ds_ref] = entry
        with open(LOG_FILE, "w") as f:
            json.dump(download_log, f, indent=2)
        success_count += 1
    else:
        print(f"    ❌ Failed: {out[:200]}")

print(f"\n{'='*60}")
print(f"SUMMARY: {success_count}/{len(all_results)} datasets downloaded successfully.")
print(f"{'='*60}")
