#!/usr/bin/env python3
"""
Search and download Kaggle futures datasets using the Kaggle API.
"""
import os, json, requests, zipfile
from datetime import datetime

DATA_DIR = "/Users/brain/hedge/data/free"
LOG_FILE = "/Users/brain/hedge/.rumbling-hedge/state/data-download-log.json"

TOKEN = os.environ.get('KAGGLE_API_TOKEN', 'KGAT_28c44563002626b9e0f7dc3cb10f0e69')

try:
    with open(LOG_FILE) as f:
        download_log = json.load(f)
except:
    download_log = {}

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": "Kaggle-API/1.0"
}

def search_datasets(query, max_results=10):
    """Search using Kaggle Datasets API."""
    url = "https://www.kaggle.com/api/v1/datasets/list"
    params = {"search": query, "page": 1}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
    if resp.status_code == 200:
        data = resp.json()
        return data[:max_results] if isinstance(data, list) else []
    else:
        print(f"  HTTP {resp.status_code}: {resp.text[:150]}")
        return None

def download_dataset(dataset_ref):
    """Download a Kaggle dataset."""
    print(f"\n  >>> Downloading: {dataset_ref}")
    url = f"https://www.kaggle.com/api/v1/datasets/{dataset_ref}/download"
    
    try:
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=60)
        if resp.status_code == 200:
            safe = dataset_ref.replace("/", "_")
            zip_path = os.path.join(DATA_DIR, f"{safe}.zip")
            
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            
            size = os.path.getsize(zip_path)
            print(f"    Saved: {zip_path} ({size:,} bytes)")
            
            if size > 0:
                extract_dir = os.path.join(DATA_DIR, safe)
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(extract_dir)
                
                print(f"    Extracted to: {extract_dir}")
                for root, dirs, files in os.walk(extract_dir):
                    for f in files:
                        fp = os.path.join(root, f)
                        print(f"    \u2022 {os.path.relpath(fp, DATA_DIR)} ({os.path.getsize(fp):,} bytes)")
                
                download_log[dataset_ref] = {
                    "dataset": dataset_ref,
                    "downloaded_at": datetime.now().isoformat(),
                    "source": "kaggle",
                    "target_dir": extract_dir,
                    "zip_path": zip_path,
                    "size_bytes": size
                }
                with open(LOG_FILE, "w") as f:
                    json.dump(download_log, f, indent=2)
                return True
            return False
        else:
            print(f"    HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"    Error: {e}")
        return False

# ── TEST AUTH ──
print("="*60)
print("TESTING KAGGLE API AUTH")
print("="*60)

resp = requests.get("https://www.kaggle.com/api/v1/datasets/list", 
                     headers=HEADERS, params={"search": "futures", "page": 1, "sortBy": "hottest"}, timeout=15)
print(f"Auth test: HTTP {resp.status_code}")
if resp.status_code == 401:
    print("❌ Unauthorized - token not valid for Bearer auth")
elif resp.status_code == 200:
    print("✅ Authenticated!")
else:
    print(f"  Response: {resp.text[:200]}")

# ── SEARCH ──
print("\n" + "="*60)
print("SEARCHING KAGGLE DATASETS")
print("="*60)

queries = [
    "crude oil futures", "gold futures", "euro fx futures",
    "CL futures", "GC futures", "6E futures",
    "crude-oil-futures", "gold-futures", "6E-futures",
    "finnhub", "choweric", "kukuroo3",
    "intraday futures OHLCV",
]

all_refs = set()
for q in queries:
    print(f"\n--- '{q}' ---")
    results = search_datasets(q)
    if results is None:
        print("  (API error)")
    elif len(results) == 0:
        print("  (no results)")
    else:
        for ds in results:
            ref = ds.get('ref', '?')
            title = ds.get('title', '?')
            size = ds.get('size', '?')
            ds_name = ds.get('datasetName', '?')
            owner = ds.get('ownerName', '?')
            print(f"  \u2022 {ref}: {title} [{size}]")
            all_refs.add(ref)

print(f"\nUnique: {len(all_refs)} datasets")

# ── DOWNLOAD ──
print("\n" + "="*60)
print("DOWNLOADING")
print("="*60)

if len(all_refs) > 0:
    for ref in sorted(all_refs):
        download_dataset(ref)
else:
    print("No datasets found to download via search.")
    print("\nTrying known dataset paths...")
    known = [
        "choweric/intraday-futures-data",
        "finnhub/crude-oil-futures",
        "finnhub/gold-futures",
        "finnhub/euro-fx-futures",
    ]
    for ref in known:
        download_dataset(ref)

print(f"\n{'='*60}")
print("DONE")
print(f"Check log: {LOG_FILE}")
print(f"{'='*60}")