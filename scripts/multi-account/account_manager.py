#!/usr/bin/env python3
"""TopstepX Account Manager — multi-account registry and rename utility.

API discovery confirms:
  /api/Account/search (POST) -> returns accounts list with id, balance, name
  /api/Account/update (POST, presumed) -> update account name

Usage:
  python3 scripts/multi-account/account_manager.py --list
  python3 scripts/multi-account/account_manager.py --rename <id> <name>
"""

import json, os, sys
from pathlib import Path
from urllib.request import Request, urlopen

ENV_PATH = Path.home() / "Library/Application Support/AgentPay/bill/bill.env"
API_BASE = "https://api.topstepx.com"

ACCOUNTS = {
    "97442788": {"label": "LIVE TRADING",  "purpose": "live"},
    "83651531": {"label": "DEMO 100K",     "purpose": "demo"},
    "28339015": {"label": "TEST 50K A",    "purpose": "test"},
    "71363980": {"label": "TEST 50K B",    "purpose": "test"},
}

def read_env(k):
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "): line = line[7:]
        if "=" in line:
            key, val = line.split("=", 1)
            if key.strip() == k: return val.strip().strip("'\"").strip()
    return None

def login():
    # Shared machine-wide token cache — direct loginKey calls each create a
    # Topstep session and collide with the operator's manual platform login.
    sys.path.insert(0, os.path.expanduser("~/.hermes/scripts"))
    from topstep_auth_cache import get_token
    return get_token()

def api_post(path, body, token):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    req = Request(f"{API_BASE}{path}", data=json.dumps(body).encode(), headers=headers)
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def list_accounts(token):
    """List all active accounts via Account/search."""
    data = api_post("/api/Account/search", {"onlyActiveAccounts": True}, token)
    accounts = data.get("accounts", [])
    print(f"Found {len(accounts)} accounts:\n")
    for a in accounts:
        aid = str(a.get("id", ""))
        matched = False
        for suffix, info in ACCOUNTS.items():
            if aid.endswith(suffix):
                print(f"  🎯 {aid:20s} '{a.get('name','')}' bal={a.get('balance',0):,.2f} -> {info['label']} ({info['purpose']})")
                matched = True
                break
        if not matched:
            print(f"     {aid:20s} '{a.get('name','')}' bal={a.get('balance',0):,.2f}")

def rename_account(token, account_id, new_name):
    """Rename an account via Account/update."""
    try:
        result = api_post("/api/Account/update", {"accountId": int(account_id), "name": new_name}, token)
        print(f"✅ Renamed {account_id} -> '{new_name}'")
        return result
    except Exception as e:
        print(f"❌ Rename failed: {e}")
        return None

if __name__ == "__main__":
    token = login()
    print("✅ Logged in\n")
    
    if "--list" in sys.argv:
        list_accounts(token)
    elif "--rename" in sys.argv:
        idx = sys.argv.index("--rename")
        if idx + 2 < len(sys.argv):
            rename_account(token, sys.argv[idx+1], sys.argv[idx+2])
        else:
            print("Usage: --rename <account_id> <new_name>")
    else:
        list_accounts(token)
