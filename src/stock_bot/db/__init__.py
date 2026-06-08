"""Lightweight DB utilities used across the project (Phase 1).

This module intentionally contains only a dependency-free health check
so importing the package does not require third-party packages yet.
"""
from __future__ import annotations

from typing import Any


def health_check() -> bool:
    """Return True when basic package-level invariants hold.

    In later phases this will verify connectivity to MariaDB.
    """
    # Currently nothing to check beyond module importability.
    return True


def ensure_commit(_session: Any) -> None:
    """Utility to commit a DB session with basic error handling.

    This is a placeholder to be replaced with real session management
    in Phase 4; it purposely accepts `Any` to avoid creating dependencies.
    """
    try:
        _session.commit()
    except Exception:
        try:
            _session.rollback()
        except Exception:
            pass
        raise
