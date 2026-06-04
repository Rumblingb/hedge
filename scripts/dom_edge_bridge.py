#!/usr/bin/env python3
"""
DOM Data Pipeline Bridge
Reads dom-proxy-signal.latest.json → converts to dom_micro_edges.json format
This feeds domMicroEdge.ts which boosts strategy confidence based on order flow signals.
"""

import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", str(ROOT / ".rumbling-hedge" / "state")))
PROXY_PATH = STATE_DIR / "dom-proxy-signal.latest.json"
DOM_EDGE_PATH = STATE_DIR / "dom_micro_edges.json"

def convert_to_dom_edge(proxy_data: dict, source_path: Path = PROXY_PATH) -> dict:
    """Convert OHLCV proxy format to dom_micro_edges.json format."""
    signals_list = []
    ofi_3 = 0.0
    cd_10 = 0.0
    iceberg_count = 0
    vwap_deviation_pct = 0.0
    vwap = 0.0
    microprice = 0.0
    price = 0.0

    # Map signals from proxy format
    for sig in proxy_data.get("signals", []):
        sig_type = sig.get("type", "")
        sig_desc = sig.get("desc", "")
        sig_strength = sig.get("strength", 0)

        if "bullish_divergence" in sig_type or sig_type == "bullish_divergence":
            signals_list.append("OFI LONG")
            ofi_3 = min(sig_strength, 1.0)
            cd_10 = ofi_3 * 1.2
        elif "bearish_divergence" in sig_type or sig_type == "bearish_divergence":
            signals_list.append("OFI SHORT")
            ofi_3 = -min(abs(sig_strength), 1.0)
            cd_10 = ofi_3 * 1.2
        elif "iceberg" in sig_type.lower():
            signals_list.append("ICEBERG DETECTED")
            iceberg_count += 1

    # Use CLV as price direction indicator
    clv = proxy_data.get("current_clv", 0)
    if abs(clv) > 0.3 and not any("OFI" in s for s in signals_list):
        if clv > 0:
            signals_list.append("OFI LONG")
            ofi_3 = clv
            cd_10 = clv * 0.8
        else:
            signals_list.append("OFI SHORT")
            ofi_3 = clv
            cd_10 = clv * 0.8

    # Price z-score > 2 → VWAP deviation
    price_z = proxy_data.get("current_price_z", 0)
    if abs(price_z) > 2.0:
        direction = "LONG" if price_z < -2.0 else "SHORT"
        signals_list.append(f"VWAP_DEVIATION_{direction}")
        vwap_deviation_pct = price_z / 10.0  # normalize

    # VWAP stop-hunt if delta z-score diverges from price z-score
    delta_z = proxy_data.get("current_delta_z", 0)
    if abs(price_z - delta_z) > 1.5:
        direction = "LONG" if delta_z > price_z else "SHORT"
        signals_list.append(f"VWAP_STOP_HUNT_{direction}")

    if not signals_list:
        signals_list.append("NO_EDGE")

    return {
        "timestamp": proxy_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "signals": signals_list,
        "ofi_3": round(ofi_3, 4),
        "cd_10": round(cd_10, 4),
        "iceberg_count": iceberg_count,
        "vwap_deviation_pct": round(vwap_deviation_pct, 4),
        "vwap": vwap,
        "microprice": microprice,
        "microprice_spread": 0.0,
        "price": price,
        "source": str(source_path),
        "source_method": proxy_data.get("method", "OHLCV_DOM_proxy"),
        "source_evidence_level": proxy_data.get("evidence_level", "proxy_shadow_only"),
        "source_data_provider": proxy_data.get("source_data_provider", "unknown"),
        "source_data_stale": bool(proxy_data.get("source_data_stale", True)),
        "researchOnly": True,
        "proxyOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "execution_role": "diagnostic_only",
        "operator_read": (
            "Research-only OHLCV proxy bridge for domMicroEdge.ts. This is not true DOM, "
            "bid/ask depth, tape, or broker execution evidence."
        ),
    }


def write_dom_edge_file(proxy_data: dict, output_path: Path = DOM_EDGE_PATH, source_path: Path = PROXY_PATH) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dom_edge = convert_to_dom_edge(proxy_data, source_path=source_path)
    with open(output_path, "w") as f:
        json.dump(dom_edge, f, indent=2)
    return dom_edge


def main():
    if not PROXY_PATH.exists():
        # Write a neutral/default edge file
        default = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signals": ["NO_EDGE"],
            "ofi_3": 0.0,
            "cd_10": 0.0,
            "iceberg_count": 0,
            "vwap_deviation_pct": 0.0,
            "vwap": 0.0,
            "microprice": 0.0,
            "microprice_spread": 0.0,
            "price": 0.0,
            "source": str(PROXY_PATH),
            "source_method": "missing_proxy",
            "source_evidence_level": "proxy_shadow_only",
            "source_data_stale": True,
            "researchOnly": True,
            "proxyOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "tradable_signal": False,
            "promoted_for_execution": False,
            "readyForExecution": False,
            "execution_role": "diagnostic_only",
            "operator_read": "Neutral research-only DOM bridge file; source proxy is missing.",
        }
        DOM_EDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DOM_EDGE_PATH, "w") as f:
            json.dump(default, f, indent=2)
        print(f"No proxy data. Wrote neutral edge file to {DOM_EDGE_PATH}")
        return

    with open(PROXY_PATH) as f:
        proxy_data = json.load(f)

    dom_edge = write_dom_edge_file(proxy_data)

    print(f"✅ dom_edge written to {DOM_EDGE_PATH}")
    print(f"   Signals: {dom_edge['signals']}")
    print(f"   OFI(3): {dom_edge['ofi_3']:.4f}, CD(10): {dom_edge['cd_10']:.4f}")
    print(f"   Icebergs: {dom_edge['iceberg_count']}")


if __name__ == "__main__":
    main()
