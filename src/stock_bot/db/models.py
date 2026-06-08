"""SQLAlchemy models mapping to MariaDB tables specified in project spec.

All tables use InnoDB and UTF8MB4 via the engine connection string.
"""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    MetaData,
    Table,
    Column,
    Integer,
    BigInteger,
    String,
    Date,
    DateTime,
    Numeric,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import registry, relationship

mapper_registry = registry()
metadata = MetaData()


class BaseModel:
    def __init__(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


@mapper_registry.mapped
class Trade(BaseModel):
    __table__ = Table(
        "trades",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("symbol", String(20), nullable=False, index=True),
        Column("action", String(10), nullable=False),
        Column("quantity", Integer, nullable=False),
        Column("price", Numeric(18, 4), nullable=False),
        Column("trade_date", Date, nullable=False),
        Column("created_at", DateTime, default=datetime.utcnow),
        Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    )


@mapper_registry.mapped
class Position(BaseModel):
    __table__ = Table(
        "positions",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("symbol", String(20), nullable=False, unique=True, index=True),
        Column("quantity", Integer, nullable=False),
        Column("average_price", Numeric(18, 4), nullable=False),
        Column("current_price", Numeric(18, 4), nullable=True),
        Column("unrealized_pnl", Numeric(18, 4), nullable=True),
        Column("created_at", DateTime, default=datetime.utcnow),
        Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
    )


@mapper_registry.mapped
class SignalModel(BaseModel):
    __table__ = Table(
        "signals",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("symbol", String(20), nullable=False, index=True),
        Column("score", Numeric(10, 2), nullable=True),
        Column("buy_price", Numeric(18, 4), nullable=True),
        Column("stop_loss", Numeric(18, 4), nullable=True),
        Column("target_price", Numeric(18, 4), nullable=True),
        Column("signal_date", Date, nullable=False),
        Column("created_at", DateTime, default=datetime.utcnow),
    )


@mapper_registry.mapped
class PortfolioSnapshot(BaseModel):
    __table__ = Table(
        "portfolio_snapshots",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("portfolio_value", Numeric(18, 4), nullable=False),
        Column("cash_available", Numeric(18, 4), nullable=False),
        Column("realized_pnl", Numeric(18, 4), nullable=False),
        Column("unrealized_pnl", Numeric(18, 4), nullable=False),
        Column("snapshot_date", Date, nullable=False),
    )


@mapper_registry.mapped
class BacktestRun(BaseModel):
    __table__ = Table(
        "backtest_runs",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("strategy_name", String(100), nullable=False),
        Column("start_date", Date, nullable=False),
        Column("end_date", Date, nullable=False),
        Column("cagr", Numeric(18, 4)),
        Column("sharpe_ratio", Numeric(18, 4)),
        Column("max_drawdown", Numeric(18, 4)),
        Column("win_rate", Numeric(18, 4)),
        Column("profit_factor", Numeric(18, 4)),
        Column("total_return", Numeric(18, 4)),
        Column("created_at", DateTime, default=datetime.utcnow),
    )


@mapper_registry.mapped
class BacktestTrade(BaseModel):
    __table__ = Table(
        "backtest_trades",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("run_id", Integer, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        Column("symbol", String(20), nullable=False),
        Column("entry_date", Date, nullable=False),
        Column("exit_date", Date, nullable=True),
        Column("entry_price", Numeric(18, 4), nullable=False),
        Column("exit_price", Numeric(18, 4), nullable=True),
        Column("pnl_percent", Numeric(18, 4), nullable=True),
    )


@mapper_registry.mapped
class AIReport(BaseModel):
    __table__ = Table(
        "ai_reports",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("report_date", Date, nullable=False),
        Column("summary", Text, nullable=True),
        Column("recommendations", Text, nullable=True),
        Column("created_at", DateTime, default=datetime.utcnow),
    )


@mapper_registry.mapped
class TelegramLog(BaseModel):
    __table__ = Table(
        "telegram_logs",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("message_type", String(50), nullable=False),
        Column("message_body", Text, nullable=True),
        Column("status", String(50), nullable=True),
        Column("sent_at", DateTime, nullable=True),
    )


# Indexes for common queries
Index("ix_signals_symbol_signal_date", SignalModel.__table__.c.symbol, SignalModel.__table__.c.signal_date)
Index("ix_trades_symbol_trade_date", Trade.__table__.c.symbol, Trade.__table__.c.trade_date)
