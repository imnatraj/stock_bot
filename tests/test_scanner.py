from __future__ import annotations

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch

from stock_bot.scanner.scanner import scan_universe


def _make_sample_df(days: int = 250) -> pd.DataFrame:
    dates = pd.date_range(end=datetime.today(), periods=days, freq="B")
    # random walk close prices
    rng = np.random.default_rng(42)
    close = rng.normal(loc=0.0005, scale=0.02, size=days).cumsum() + 1000
    high = close + rng.uniform(0, 2, size=days)
    low = close - rng.uniform(0, 2, size=days)
    openp = close + rng.normal(0, 0.5, size=days)
    volume = rng.integers(1000, 10000, size=days)
    df = pd.DataFrame({"Open": openp, "High": high, "Low": low, "Close": close, "Volume": volume}, index=dates)
    return df


@patch("yfinance.download")
def test_scan_universe(mock_download):
    mock_download.return_value = _make_sample_df()
    symbols = ["RELIANCE.NS"]
    signals = scan_universe(symbols)
    # Signals may be empty depending on random data; ensure function runs and returns a list
    assert isinstance(signals, list)
