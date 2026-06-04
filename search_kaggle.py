#!/usr/bin/env python3
"""Search Kaggle for futures datasets (CL, GC, 6E) and download them."""
import os
import json
import sys

# Set token
os.environ['KAGGLE_API_TOKEN'] = 'KGAT_28c44563002626b9e0f7dc3cb10f0e69'

import kagglehub
from kagglehub import KaggleDatasetAdapter
import tempfile

DATA_DIR = "/Users/brain/hedge/data/free"
LOG_FILE = "/Users/brain/hedge/.rumbling-hedge/state/data-download-log.json"

# Load existing log
try:
    with open(LOG_FILE) as f:
        download_log = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    download_log = {}

# ── Search terms to try ──
search_terms = [
    # General futures searches
    "crude oil futures",
    "gold futures",
    "euro fx futures",
    "CL futures",
    "GC futures",
    "6E futures",
    "futures intraday OHLCV",
    # Hyphenated for datasets
    "crude-oil-futures",
    "gold-futures",
    "6E-futures",
    # Specific authors/datasets
    "finnhub",
    "choweric",
    "kukuroo3",
]

# Specific known datasets to try
known_datasets = [
    "finnhub/crude-oil-futures",
    "finnhub/gold-futures",
    "finnhub/euro-fx-futures",
    "finnhub/CL-futures",
    "finnhub/GC-futures",
    "finnhub/6E-futures",
    "choweric/crude-oil-futures",
    "choweric/gold-futures",
    "choweric/euro-fx-futures",
    "choweric/intraday-futures-data",
    "kukuroo3/crude-oil-futures",
    "kukuroo3/gold-futures",
    "kukuroo3/euro-fx-futures",
    "kukuroo3/intraday-futures",
]

def try_download(dataset_path):
    """Try to download a Kaggle dataset by its path (author/dataset)."""
    print(f"\n{'='*60}")
    print(f"Trying: {dataset_path}")
    print(f"{'='*60}")
    try:
        # Download to our data dir
        result = kagglehub.dataset_download(dataset_path)
        print(f"  → Download path: {result}")
        
        # List what we got
        for root, dirs, files in os.walk(result):
            for f in files:
                fpath = os.path.join(root, f)
                size = os.path.getsize(fpath)
                print(f"  • {f} ({size:,} bytes)")
        
        # Copy to data/free
        import shutil
        safe_name = dataset_path.replace("/", "_").replace("\\", "_")
        dest = os.path.join(DATA_DIR, safe_name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(result, dest)
        print(f"  ✅ Copied to: {dest}")
        
        # Log it
        entry = {
            "dataset": dataset_path,
            "downloaded_at": __import__('datetime').datetime.now().isoformat(),
            "source": "kaggle",
            "target_dir": dest
        }
        download_log[dataset_path] = entry
        
        # Save log
        with open(LOG_FILE, "w") as f:
            json.dump(download_log, f, indent=2)
        print(f"  ✅ Logged to {LOG_FILE}")
        return True
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return False

def search_kaggle(query):
    """Search Kaggle and return results."""
    print(f"\n--- Searching Kaggle for: '{query}' ---")
    try:
        results = list(kagglehub.search(query))[:5]
        for r in results:
            print(f"  Found: {r}")
        return results
    except Exception as e:
        print(f"  Search failed: {e}")
        return []

# ── Step 1: Try to search ──
print("╔" + "═"*58 + "╗")
print("║  KAGGLE DATASET SEARCH — CL, GC, 6E Futures                     ║")
print("╚" + "═"*58 + "╝")

for term in search_terms:
    search_kaggle(term)

# ── Step 2: Try known datasets ──
print("\n\n╔" + "═"*58 + "╗")
print("║  ATTEMPTING DOWNLOADS                                           ║")
print("╚" + "═"*58 + "╝")

success_count = 0
for ds in known_datasets:
    if try_download(ds):
        success_count += 1

print(f"\n{'='*60}")
print(f"SUMMARY: {success_count}/{len(known_datasets)} datasets downloaded successfully.")
print(f"{'='*60}")
