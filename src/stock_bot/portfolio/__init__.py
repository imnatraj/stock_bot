"""Portfolio tracking package (Phase 1).

Minimal, importable surface for portfolio operations.
"""
from __future__ import annotations

from typing import Dict


def current_snapshot() -> Dict[str, float]:
    """Return a minimal portfolio snapshot.

    This returns zeros in Phase 1 and will be extended later.
    """
    return {"portfolio_value": 0.0, "cash_available": 0.0}
