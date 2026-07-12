#!/usr/bin/env python3
"""common.py — Shared utilities for the Bill/Hedge trading system."""
import json
from pathlib import Path
from datetime import datetime, timezone


def atomic_write(path: Path, data: str) -> None:
    """Atomically write data to a file via temp + rename.
    
    Writes to a .tmp sibling first, then renames to the target path,
    ensuring the write is atomic on the same filesystem.
    Accepts both Path and str.
    """
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(data)
    tmp.rename(path)


def atomic_write_json(path: Path, obj, indent: int = 2) -> None:
    """Atomically write a JSON-serializable object to path."""
    atomic_write(path, json.dumps(obj, indent=indent, default=str))


__all__ = ["atomic_write", "atomic_write_json"]
