"""CSV loader for signal data.

Reads a CSV file and returns a list of `Signal` instances.
"""
from __future__ import annotations

from typing import List
import logging
from pathlib import Path
import pandas as pd

from stock_bot.models.signal import Signal

logger = logging.getLogger(__name__)


def load_signals_from_csv(path: str | Path) -> List[Signal]:
    """Load signals from a CSV file.

    Args:
        path: Path to the CSV file.

    Returns:
        List[Signal]

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if required columns are missing or rows are invalid.
    """
    p = Path(path)
    if not p.exists():
        logger.error("CSV file not found: %s", p)
        raise FileNotFoundError(p)

    df = pd.read_csv(p)
    logger.info("Loaded %d rows from %s", len(df), p)

    required = {"symbol", "score", "buy_price", "signal_date"}
    missing = required - set(c.lower() for c in df.columns)
    if missing:
        raise ValueError(f"Missing required columns in CSV: {missing}")

    signals: List[Signal] = []
    for idx, row in df.iterrows():
        try:
            # Convert pandas Series to plain dict with native types
            row_dict = {str(k): (None if pd.isna(v) else v) for k, v in row.items()}
            sig = Signal.from_dict(row_dict)
            signals.append(sig)
        except Exception as exc:
            logger.exception("Failed to parse row %s: %s", idx, exc)
            raise

    logger.info("Parsed %d signals from CSV", len(signals))
    return signals
