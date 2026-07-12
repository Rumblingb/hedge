#!/usr/bin/env python3
"""Discover TopstepX API endpoints for account management."""
import json, os, sys
from pathlib import Path
from urllib.request import Request, urlopen

ENV_PATH = Path.home() / "Library/Application Support/AgentPay/bill/bill.env"

def read_env(k):
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "): line = line[7:]
        if "=" in line:
            key, val = line.split("=", 1)
            if key.strip() == k:
                return val.strip().strip("'\"").strip()
    return None

api_key = read_env("RH_TOPSTEP_API_KEY")
username = read_env("RH_TOPSTEP_USERNAME")
API = "https://api.topstepx.com"

req = Request(f"{API}/api/Auth/loginKey",
    data=json.dumps({"apiKey": api_key, "userName": username, "applicationId": 0, "applicationVersion": "1.0.0"}).encode(),
    headers={"Content-Type": "application/json"})
token = json.loads(urlopen(req).read())["token"]
print("Logged in\n")

# Try common account endpoints
endpoints = [
    "/api/Account/GetAll", "/api/Account/getAll", "/api/Account/list",
    "/api/account", "/api/accounts", "/api/user/accounts",
    "/api/Account/GetAccounts", "/api/Account/GetByUser"
]
for ep in endpoints:
    try:
        req2 = Request(f"{API}{ep}", headers={"Authorization": f"Bearer {token}"})
        resp = urlopen(req2, timeout=10)
        data = json.loads(resp.read())
        print(f"[{resp.status}] {ep} -> {type(data).__name__}", end="")
        if isinstance(data, list):
            print(f" ({len(data)} items)")
            for a in data[:5]:
                ids = [a.get(k) for k in ["accountId","id","accountID"] if a.get(k)]
                print(f"   ID={ids[0] if ids else '?'} name={a.get('name','?')}")
        elif isinstance(data, dict):
            print(f" keys={list(data.keys())[:8]}")
            # Check for nested account lists
            for k in ["accounts","data","result","items"]:
                if k in data and isinstance(data[k], list):
                    print(f"   -> data[{k}] has {len(data[k])} items")
                    for a in data[k][:3]:
                        print(f"      ID={a.get('accountId','?')} name={a.get('name','?')}")
        else:
            print(f" value={str(data)[:100]}")
    except Exception as e:
        print(f"[ERR] {ep} -> {e}")
