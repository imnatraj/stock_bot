"""Structured logging configuration for the application.

Uses the standard library so Phase 1 remains dependency-free.
"""
from __future__ import annotations

import logging
from typing import Optional


def configure_logging(level: Optional[str] = None) -> None:
    """Configure the root logger with a concise, structured format.

    Args:
        level: Optional logging level name (e.g., "INFO", "DEBUG").
    """
    lvl = level or "INFO"
    numeric_level = getattr(logging, lvl.upper(), logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    # Avoid adding multiple handlers during repeated imports
    if not root.handlers:
        root.setLevel(numeric_level)
        root.addHandler(handler)
