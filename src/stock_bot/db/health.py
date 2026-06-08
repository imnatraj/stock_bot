"""Database health checks."""
from __future__ import annotations

import logging
from typing import Tuple

from sqlalchemy import text

from stock_bot.db.engine import get_engine

logger = logging.getLogger(__name__)


def ping_db(timeout_seconds: int = 5) -> Tuple[bool, str]:
    """Return (ok, message)."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:
        logger.exception("DB ping failed: %s", exc)
        return False, str(exc)
