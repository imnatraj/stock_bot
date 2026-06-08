"""Google Sheets loader for signals.

Uses a service account JSON to read a given range and convert rows to `Signal`.
"""
from __future__ import annotations

from typing import List, Optional
import logging
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build

from stock_bot.models.signal import Signal

logger = logging.getLogger(__name__)


def _rows_to_signals(rows: list[list[str]]) -> List[Signal]:
    # Expect header in first row
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    signals: List[Signal] = []
    for row in rows[1:]:
        data = {header[i]: (row[i] if i < len(row) else None) for i in range(len(header))}
        sig = Signal.from_dict(data)
        signals.append(sig)
    return signals


def load_signals_from_sheet(
    spreadsheet_id: str,
    range_name: str,
    service_account_file: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> List[Signal]:
    """Load signals from a Google Sheets range.

    Args:
        spreadsheet_id: ID of the Google Sheets spreadsheet.
        range_name: A1 notation range (e.g., 'Sheet1!A1:G100').
        service_account_file: Path to service account JSON. If None, uses
            application default credentials.
        max_retries: number of retries for transient errors.
        retry_delay: seconds between retries.

    Returns:
        List[Signal]
    """
    creds = None
    if service_account_file:
        creds = service_account.Credentials.from_service_account_file(service_account_file, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])  # type: ignore[arg-type]

    attempt = 0
    last_exc = None
    while attempt < max_retries:
        try:
            service = build("sheets", "v4", credentials=creds, cache_discovery=False)
            sheet = service.spreadsheets()
            result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
            values = result.get("values", [])
            logger.info("Fetched %d rows from sheet %s %s", len(values), spreadsheet_id, range_name)
            return _rows_to_signals(values)
        except Exception as exc:
            last_exc = exc
            attempt += 1
            logger.warning("Attempt %d/%d failed reading sheet: %s", attempt, max_retries, exc)
            time.sleep(retry_delay)

    logger.error("All %d attempts to read sheet failed", max_retries)
    raise last_exc


def update_sheets_portfolio(
    spreadsheet_id: str,
    range_name: str,
    positions_data: List[dict],
    service_account_file: Optional[str] = None,
) -> bool:
    """Write positions list to Google Sheets.

    Each dict in positions_data should have keys: symbol, quantity, average_price, current_price, unrealized_pnl.
    """
    creds = None
    if service_account_file:
        try:
            creds = service_account.Credentials.from_service_account_file(
                service_account_file, scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
        except Exception as exc:
            logger.error("Failed to load service account file for writing: %s", exc)
            return False

    try:
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        sheet = service.spreadsheets()

        header = ["Symbol", "Quantity", "Average Price", "Current Price", "Unrealized P&L"]
        values = [header]
        for pos in positions_data:
            values.append([
                pos.get("symbol", ""),
                pos.get("quantity", 0),
                float(pos.get("average_price", 0.0)),
                float(pos.get("current_price", 0.0)) if pos.get("current_price") is not None else 0.0,
                float(pos.get("unrealized_pnl", 0.0)) if pos.get("unrealized_pnl") is not None else 0.0,
            ])

        body = {"values": values}
        sheet.values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body=body
        ).execute()
        logger.info("Successfully updated Google Sheet %s with portfolio positions", spreadsheet_id)
        return True
    except Exception as exc:
        logger.error("Failed to update Google Sheet: %s", exc)
        return False

