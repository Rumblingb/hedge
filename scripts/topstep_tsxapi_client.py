#!/usr/bin/env python3
"""Shared tsxapipy APIClient factory that reuses topstep_auth_cache.

Never call tsxapipy.authenticate() from hedge cron/scripts — that opens a
fresh /api/Auth/loginKey session and trips Topstep multiple-session warnings.

Order path stays quarantined under .quarantine/tsxapi-order-path-20260707/.
This module is READ-ONLY market-data only.
"""
from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUTH_CACHE_PATH = Path.home() / ".hermes" / "scripts" / "topstep_auth_cache.py"

os.environ.setdefault("BILL_ENABLE_FUTURES_DEMO_EXECUTION", "false")
os.environ.setdefault("RH_TOPSTEP_READ_ONLY", "true")
os.environ.setdefault("RH_LIVE_EXECUTION_ENABLED", "false")
os.environ.setdefault("TRADING_ENVIRONMENT", "LIVE")


def _load_auth_cache() -> Any:
    spec = importlib.util.spec_from_file_location("topstep_auth_cache", AUTH_CACHE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load topstep_auth_cache from {AUTH_CACHE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_shared_token(*, force_refresh: bool = False) -> str:
    """Return the machine-wide Topstep token (one loginKey per ~20h)."""
    cache = _load_auth_cache()
    if force_refresh and hasattr(cache, "get_token"):
        try:
            return str(cache.get_token(force_refresh=True))
        except TypeError:
            # Older cache API without force_refresh kwarg
            return str(cache.get_token())
    return str(cache.get_token())


def get_api_client(*, force_refresh: bool = False) -> Any:
    """Build a tsxapipy APIClient that never calls loginKey itself.

    Re-auth is delegated to topstep_auth_cache so cron jobs share one session.
    """
    from tsxapipy import APIClient

    token = get_shared_token(force_refresh=force_refresh)
    acquired = datetime.now(timezone.utc)
    # Long assumed lifetime so short-lived clients do not reauth mid-request;
    # if they do, the patched reauth path still uses the shared cache.
    client = APIClient(
        initial_token=token,
        token_acquired_at=acquired,
        default_token_lifetime_hours=48.0,
    )

    def _reauth_via_shared_cache() -> None:
        new_token = get_shared_token(force_refresh=True)
        client._token = new_token
        client._token_acquired_at = datetime.now(timezone.utc)
        client._update_headers()

    client._perform_re_authentication_internal = _reauth_via_shared_cache  # type: ignore[method-assign]
    return client


def smoke_contract_search(query: str = "MNQ") -> dict[str, Any]:
    """Read-only contract search smoke (uses shared cache)."""
    client = get_api_client()
    contracts = client.search_contracts(query)
    first = contracts[0] if contracts else None
    return {
        "ok": True,
        "query": query,
        "count": len(contracts),
        "first_symbol_id": getattr(first, "symbol_id", None) if first else None,
        "first_id": str(getattr(first, "id", "")) if first else None,
        "provider": "tsxapipy+topstep_auth_cache",
        "writes_orders": False,
        "touches_broker": True,
        "read_only": True,
    }


if __name__ == "__main__":
    import json
    import sys

    try:
        print(json.dumps(smoke_contract_search(), indent=2, default=str))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        sys.exit(1)
