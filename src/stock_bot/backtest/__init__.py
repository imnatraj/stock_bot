"""Backtest package (Phase 1).

Provides a safe import surface. Full backtesting engine implemented in Phase 6.
"""
from __future__ import annotations

from typing import List, Dict, Any


def run_backtest(symbols: List[str], start_date: str, end_date: str) -> Dict[str, Any]:
    """Run a minimal backtest placeholder.

    Returns an empty report structure to keep interfaces stable.
    """
    return {"symbols": symbols, "start_date": start_date, "end_date": end_date, "report": {}}
