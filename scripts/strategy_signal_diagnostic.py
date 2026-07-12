#!/usr/bin/env python3
"""Compatibility wrapper for the research-only futures strategy diagnostic."""

from __future__ import annotations

try:
    from scripts.strategy_diagnostic import build_report, main, render_text
except ImportError:
    from strategy_diagnostic import build_report, main, render_text


if __name__ == "__main__":
    raise SystemExit(main())
