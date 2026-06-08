"""Repository implementations using SQLAlchemy sessions.

Provides a set of repositories following the repository pattern for domain
objects backed by the database models.
"""
from __future__ import annotations

from typing import List, Optional
import logging

from sqlalchemy.orm import Session

from stock_bot.db.models import Trade, Position, SignalModel, PortfolioSnapshot, BacktestRun, BacktestTrade, AIReport, TelegramLog

logger = logging.getLogger(__name__)


class TradesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, trade: Trade) -> Trade:
        self.session.add(trade)
        self.session.flush()
        return trade

    def list(self, limit: int = 100) -> List[Trade]:
        return self.session.query(Trade).order_by(Trade.__table__.c.trade_date.desc()).limit(limit).all()


class PositionsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, symbol: str, quantity: int, avg_price: float) -> Position:
        pos = self.session.query(Position).filter_by(symbol=symbol).one_or_none()
        if pos is None:
            pos = Position(symbol=symbol, quantity=quantity, average_price=avg_price)
            self.session.add(pos)
            self.session.flush()
            return pos
        pos.quantity = quantity
        pos.average_price = avg_price
        self.session.add(pos)
        return pos

    def list(self) -> List[Position]:
        return self.session.query(Position).all()


class SignalsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, signal: SignalModel) -> SignalModel:
        self.session.add(signal)
        self.session.flush()
        return signal

    def recent(self, days: int = 7) -> List[SignalModel]:
        return (
            self.session.query(SignalModel)
            .order_by(SignalModel.__table__.c.signal_date.desc())
            .limit(100)
            .all()
        )


class PortfolioSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        self.session.add(snapshot)
        self.session.flush()
        return snapshot


class BacktestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_run(self, run: BacktestRun) -> BacktestRun:
        self.session.add(run)
        self.session.flush()
        return run

    def add_trade(self, trade: BacktestTrade) -> BacktestTrade:
        self.session.add(trade)
        self.session.flush()
        return trade


class AIReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, report: AIReport) -> AIReport:
        self.session.add(report)
        self.session.flush()
        return report


class TelegramLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, log: TelegramLog) -> TelegramLog:
        self.session.add(log)
        self.session.flush()
        return log
