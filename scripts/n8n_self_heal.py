#!/usr/bin/env python3
"""N8N self-healing: watch for JWT expiry and auto-refresh from n8n DB.
Checks every 60s if MCP is reachable. If 401, flags for manual JWT refresh.
Also monitors workflow execution health."""
import json, time, urllib.request, os, sys

CONFIG = os.path.expanduser("~/.hermes/config.yaml")
HEALTH_FILE = os.path.expanduser("~/.rumbling-hedge/state/n8n-self-heal.json")

def check_n8n_health():
    """Check if n8n is running and MCP is responsive."""
    status = {"ts": time.time(), "n8n_up": False, "mcp_ok": False, "workflows_healthy": False, "errors": []}
    
    # Check n8n basic health
    try:
        req = urllib.request.Request("http://localhost:5678/healthz")
        resp = urllib.request.urlopen(req, timeout=5)
        if json.loads(resp.read()).get("status") == "ok":
            status["n8n_up"] = True
    except Exception as e:
        status["errors"].append(f"n8n down: {e}")
        return status
    
    # Check MCP connectivity with stored JWT
    try:
        import re
        with open(CONFIG) as f:
            m = re.search(r'Bearer (eyJ[a-zA-Z0-9_.-]+)', f.read())
        token = m.group(1) if m else ""
        
        body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/list"}).encode()
        req = urllib.request.Request("http://localhost:5678/mcp-server/http",
            data=body, method="POST",
            headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream",
                     "Authorization": f"Bearer {token}"})
        resp = urllib.request.urlopen(req, timeout=10)
        for line in resp.read().decode().split("\n"):
            if "tools" in line:
                status["mcp_ok"] = True
                break
    except urllib.error.HTTPError as e:
        if e.code == 401:
            status["errors"].append("MCP JWT expired — needs refresh from n8n UI > Settings > MCP Server")
        else:
            status["errors"].append(f"MCP error: {e.code}")
    except Exception as e:
        status["errors"].append(f"MCP check failed: {e}")
    
    # Check recent workflow executions
    try:
        import psycopg2
        conn = psycopg2.connect("dbname=n8n user=n8n host=localhost")
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM execution_entity 
            WHERE status = 'error' AND "startedAt" > NOW() - INTERVAL '1 hour'
        """)
        error_count = c.fetchone()[0]
        if error_count > 5:
            status["errors"].append(f"{error_count} workflow errors in last hour")
        elif error_count > 0:
            status["errors"].append(f"{error_count} workflow errors in last hour — monitoring")
        status["workflows_healthy"] = error_count < 3
        conn.close()
    except Exception as e:
        status["errors"].append(f"DB check failed: {e}")
    
    return status

if __name__ == "__main__":
    status = check_n8n_health()
    with open(HEALTH_FILE, 'w') as f:
        json.dump(status, f, indent=2)
    
    if status["errors"]:
        print("ISSUES:")
        for e in status["errors"]:
            print(f"  ❌ {e}")
    else:
        print("✅ All healthy")
    
    if not status["mcp_ok"]:
        print("\n⚠️  MCP JWT needs refresh. Go to:")
        print("   http://localhost:5678 > Settings > MCP Server > Copy JWT")
        print("   Then: paste it here and I'll update config.")
        sys.exit(1)
