from __future__ import annotations

from pathlib import Path

from stock_bot.integrations.csv_loader import load_signals_from_csv


def test_load_signals_from_csv() -> None:
    sample = Path(__file__).resolve().parent.parent / "examples" / "google_sheet_sample.csv"
    signals = load_signals_from_csv(sample)
    assert len(signals) == 5
    assert signals[0].symbol == "RELIANCE.NS"
    assert abs(signals[0].score - 85.50) < 1e-6
