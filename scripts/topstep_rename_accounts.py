#!/usr/bin/env python3
"""List and rename TopstepX demo accounts via their API."""

import json, os, sys
from pathlib import Path
from urllib.request import Request, urlopen

ENV_PATH = Path.home() / "Library/Application Support/AgentPay/bill/bill.env"
API_BASE = "https://api.topstepx.com"

def read_env(k: str) -> str | None:
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "): line = line[7:]
        if "=" in line:
            key, val = line.split("=", 1)
            if key.strip() == k:
                return val.strip().strip("'\"").strip()
    return None

def api_post(path: str, body: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(f"{API_BASE}{path}", data=json.dumps(body).encode(), headers=headers)
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def main():
    api_key = read_env("RH_TOPSTEP_API_KEY")
    username = read_env("RH_TOPSTEP_USERNAME")
    if not api_key or not username:
        print("Cannot read API credentials from bill.env")
        sys.exit(1)

    # Login
    token = api_post("/api/Auth/loginKey", {
        "apiKey": api_key, "userName": username,
        "applicationId": 0, "applicationVersion": "1.0.0"
    })["token"]
    print("✅ Logged in to TopstepX")

    # List accounts
    accounts = api_post("/api/Account/list", {}, token)
    print(f"\nAccounts ({len(accounts) if isinstance(accounts, list) else '?'}):")
    
    target_ids = {
        "97442788": "LIVE TRADING",
        "83651531": "DEMO 100K",
        "28339015": "TEST 50K A",
        "71363980": "TEST 50K B",
    }
    
    for acct in (accounts if isinstance(accounts, list) else []):
        aid = str(acct.get("accountId", ""))
        name = acct.get("name", "")
        acc_type = acct.get("accountTypeName", "")
        is_live = acct.get("isLive", False)
        
        # Check if this account ID ends with one of our targets
        match = None
        for suffix, label in target_ids.items():
            if aid.endswith(suffix):
                match = (suffix, label)
                break
        
        if match:
            suffix, label = match
            print(f"\n  🎯 ID={aid}  current_name='{name}'  type={acc_type}  live={is_live}")
            print(f"     Target: '{label}'")
            
            # Only rename demo accounts (not live)
            if not is_live:
                try:
                    result = api_post("/api/Account/update", {
                        "accountId": int(aid),
                        "name": label
                    }, token)
                    print(f"     ✅ Renamed to '{label}'")
                except Exception as e:
                    print(f"     ❌ Rename failed: {e}")
            else:
                print(f"     ⏭️  Live account — skipping rename")
        else:
            print(f"     {aid:15s} '{name}' {acc_type} live={is_live}")

if __name__ == "__main__":
    main()
