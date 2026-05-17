#!/usr/bin/env python3
"""Fetch daily GEX levels from haus-edge/gex-levels repo and save as JSON."""
import json, os, logging, sys
from datetime import datetime, timezone

GEX_URLS = {
    "spx": "https://raw.githubusercontent.com/haus-edge/gex-levels/master/data/gex_SPX.txt",
    "qqq": "https://raw.githubusercontent.com/haus-edge/gex-levels/master/data/gex_QQQ.txt",
}
OUTPUT_DIR = os.path.expanduser("~/.rumbling-hedge/state")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "gex_levels.json")
LOG_DIR = os.path.expanduser("~/.rumbling-hedge/logs")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(LOG_DIR, "gex_fetch.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

def parse_gex_file(source: str, text: str) -> dict:
    """Parse a GEX text file into structured levels."""
    levels = {"gamma_flip": None, "call_wall": None, "put_wall": None, "zero_gamma": None, "total_gex": None}
    for line in text.strip().split("\n"):
        line = line.strip()
        if "=" in line:
            parts = line.split("=", 1)
            key = parts[0].strip().lower().replace(" ", "_")
            try:
                val = float(parts[1].strip())
                if "gamma" in key or "flip" in key:
                    levels["gamma_flip"] = val
                elif "call" in key and "wall" in key:
                    levels["call_wall"] = val
                elif "put" in key and "wall" in key:
                    levels["put_wall"] = val
                elif "zero" in key and "gamma" in key:
                    levels["zero_gamma"] = val
                elif "total" in key and "gex" in key:
                    levels["total_gex"] = val
            except (ValueError, IndexError):
                pass
    return levels

try:
    import urllib.request
    combined = {"timestamp": datetime.now(timezone.utc).isoformat(), "spx": {}, "qqq": {}}
    
    for source, url in GEX_URLS.items():
        try:
            response = urllib.request.urlopen(url, timeout=15)
            raw = response.read().decode("utf-8").strip()
            combined[source] = parse_gex_file(source, raw)
            logging.info(f"{source.upper()} GEX: {combined[source]}")
        except Exception as e:
            logging.warning(f"{source.upper()} fetch failed: {e}")
    
    with open(OUTPUT_PATH, "w") as f:
        json.dump(combined, f, indent=2)
    
    spx = combined["spx"]
    print(f"GEX levels saved. SPX: gamma_flip={spx.get('gamma_flip')}, call_wall={spx.get('call_wall')}, put_wall={spx.get('put_wall')}")
    
except Exception as e:
    fallback = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "spx": {"gamma_flip": None, "call_wall": None, "put_wall": None, "zero_gamma": None},
        "qqq": {"gamma_flip": None, "call_wall": None, "put_wall": None, "zero_gamma": None},
        "error": str(e)
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(fallback, f, indent=2)
    print(f"GEX fetch failed: {e}", file=sys.stderr)
    logging.error(f"GEX fetch failed: {e}")
