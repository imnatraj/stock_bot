"""Domain model for trading signals.

Provides typed conversion helpers used by CSV and Google Sheets loaders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Signal:
    symbol: str
    score: float
    buy_price: float
    stop_loss: Optional[float]
    target_price: Optional[float]
    signal_date: date
    notes: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Signal":
        """Create a `Signal` from a dict (case-insensitive keys accepted).

        This method is defensive: it will raise `ValueError` for missing or
        malformed required fields.
        """
        def get(key: str) -> Any:
            target = key.lower()
            for k, v in data.items():
                if k.lower() == target and v not in (None, ""):
                    return v
            return None

        symbol = get("symbol")
        if not symbol:
            raise ValueError("Missing required field: symbol")

        def parse_float(val: Any, name: str) -> Optional[float]:
            if val is None:
                return None
            try:
                return float(val)
            except Exception as exc:
                raise ValueError(f"Invalid float for {name}: {val}") from exc

        score = parse_float(get("score"), "score")
        if score is None:
            raise ValueError("Missing required field: score")

        buy_price = parse_float(get("buy_price"), "buy_price")
        if buy_price is None:
            raise ValueError("Missing required field: buy_price")

        stop_loss = parse_float(get("stop_loss"), "stop_loss")
        target_price = parse_float(get("target_price"), "target_price")

        raw_date = get("signal_date")
        if raw_date is None:
            raise ValueError("Missing required field: signal_date")
        if isinstance(raw_date, date):
            signal_date = raw_date
        else:
            # Accept ISO date strings
            try:
                signal_date = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
            except Exception as exc:
                raise ValueError(f"Invalid date for signal_date: {raw_date}") from exc

        notes = get("notes")
        if notes is not None:
            notes = str(notes)

        logger.debug("Parsed Signal: %s %s", symbol, score)
        return cls(
            symbol=str(symbol),
            score=score,
            buy_price=buy_price,
            stop_loss=stop_loss,
            target_price=target_price,
            signal_date=signal_date,
            notes=notes,
        )
