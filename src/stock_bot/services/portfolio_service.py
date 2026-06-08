"""Portfolio service to record trades and compute portfolio snapshots.

Uses repository pattern to persist trades and maintain positions.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date
from typing import Dict, Any
import logging

from stock_bot.db.engine import get_session
from stock_bot.db.models import Trade, Position, PortfolioSnapshot
from stock_bot.repositories.sqlalchemy_repo import TradesRepository, PositionsRepository, PortfolioSnapshotRepository

logger = logging.getLogger(__name__)


import os
import yfinance as yf

def record_trade(symbol: str, action: str, quantity: int, price: float, trade_date: date | None = None) -> Dict[str, Any]:
    trade_date = trade_date or date.today()
    action = action.upper()
    if action not in ("BUY", "SELL"):
        raise ValueError("Action must be 'BUY' or 'SELL'")

    with get_session() as session:
        trades_repo = TradesRepository(session)
        positions_repo = PositionsRepository(session)

        # 1. Fetch current cash and realized P&L from latest snapshot
        from stock_bot.db.models import PortfolioSnapshot
        last_snap = session.query(PortfolioSnapshot).order_by(PortfolioSnapshot.id.desc()).first()
        if last_snap is not None:
            cash = last_snap.cash_available
            realized_pnl = last_snap.realized_pnl
        else:
            cash = Decimal(os.getenv("INITIAL_CASH", "100000.0"))
            realized_pnl = Decimal("0.0")

        trade_price = Decimal(str(price))
        trade_qty = int(quantity)
        trade_value = trade_price * trade_qty

        # 2. Add trade record
        trade = Trade(
            symbol=symbol,
            action=action,
            quantity=trade_qty,
            price=trade_price,
            trade_date=trade_date,
        )
        trades_repo.add(trade)

        # 3. Update position and cash
        pos = session.query(Position).filter_by(symbol=symbol).one_or_none()
        trade_realized_pnl = Decimal("0.0")

        if action == "BUY":
            cash -= trade_value
            if pos is None:
                pos = Position(
                    symbol=symbol,
                    quantity=trade_qty,
                    average_price=trade_price,
                    current_price=trade_price,
                    unrealized_pnl=Decimal("0.0")
                )
                session.add(pos)
            else:
                total_cost = pos.average_price * pos.quantity + trade_value
                total_qty = pos.quantity + trade_qty
                pos.quantity = total_qty
                pos.average_price = (total_cost / total_qty).quantize(Decimal("0.0001"))
                pos.current_price = trade_price
                pos.unrealized_pnl = pos.quantity * (pos.current_price - pos.average_price)

        elif action == "SELL":
            cash += trade_value
            if pos is None or pos.quantity <= 0:
                logger.warning("Sell recorded for non-existing or empty position %s", symbol)
            else:
                sell_qty = min(pos.quantity, trade_qty)
                trade_realized_pnl = sell_qty * (trade_price - pos.average_price)
                realized_pnl += trade_realized_pnl

                pos.quantity = max(0, pos.quantity - sell_qty)
                if pos.quantity == 0:
                    pos.current_price = Decimal("0.0")
                    pos.unrealized_pnl = Decimal("0.0")
                else:
                    pos.unrealized_pnl = pos.quantity * (pos.current_price - pos.average_price)

        # 4. Compute overall portfolio snapshot
        positions = session.query(Position).all()
        portfolio_value = cash
        total_unrealized_pnl = Decimal("0.0")
        for p in positions:
            if p.quantity > 0 and p.current_price is not None:
                portfolio_value += p.current_price * p.quantity
                total_unrealized_pnl += p.unrealized_pnl

        snapshot = PortfolioSnapshot(
            portfolio_value=portfolio_value,
            cash_available=cash,
            realized_pnl=realized_pnl,
            unrealized_pnl=total_unrealized_pnl,
            snapshot_date=trade_date,
        )
        session.add(snapshot)
        session.flush()

        # 5. Google Sheets Sync
        sheet_id = os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        sheet_file = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE")
        if sheet_id and sheet_file:
            try:
                from stock_bot.integrations.google_sheets import update_sheets_portfolio
                positions_data = [
                    {
                        "symbol": p.symbol,
                        "quantity": p.quantity,
                        "average_price": p.average_price,
                        "current_price": p.current_price,
                        "unrealized_pnl": p.unrealized_pnl,
                    }
                    for p in positions if p.quantity > 0
                ]
                update_sheets_portfolio(sheet_id, "Portfolio!A1:E100", positions_data, sheet_file)
            except Exception as sheet_exc:
                logger.debug("Failed Google Sheets sync: %s", sheet_exc)

        session.commit()
        return {
            "status": "ok",
            "trade_id": trade.id,
            "cash_available": float(cash),
            "realized_pnl": float(realized_pnl),
            "trade_realized_pnl": float(trade_realized_pnl)
        }


def compute_portfolio_snapshot(cash_available: float | None = None) -> Dict[str, Any]:
    with get_session() as session:
        # 1. Fetch current cash and realized P&L from latest snapshot
        from stock_bot.db.models import PortfolioSnapshot
        last_snap = session.query(PortfolioSnapshot).order_by(PortfolioSnapshot.id.desc()).first()

        if cash_available is not None:
            cash = Decimal(str(cash_available))
            realized_pnl = last_snap.realized_pnl if last_snap is not None else Decimal("0.0")
        else:
            if last_snap is not None:
                cash = last_snap.cash_available
                realized_pnl = last_snap.realized_pnl
            else:
                cash = Decimal(os.getenv("INITIAL_CASH", "100000.0"))
                realized_pnl = Decimal("0.0")

        # 2. Update current prices of open positions from yfinance
        positions = session.query(Position).all()
        portfolio_value = cash
        total_unrealized_pnl = Decimal("0.0")

        for pos in positions:
            if pos.quantity > 0:
                try:
                    ticker = yf.Ticker(pos.symbol)
                    history = ticker.history(period="1d")
                    if not history.empty:
                        latest_close = float(history.iloc[-1]["Close"])
                        pos.current_price = Decimal(str(latest_close))
                        pos.unrealized_pnl = pos.quantity * (pos.current_price - pos.average_price)
                except Exception as yf_exc:
                    logger.warning("Could not update current price for %s via yfinance: %s", pos.symbol, yf_exc)

                if pos.current_price is not None:
                    portfolio_value += pos.current_price * pos.quantity
                    total_unrealized_pnl += pos.unrealized_pnl

        # 3. Create snapshot
        snapshot = PortfolioSnapshot(
            portfolio_value=portfolio_value,
            cash_available=cash,
            realized_pnl=realized_pnl,
            unrealized_pnl=total_unrealized_pnl,
            snapshot_date=date.today(),
        )
        session.add(snapshot)
        session.flush()

        # 4. Google Sheets Sync
        sheet_id = os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        sheet_file = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE")
        if sheet_id and sheet_file:
            try:
                from stock_bot.integrations.google_sheets import update_sheets_portfolio
                positions_data = [
                    {
                        "symbol": p.symbol,
                        "quantity": p.quantity,
                        "average_price": p.average_price,
                        "current_price": p.current_price,
                        "unrealized_pnl": p.unrealized_pnl,
                    }
                    for p in positions if p.quantity > 0
                ]
                update_sheets_portfolio(sheet_id, "Portfolio!A1:E100", positions_data, sheet_file)
            except Exception as sheet_exc:
                logger.debug("Failed Google Sheets sync: %s", sheet_exc)

        session.commit()
        return {
            "portfolio_value": float(portfolio_value),
            "cash_available": float(cash),
            "realized_pnl": float(realized_pnl),
            "unrealized_pnl": float(total_unrealized_pnl),
            "snapshot_id": snapshot.id,
        }
