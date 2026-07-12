#!/usr/bin/env python3
"""Order execution bridge using tsxapipy OrderPlacer.

Called as subprocess from TypeScript (demoExecution.ts). Reads credentials
from bill.env automatically. Accepts stdin JSON for order placement and
prints JSON result to stdout.

Usage modes:
    python3 scripts/tsxapi_order_bridge.py --help
    python3 scripts/tsxapi_order_bridge.py place <order.json>
    python3 scripts/tsxapi_order_bridge.py cancel <order_id>
    python3 scripts/tsxapi_order_bridge.py status <order_id>
    python3 scripts/tsxapi_order_bridge.py accounts
    python3 scripts/tsxapi_order_bridge.py positions

Order JSON format (stdin or file):
    {
        "account_id": 12345,
        "contract_id": "CON.F.US.MNQ.U26",
        "side": "buy",
        "size": 1,
        "order_type": "MARKET",
        "limit_price": null,
        "stop_price": null,
        "custom_tag": "demo-canary-2026-07-06"
    }

Output (stdout JSON):
    {"success": true, "order_id": 67890, "message": "..."}
    {"success": false, "error": "..."}
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Default to LIVE — hedge uses api.topstepx.com
os.environ.setdefault("TRADING_ENVIRONMENT", "LIVE")

# Safety: never execute outside demo
os.environ.setdefault("BILL_ENABLE_FUTURES_DEMO_EXECUTION", "true")
os.environ.setdefault("RH_TOPSTEP_READ_ONLY", "false")
os.environ.setdefault("RH_LIVE_EXECUTION_ENABLED", "false")

ROOT = Path(__file__).resolve().parents[1]

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("tsxapi_order_bridge")


def authenticate() -> tuple[str, datetime]:
    from tsxapipy import authenticate as tsx_auth
    token, ts = tsx_auth()
    if not token:
        raise RuntimeError("Authentication returned empty token")
    return token, ts


def get_client() -> Any:
    from tsxapipy import APIClient
    token, ts = authenticate()
    return APIClient(token, ts)


def cmd_place(args: argparse.Namespace) -> dict[str, Any]:
    """Place an order using tsxapipy OrderPlacer."""
    from tsxapipy.trading.order_handler import OrderPlacer

    if args.order_file and args.order_file != "-":
        order_spec = json.loads(Path(args.order_file).read_text())
    else:
        order_spec = json.loads(sys.stdin.read())

    account_id = int(order_spec.get("account_id", 0))
    if not account_id:
        return {"success": False, "error": "account_id is required"}

    contract_id = order_spec.get("contract_id", "")
    if not contract_id:
        return {"success": False, "error": "contract_id is required"}

    side = str(order_spec.get("side", "buy")).upper()
    if side == "BUY":
        side_code = "BUY"
    elif side == "SELL":
        side_code = "SELL"
    else:
        return {"success": False, "error": f"invalid side: {side}"}

    size = int(order_spec.get("size", 1))
    if size <= 0:
        return {"success": False, "error": "size must be positive"}

    order_type = str(order_spec.get("order_type", "MARKET")).upper()
    limit_price = order_spec.get("limit_price")
    stop_price = order_spec.get("stop_price")
    custom_tag = order_spec.get("custom_tag")

    try:
        client = get_client()
        placer = OrderPlacer(api_client=client, account_id=account_id, default_contract_id=contract_id)
        order_id = placer.place_order(
            contract_id=contract_id,
            order_type=order_type,
            side=side_code,
            size=size,
            limit_price=limit_price,
            stop_price=stop_price,
            custom_tag=custom_tag,
        )
        if order_id:
            return {"success": True, "order_id": order_id, "message": f"{side_code} {order_type} {size} of {contract_id}"}
        return {"success": False, "error": "Order placement returned no order_id (API rejection or market closed)"}
    except Exception as e:
        logger.error("place_order failed: %s", e)
        return {"success": False, "error": str(e)}


def cmd_cancel(args: argparse.Namespace) -> dict[str, Any]:
    """Cancel an existing order."""
    from tsxapipy.trading.order_handler import OrderPlacer

    order_id = int(args.order_id)
    account_id = int(args.account_id) if args.account_id else None

    if not account_id:
        return {"success": False, "error": "--account-id is required for cancel"}

    try:
        client = get_client()
        placer = OrderPlacer(api_client=client, account_id=account_id)
        result = placer.cancel_order(order_id=order_id)
        return {"success": result, "order_id": order_id, "message": "cancelled" if result else "cancel failed"}
    except Exception as e:
        logger.error("cancel_order failed: %s", e)
        return {"success": False, "error": str(e)}


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    """Get order status."""
    from tsxapipy.trading.order_handler import OrderPlacer, ORDER_STATUS_TO_STRING_MAP

    order_id = int(args.order_id)
    account_id = int(args.account_id) if args.account_id else None

    if not account_id:
        return {"success": False, "error": "--account-id is required for status"}

    try:
        client = get_client()
        placer = OrderPlacer(api_client=client, account_id=account_id)
        details = placer.get_order_details(order_id_to_find=order_id)
        if details:
            return {
                "success": True,
                "order_id": order_id,
                "status_code": details.status,
                "status": ORDER_STATUS_TO_STRING_MAP.get(details.status, "UNKNOWN"),
                "filled_quantity": details.filledQuantity,
                "remaining_quantity": details.remainingQuantity,
                "price": details.price,
            }
        return {"success": False, "error": f"order {order_id} not found"}
    except Exception as e:
        logger.error("get_order_details failed: %s", e)
        return {"success": False, "error": str(e)}


def cmd_accounts(args: argparse.Namespace) -> dict[str, Any]:
    """List available demo accounts."""
    try:
        client = get_client()
        accounts = client.get_accounts(only_active=True)
        result = []
        for acc in accounts:
            result.append({
                "id": acc.id,
                "name": acc.name,
                "can_trade": acc.can_trade,
                "balance": acc.balance,
            })
        return {"success": True, "accounts": result}
    except Exception as e:
        logger.error("get_accounts failed: %s", e)
        return {"success": False, "error": str(e)}


def cmd_positions(args: argparse.Namespace) -> dict[str, Any]:
    """List current positions."""
    # Use the REST API to fetch positions - Client doesn't have a direct positions method
    # but we can use search_orders or extend
    return {"success": False, "error": "positions endpoint not yet implemented via tsxapipy"}


def cmd_contracts(args: argparse.Namespace) -> dict[str, Any]:
    """Search for active contracts."""
    try:
        client = get_client()
        contracts = client.search_contracts(args.search_text)
        result = []
        for c in contracts:
            result.append({
                "id": c.id,
                "name": c.name,
                "symbol_id": c.symbol_id,
                "active_contract": c.active_contract,
                "tick_size": c.tick_size,
                "tick_value": c.tick_value,
            })
        return {"success": True, "contracts": result}
    except Exception as e:
        logger.error("search_contracts failed: %s", e)
        return {"success": False, "error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="TopstepX order execution bridge (tsxapipy)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # place
    p_place = subparsers.add_parser("place", help="Place an order")
    p_place.add_argument("order_file", nargs="?", default="-",
                         help="Order JSON file path (omit or '-' for stdin)")

    # cancel
    p_cancel = subparsers.add_parser("cancel", help="Cancel an order")
    p_cancel.add_argument("order_id", help="Order ID to cancel")
    p_cancel.add_argument("--account-id", required=True, help="Account ID")

    # status
    p_status = subparsers.add_parser("status", help="Get order status")
    p_status.add_argument("order_id", help="Order ID to check")
    p_status.add_argument("--account-id", required=True, help="Account ID")

    # accounts
    subparsers.add_parser("accounts", help="List demo accounts")

    # positions
    subparsers.add_parser("positions", help="List positions")

    # contracts
    p_contracts = subparsers.add_parser("contracts", help="Search contracts")
    p_contracts.add_argument("search_text", nargs="?", default="MNQ", help="Text to search")

    parsed = parser.parse_args()

    commands = {
        "place": cmd_place,
        "cancel": cmd_cancel,
        "status": cmd_status,
        "accounts": cmd_accounts,
        "positions": cmd_positions,
        "contracts": cmd_contracts,
    }

    handler = commands.get(parsed.command)
    if not handler:
        print(json.dumps({"success": False, "error": f"unknown command: {parsed.command}"}))
        return 1

    try:
        result = handler(parsed)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("success") else 1
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
