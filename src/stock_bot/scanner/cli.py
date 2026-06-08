"""CLI entrypoint to run the scanner and send Telegram alerts.

Example usage:
    PYTHONPATH=./src python -m stock_bot.scanner.cli
"""
from __future__ import annotations

import logging
import os
from typing import List

from stock_bot.scanner.scanner import scan_universe
from stock_bot.integrations.telegram import format_signal_message, send_signal_alert

logger = logging.getLogger(__name__)


def run_scanner_and_alert(symbols: List[str]) -> int:
    signals = scan_universe(symbols)
    sent = 0
    for sig in signals:
        msg = format_signal_message(sig.symbol, sig.buy_price, sig.stop_loss or 0.0, sig.target_price or 0.0)
        ok = send_signal_alert(msg)
        if ok:
            sent += 1
    return sent


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    
    symbols_env = os.getenv("SAMPLE_SYMBOLS")
    scan_index_env = os.getenv("SCAN_INDEX")
    
    symbols = []
    if symbols_env:
        symbols = [s.strip() for s in symbols_env.split(",") if s.strip()]
    elif scan_index_env:
        from stock_bot.scanner.constituents import CONSTITUENTS
        for idx_name in scan_index_env.split(","):
            idx_name = idx_name.strip().upper()
            if idx_name in CONSTITUENTS:
                symbols.extend(CONSTITUENTS[idx_name])
            else:
                logger.warning("Unknown index name in SCAN_INDEX: %s", idx_name)
    else:
        from stock_bot.scanner.constituents import CONSTITUENTS
        symbols = CONSTITUENTS["NIFTY50"]
        logger.info("No scan target specified; defaulting to NIFTY50 index constituents")

    # De-duplicate symbols
    symbols = list(dict.fromkeys(symbols))

    logger.info("Running scanner for %d symbols", len(symbols))
    sent = run_scanner_and_alert(symbols)
    logger.info("Sent %d alerts", sent)


if __name__ == "__main__":
    main()
