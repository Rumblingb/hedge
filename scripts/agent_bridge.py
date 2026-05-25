#!/usr/bin/env python3
"""
Agent Communication Bridge — Shared State Protocol
===================================================
Universal input/output bridge for ALL agents in the system.

Every agent (Hermes, OpenClaw, Codex, TradingAgents, Gengar, Bill TS, Python arsenal)
communicates through this shared state layer.

Input Bridge (any agent → loop):
  - Drop research content into ~/.rumbling-hedge/agent-inbox/
  - Research pipeline picks it up, extracts, tests, dispatches
  - Format: standardized JSON with source attribution

Output Bridge (loop → any agent):
  - Extracted signals at ~/.rumbling-hedge/research/extracted/
  - Dispatched strategies at ~/.rumbling-hedge/dispatcher/targets/
  - Test results at ~/.rumbling-hedge/multi-d-testing/
  - Source quality at ~/.rumbling-hedge/learning/

Agent-to-Agent (peer-to-peer):
  - Messages via ~/.rumbling-hedge/agent-messages/
  - Any agent can send, any can read
  - Threaded conversations, status tracking

Usage:
  python3 scripts/agent_bridge.py --submit research <file>    # Submit research content
  python3 scripts/agent_bridge.py --submit signal <file>      # Submit a signal directly
  python3 scripts/agent_bridge.py --read dispatches           # Read pending dispatches
  python3 scripts/agent_bridge.py --read tests                # Read test results
  python3 scripts/agent_bridge.py --read learning             # Read source quality
  python3 scripts/agent_bridge.py --wire-crons                # Wire existing crons into loop
  python3 scripts/agent_bridge.py --send <agent> <subject>    # Send a message to another agent
  python3 scripts/agent_bridge.py --inbox                     # Read messages for you
  python3 scripts/agent_bridge.py --status                    # Bridge status
"""

import json
import os
import sys
import glob
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(os.path.expanduser("~/.rumbling-hedge"))
AGENT_NAME = os.environ.get("HERMES_AGENT", "hermes")

# Directory structure
DIRS = {
    "inbox": ROOT / "agent-inbox",          # Any agent drops research here
    "outbox": ROOT / "agent-outbox",        # Loop drops outputs here
    "messages": ROOT / "agent-messages",    # Agent-to-agent communication
    "signals": ROOT / "research" / "extracted",
    "dispatches": ROOT / "dispatcher" / "targets",
    "tests": ROOT / "multi-d-testing",
    "learning": ROOT / "learning",
}

# Which existing state files to bridge
STATE_BRIDGE = {
    "pm-edge": {
        "source": ROOT / "state" / "pm-execution-engine.json",
        "category": "prediction_market",
        "type": "prediction_market",
    },
    "signal-arbitration": {
        "source": ROOT / "state" / "arbitration.latest.json",
        "category": "signal_fusion",
        "type": "signal",
    },
    "new-arsenal": {
        "source": ROOT / "state" / "new-arsenal-combined.json",
        "category": "signal_composite",
        "type": "signal",
    },
    "insider": {
        "source": ROOT / "state" / "insider-signal.latest.json",
        "category": "fundamental",
        "type": "signal",
    },
    "cot": {
        "source": ROOT / "state" / "cot-signal.latest.json",
        "category": "fundamental",
        "type": "signal",
    },
    "ichimoku": {
        "source": ROOT / "state" / "ichimoku-signal.latest.json",
        "category": "technical",
        "type": "signal",
    },
    "opening-candle": {
        "source": ROOT / "state" / "opening-candle-signal.latest.json",
        "category": "regime",
        "type": "signal",
    },
    "manipulation": {
        "source": ROOT / "state" / "manipulation-4h-signal.latest.json",
        "category": "pattern",
        "type": "signal",
    },
    "kalman-pairs": {
        "source": ROOT / "state" / "kalman-pairs-signal.latest.json",
        "category": "stat_arb",
        "type": "signal",
    },
    "vwap": {
        "source": ROOT / "state" / "vwap-signal.latest.json",
        "category": "mean_reversion",
        "type": "signal",
    },
    "heiken-ashi": {
        "source": ROOT / "state" / "heiken-ashi-signal.latest.json",
        "category": "trend",
        "type": "signal",
    },
    "dom-proxy": {
        "source": ROOT / "state" / "dom-proxy-signal.latest.json",
        "category": "order_flow",
        "type": "signal",
    },
}


def ensure_dirs():
    for d in DIRS.values():
        d.mkdir(parents=True, exist_ok=True)
    (ROOT / "agent-inbox" / "processed").mkdir(parents=True, exist_ok=True)


# ─── INPUT BRIDGE ───────────────────────────────────────────────────

def write_inbox(content: dict, source_agent: str = AGENT_NAME) -> str:
    """
    Any agent calls this to submit research content into the loop.
    Content flows: inbox → research pipeline → extraction → testing → dispatch

    Required fields in content:
      - title: str
      - content_text: str (the actual research content)
      - source_type: youtube|arxiv|twitter|paper|signal|custom
      - source_name: str
      - url: str (optional but recommended)
      - tags: list[str] (optional)

    Returns: inbox file path
    """
    ensure_dirs()
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": source_agent,
        "title": content.get("title", "Untitled"),
        "content_text": content.get("content_text", ""),
        "source_type": content.get("source_type", "custom"),
        "source_name": content.get("source_name", source_agent),
        "url": content.get("url", ""),
        "tags": content.get("tags", []),
        "entry_type": content.get("entry_type", "research"),
        "processed": False,
    }

    safe_name = content.get("source_name", source_agent).replace(" ", "_").lower()[:20]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:20]
    filename = f"{safe_name}_{timestamp}.json"
    path = DIRS["inbox"] / filename
    with open(path, "w") as f:
        json.dump(entry, f, indent=2)

    return str(path)


def submit_signal(signal: dict, source_agent: str = AGENT_NAME) -> str:
    """
    Submit a raw signal directly into the extraction pipeline.
    Skips the research collection step.

    Required signal fields:
      - signal_name: str
      - instrument_type: futures|crypto|prediction_market|stocks
      - entry_condition: str
      - exit_condition: str (optional)
      - direction_rule: LONG|SHORT|BOTH
      - market_logic: str (WHY this edge exists)
      - timeframe: str (optional hint)

    Returns: extraction file path
    """
    ensure_dirs()
    extraction = {
        "signal": {
            "signal_name": signal.get("signal_name", "unnamed"),
            "instrument_type": signal.get("instrument_type", "futures"),
            "entry_condition": signal.get("entry_condition", ""),
            "exit_condition": signal.get("exit_condition", ""),
            "direction_rule": signal.get("direction_rule", "BOTH"),
            "market_logic": signal.get("market_logic", ""),
            "timeframe": signal.get("timeframe", "any"),
            "confidence_score": signal.get("confidence", 0.5),
        },
        "source_type": signal.get("source_type", f"agent:{source_agent}"),
        "source_url": signal.get("source_url", f"agent://{source_agent}"),
        "source_name": signal.get("source_name", source_agent),
        "submitted_by": source_agent,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "classification": "gold",
    }

    # Write to extraction dir directly
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_name = signal.get("signal_name", "unnamed").replace(" ", "_").lower()[:30]
    path = DIRS["signals"] / f"agent-signal-{date}-{safe_name}.json"
    with open(path, "w") as f:
        json.dump(extraction, f, indent=2)

    return str(path)


# ─── OUTPUT BRIDGE ──────────────────────────────────────────────────

def read_dispatches(engine: str | None = None) -> list[dict]:
    """Read pending strategy dispatches. Optionally filter by engine."""
    target_dir = DIRS["dispatches"]
    if not target_dir.exists():
        return []

    dispatches = []
    pattern = "*-pending.json"
    for f in target_dir.glob(pattern):
        try:
            with open(f) as pf:
                data = json.load(pf)
        except Exception:
            continue

        if isinstance(data, list):
            dispatches.extend(data)
        else:
            dispatches.append(data)

    # Filter by engine if specified
    if engine:
        dispatches = [d for d in dispatches if d.get("target_engine", d.get("engine", "")).lower() == engine.lower()]

    return dispatches


def read_test_results(plan_id: str | None = None) -> list[dict]:
    """Read multi-D test results."""
    test_dir = DIRS["tests"]
    if not test_dir.exists():
        return []

    if plan_id:
        files = list(test_dir.glob(f"plan-{plan_id}.json"))
    else:
        files = list(test_dir.glob("plan-*.json"))

    results = []
    for f in files:
        try:
            with open(f) as pf:
                data = json.load(pf)
            results.append(data)
        except Exception:
            continue

    return results


def read_learning() -> dict:
    """Read source quality and learning state."""
    sq_file = DIRS["learning"] / "source-quality.json"
    summary_file = DIRS["learning"] / "learning-summary.latest.json"

    result = {"sources": [], "summary": {}}

    if sq_file.exists():
        with open(sq_file) as f:
            result["sources"] = json.load(f)

    if summary_file.exists():
        with open(summary_file) as f:
            result["summary"] = json.load(f)

    return result


# ─── AGENT-TO-AGENT COMMUNICATION ──────────────────────────────────

def send_message(to_agent: str, subject: str, body: str,
                 reply_to: str | None = None,
                 from_agent: str = AGENT_NAME) -> str:
    """
    Send a message to another agent.
    Messages are JSON files in ~/.rumbling-hedge/agent-messages/
    Any agent can read messages addressed to them.

    Args:
        to_agent: name of target agent (or "ALL" for broadcast)
        subject: message subject
        body: message body
        reply_to: message ID this is replying to (optional)
        from_agent: sender (default: HERMES_AGENT env or "hermes")

    Returns: message ID
    """
    ensure_dirs()
    message = {
        "id": datetime.now(timezone.utc).strftime("msg_%Y%m%d_%H%M%S_%f")[:22],
        "from": from_agent,
        "to": to_agent,
        "subject": subject,
        "body": body,
        "reply_to": reply_to,
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "unread",
        "thread_id": reply_to or "new",
    }

    path = DIRS["messages"] / f"{message['id']}.json"
    with open(path, "w") as f:
        json.dump(message, f, indent=2)

    print(f"  ✉️  Message sent: {from_agent} → {to_agent}: {subject}")
    return message["id"]


def read_messages(for_agent: str | None = None, status: str | None = None) -> list[dict]:
    """Read messages for a specific agent."""
    ensure_dirs()
    if for_agent is None:
        for_agent = AGENT_NAME

    messages = []
    for f in sorted(DIRS["messages"].glob("msg_*.json")):
        try:
            with open(f) as pf:
                msg = json.load(pf)
        except Exception:
            continue

        # Filter by recipient
        if msg.get("to") in (for_agent, "ALL"):
            if status is None or msg.get("status") == status:
                messages.append(msg)

    return sorted(messages, key=lambda m: m.get("ts", ""), reverse=True)


def mark_read(message_id: str):
    """Mark a message as read."""
    path = DIRS["messages"] / f"{message_id}.json"
    if path.exists():
        with open(path) as f:
            msg = json.load(f)
        msg["status"] = "read"
        msg["read_at"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w") as f:
            json.dump(msg, f, indent=2)
        return True
    return False


def reply_to(message_id: str, body: str, from_agent: str = AGENT_NAME) -> str | None:
    """Reply to an existing message."""
    path = DIRS["messages"] / f"{message_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        original = json.load(f)
    return send_message(
        to_agent=original["from"],
        subject=f"Re: {original['subject']}",
        body=body,
        reply_to=message_id,
        from_agent=from_agent,
    )


# ─── WIRE EXISTING CRONS ────────────────────────────────────────────

def wire_existing_crons() -> int:
    """
    Bridge existing cron state files into the loop.
    Reads ~/.rumbling-hedge/state/*.latest.json files and converts them
    into standardized research entries in the agent-inbox.
    """
    ensure_dirs()
    bridged = 0

    for name, config in STATE_BRIDGE.items():
        src = config["source"]
        if not src.exists():
            continue

        try:
            with open(src) as f:
                data = json.load(f)
        except Exception:
            continue

        if not data:
            continue

        # Create a research entry from the state data
        content = {
            "title": f"Signal: {name} ({config['category']})",
            "content_text": json.dumps(data, indent=2),
            "source_type": config["type"],
            "source_name": f"cron:{name}",
            "url": f"file://{src}",
            "tags": [config["category"], config["type"], "auto-bridged"],
            "entry_type": "signal",
        }

        path = write_inbox(content, source_agent=f"cron:{name}")
        bridged += 1

    return bridged


# ─── STATUS ─────────────────────────────────────────────────────────

def cmd_status():
    """Show bridge status."""
    ensure_dirs()

    # Inbox stats
    inbox_files = list(DIRS["inbox"].glob("*.json"))
    unprocessed = [f for f in inbox_files if not f.name.startswith("processed")]
    
    # Message stats
    all_msgs = list(DIRS["messages"].glob("msg_*.json"))
    unread = []
    for f in all_msgs:
        try:
            with open(f) as pf:
                m = json.load(pf)
            if m.get("status") == "unread" and m.get("to") in (AGENT_NAME, "ALL"):
                unread.append(m)
        except Exception:
            continue

    # Dispatch stats
    dispatches = read_dispatches()
    
    # Source stats
    learning = read_learning()
    sources = learning.get("sources", [])

    # Existing cron state bridge status
    bridged = 0
    not_bridged = 0
    for name, config in STATE_BRIDGE.items():
        if config["source"].exists():
            bridged += 1
        else:
            not_bridged += 1

    print(f"\n{'='*60}")
    print(f"  AGENT COMMUNICATION BRIDGE — STATUS")
    print(f"{'='*60}")
    print(f"  Agent: {AGENT_NAME}")
    print(f"  Inbox: {len(inbox_files)} items ({len(unprocessed)} unprocessed)")
    print(f"  Messages: {len(all_msgs)} total ({len(unread)} unread for {AGENT_NAME})")
    print(f"  Dispatches: {len(dispatches)} pending")
    print(f"  Sources tracked: {len(sources)}")
    print(f"  State bridges: {bridged}/{bridged + not_bridged} active")
    print()

    if unread:
        print(f"  📬 Unread messages for {AGENT_NAME}:")
        for m in unread[:5]:
            print(f"    [{m.get('id','?')[:16]}] {m.get('from','?')}: {m.get('subject','?')}")
    
    print(f"\n  Directories:")
    for name, path in DIRS.items():
        exists = path.exists()
        count = len(list(path.glob("*.json"))) if exists else 0
        print(f"    {name:<12} {'✅' if exists else '❌'}  {count} files")

    return {
        "agent": AGENT_NAME,
        "inbox": len(inbox_files),
        "unread_messages": len(unread),
        "sources": len(sources),
        "bridges": bridged,
    }


# ─── CLI ────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Agent Communication Bridge — Universal I/O for all trading agents"
    )
    parser.add_argument("--status", action="store_true", help="Show bridge status")
    
    # Input bridge
    parser.add_argument("--submit", nargs=2, metavar=("TYPE", "FILE"),
                        help="Submit content: research|signal <filepath>")
    
    # Output bridge
    parser.add_argument("--read", choices=["dispatches", "tests", "learning"],
                        help="Read loop outputs")
    
    # Agent communication
    parser.add_argument("--send", nargs=3, metavar=("TO", "SUBJECT", "BODY"),
                        help="Send message to another agent")
    parser.add_argument("--inbox", nargs="?", const="all", metavar="AGENT",
                        help="Read messages (optional: filter by agent name)")
    parser.add_argument("--mark-read", metavar="MSG_ID", help="Mark message as read")
    parser.add_argument("--reply", nargs=2, metavar=("MSG_ID", "BODY"),
                        help="Reply to a message")
    
    # Bridge ops
    parser.add_argument("--wire-crons", action="store_true",
                        help="Bridge existing cron state files into the loop")

    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.submit:
        typ, filepath = args.submit
        try:
            with open(filepath) as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = {"content_text": open(filepath).read(), "title": filepath}
        
        if typ == "research":
            path = write_inbox(data)
            print(f"  📥 Research submitted: {path}")
        elif typ == "signal":
            path = submit_signal(data)
            print(f"  📥 Signal submitted: {path}")
        else:
            print(f"  ❌ Unknown type: {typ} (use 'research' or 'signal')")
    elif args.read == "dispatches":
        dispatches = read_dispatches()
        for d in dispatches:
            print(f"  📤 {d.get('signal_name','?'):30s} → {d.get('target_engine', d.get('engine','?'))}")
        print(f"  ({len(dispatches)} pending)")
    elif args.read == "tests":
        plans = read_test_results()
        for p in plans:
            fb = p.get("feedback", {})
            print(f"  {'✅' if fb.get('edge_found') else '⏳'} {p.get('signal_name','?'):30s} "
                  f"R={fb.get('total_r',0):.1f}")
    elif args.read == "learning":
        data = read_learning()
        for s in sorted(data.get("sources", []), key=lambda x: x.get("quality", 0), reverse=True):
            print(f"  {s.get('name','?'):30s} q={s.get('quality',0):.3f} "
                  f"c={s.get('confidence',0):.0f} [{s.get('priority','medium')}]")
    elif args.send:
        to_agent, subject, body = args.send
        msg_id = send_message(to_agent, subject, body)
        print(f"  ✅ Message sent: {msg_id}")
    elif args.inbox is not None:
        agent = args.inbox if args.inbox != "all" else None
        msgs = read_messages(for_agent=agent)
        for m in msgs[:10]:
            status = "📬" if m.get("status") == "unread" else "📖"
            print(f"  {status} [{m.get('id','?')[:16]}] {m.get('from','?'):15s} → "
                  f"{m.get('to','?'):15s}: {m.get('subject','?')}")
        print(f"  ({len(msgs)} messages)")
    elif args.mark_read:
        if mark_read(args.mark_read):
            print(f"  ✅ Marked {args.mark_read} as read")
        else:
            print(f"  ❌ Message not found: {args.mark_read}")
    elif args.reply:
        msg_id, body = args.reply
        new_id = reply_to(msg_id, body)
        if new_id:
            print(f"  ✅ Reply sent: {new_id}")
        else:
            print(f"  ❌ Original message not found: {msg_id}")
    elif args.wire_crons:
        count = wire_existing_crons()
        print(f"  🔗 Bridged {count} cron state files into the loop")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
