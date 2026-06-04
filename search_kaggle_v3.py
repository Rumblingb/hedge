#!/usr/bin/env python3
"""
Search Kaggle for futures datasets using direct HTTP API calls.
Token: KGAT_28c44563002626b9e0f7dc3cb10f0e69
"""
import os
import json
import shutil
import requests
import zipfile
from datetime import datetime

DATA_DIR = "/Users/brain/hedge/data/free"
LOG_FILE = "/Users/brain/hedge/.rumbling-hedge/state/data-download-log.json"

TOKEN = os.environ.get('KAGGLE_API_TOKEN', 'KGAT_28c44563002626b9e0f7dc3cb10f0e69')

# Load existing log
try:
    with open(LOG_FILE) as f:
        download_log = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    download_log = {}

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}

def search_datasets(query, max_results=10):
    """Search Kaggle datasets using the dataset search API."""
    url = "https://www.kaggle.com/api/v1/datasets/list"
    params = {"search": query, "page": 1, "max-size": max_results}
    
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        return None

def download_dataset(dataset_ref):
    """Download a Kaggle dataset by ref (owner/dataset-name)."""
    print(f"\n  Downloading: {dataset_ref}")
    
    url = f"https://www.kaggle.com/api/v1/datasets/{dataset_ref}/download"
    
    try:
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=30)
        if resp.status_code == 200:
            safe_name = dataset_ref.replace("/", "_")
            zip_path = os.path.join(DATA_DIR, f"{safe_name}.zip")
            
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            size = os.path.getsize(zip_path)
            print(f"    Downloaded: {zip_path} ({size:,} bytes)")
            
            # Unzip
            extract_dir = os.path.join(DATA_DIR, safe_name)
            os.makedirs(extract_dir, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
            
            print(f"    Extracted to: {extract_dir}")
            
            # List files
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    fpath = os.path.join(root, f)
                    fsize = os.path.getsize(fpath)
                    print(f"    \u2022 {os.path.relpath(fpath, DATA_DIR)} ({fsize:,} bytes)")
            
            # Log it
            entry = {
                "dataset": dataset_ref,
                "downloaded_at": datetime.now().isoformat(),
                "source": "kaggle",
                "target_dir": extract_dir,
                "zip_path": zip_path,
                "size_bytes": size
            }
            download_log[dataset_ref] = entry
            with open(LOG_FILE, "w") as f:
                json.dump(download_log, f, indent=2)
            
            return True
        else:
            print(f"    HTTP {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"    Error: {e}")
        return False

# ── TEST AUTH FIRST ──
print("═"*60)
print("TESTING KAGGLE API AUTHENTICATION")
print("═"*60)

url = "https://www.kaggle.com/api/v1/datasets/list"
params = {"search": "futures", "page": 1, "max-size": 3}
resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
print(f"Auth test: HTTP {resp.status_code}")
if resp.status_code == 200:
    print("✅ Authentication works!")
else:
    print(f"❌ Auth failed: {resp.text[:300]}")
    
    # Try without Bearer prefix
    print("\nTrying without Bearer prefix...")
    HEADERS2 = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    resp2 = requests.get(url, headers=HEADERS2, params={**params, "token": TOKEN}, timeout=15)
    print(f"  HTTP {resp2.status_code}: {resp2.text[:300]}")

# ── SEARCH ──
print("\n")
print("═"*60)
print("SEARCHING DATASETS")
print("═"*60)

search_queries = [
    "crude oil futures",
    "gold futures",
    "euro fx futures",
    "CL futures",
    "GC futures",
    "6E futures",
    "crude-oil-futures",
    "gold-futures",
    "6E-futures",
    "finnhub",
    "choweric",
    "kukuroo3",
]

all_refs = set()
for query in search_queries:
    print(f"\n--- Searching: '{query}' ---")
    results = search_datasets(query)
    if results:
        for ds in results[:8]:
            ref = ds.get('ref', f"{ds.get('ownerName','?')}/{ds.get('datasetName','?')}")
            title = ds.get('title', ds.get('datasetName', '?'))
            size = ds.get('size', '?')
            print(f"  \u2022 {ref}: {title} ({size})")
            all_refs.add(ref)
    else:
        print("  (no results or error)")

print(f"\nTotal unique datasets found: {len(all_refs)}")

# Add known dataset refs
known_refs = [
    "choweric/intraday-futures-data",
    "finnhub/crude-oil-futures",
    "finnhub/gold-futures",
    "finnhub/euro-fx-futures",
]
all_refs.update(known_refs)

# ── DOWNLOAD ──
print("\n")
print("═"*60)
print("DOWNLOADING DATASETS")
print("═"*60)

success_count = 0
for ref in sorted(all_refs):
    if download_dataset(ref):
        success_count += 1

print(f"\n{'='*60}")
print(f"FINAL SUMMARY: {success_count}/{len(all_refs)} datasets downloaded successfully.")
print(f"{'='*60}")