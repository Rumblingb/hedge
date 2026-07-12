#!/usr/bin/env python3
"""Consolidate FX 1-minute zip files into continuous CSV files."""
import zipfile, csv, glob, os, sys

pair = sys.argv[1]
zip_dir = f"/Users/brain/hedge/data/free/fx-1min/output/{pair}"
out = f"/Users/brain/hedge/data/free/{pair.upper()}-1min.csv"

zips = sorted(glob.glob(f"{zip_dir}/DAT_ASCII_*M1_*.zip"))
if not zips:
    print(f"{pair}: no zip files found in {zip_dir}")
    sys.exit(1)

total = 0
with open(out, 'w', newline='') as out_f:
    w = csv.writer(out_f)
    w.writerow(['datetime', 'open', 'high', 'low', 'close', 'volume'])
    for zpath in zips:
        try:
            with zipfile.ZipFile(zpath) as z:
                csv_name = [n for n in z.namelist() if n.endswith('.csv')][0]
                with z.open(csv_name) as f:
                    lines = f.read().decode('latin-1').strip().split('\n')
                    for line in lines:
                        if not line.strip():
                            continue
                        parts = line.split(';')
                        if len(parts) >= 6:
                            dt_raw = parts[0].strip()
                            dt = f"{dt_raw[:4]}-{dt_raw[4:6]}-{dt_raw[6:8]} {dt_raw[9:11]}:{dt_raw[11:13]}:{dt_raw[13:15]}"
                            w.writerow([dt, parts[1], parts[2], parts[3], parts[4], parts[5]])
                            total += 1
                    print(f"  {os.path.basename(zpath)}: OK", flush=True)
        except Exception as e:
            print(f"  {os.path.basename(zpath)}: ERROR - {e}", flush=True)

sz = os.path.getsize(out) / 1024 / 1024
print(f"\n{pair.upper()}: {total:,} rows, {sz:.1f} MB -> {out}")
