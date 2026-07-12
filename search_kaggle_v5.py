#!/usr/bin/env python3
"""
Search and download Kaggle futures datasets.
Uses kagglehub library with proper auth.
"""
import os, json, shutil
from datetime import datetime

os.environ['KAGGLE_API_TOKEN'] = 'KGAT_28c44563002626b9e0f7dc3cb10f0e69'

import kagglehub
from kagglehub import KaggleDatasetAdapter

DATA_DIR = "/Users/brain/hedge/data/free"
LOG_FILE = "/Users/brain/hedge/.rumbling-hedge/state/data-download-log.json"

try:
    with open(LOG_FILE) as f:
        download_log = json.load(f)
except:
    download_log = {}

# Check kagglehub auth
print("Checking kagglehub auth...")
try:
    # Try a simple download to test
    path = kagglehub.dataset_download("uciml/iris")
    print(f"kagglehub auth OK. Test download: {path}")
except Exception as e:
    print(f"kagglehub auth test: {e}")

# ── PRIORITY DATASETS FROM SEARCH RESULTS ──
# These are the most relevant ones for our needs:
priority_datasets = [
    # CL (Crude Oil) futures - choweric has good datasets
    "choweric/nymex-cl",
    "youneseloiarm/nymex-crude-oil-futures-dataset-cl-contract",
    
    # GC (Gold) futures
    "choweric/comex-gc",
    "youneseloiarm/comex-gold-futures-dataset-gc-contract",
    "prajwaldongre/gold-futures-data-from-2012-2023",
    
    # 6E (Euro FX) futures
    "choweric/cme-euro",
    
    # General futures
    "choweric/cme-es",
    "choweric/cme-nasdaq",
    "choweric/cme-jpy",
    "guillemservera/fuels-futures-data",
    "guillemservera/precious-metals-data",
    "tgtanalytics/nq-futures-1min-bar-2022-2025",
]

print(f"\nAttempting to download {len(priority_datasets)} datasets...")

success_count = 0
for ds in priority_datasets:
    print(f"\n  >>> {ds}")
    try:
        result_path = kagglehub.dataset_download(ds)
        print(f"  ✅ Downloaded to: {result_path}")
        
        # Copy to data dir
        safe_name = ds.replace("/", "_")
        dest = os.path.join(DATA_DIR, safe_name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(result_path, dest)
        
        # List files
        total_size = 0
        for root, dirs, files in os.walk(dest):
            for f in files:
                fp = os.path.join(root, f)
                s = os.path.getsize(fp)
                total_size += s
                print(f"    \u2022 {os.path.relpath(fp, DATA_DIR)} ({s:,} bytes)")
        
        # Log it
        entry = {
            "dataset": ds,
            "downloaded_at": datetime.now().isoformat(),
            "source": "kaggle",
            "target_dir": dest,
            "total_size_bytes": total_size
        }
        download_log[ds] = entry
        with open(LOG_FILE, "w") as f:
            json.dump(download_log, f, indent=2)
        success_count += 1
        
    except Exception as e:
        print(f"  ❌ {e}")

print(f"\n{'='*60}")
print(f"SUMMARY: {success_count}/{len(priority_datasets)} datasets downloaded")
print(f"{'='*60}")