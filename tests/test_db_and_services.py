from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
import pytest
import pandas as pd

from stock_bot.db.models import metadata, Trade, Position, SignalModel
from stock_bot.repositories.sqlalchemy_repo import (
    TradesRepository,
    PositionsRepository,
    SignalsRepository,
)
from stock_bot.services.portfolio_service import record_trade
from stock_bot.ranking.engine import score_symbols
from stock_bot.backtest.simple import run_backtest
from stock_bot.ai.assistant import explain_ranking
from stock_bot.models.signal import Signal

# Use SQLite in-memory database for local offline testing
@pytest.fixture(name="db_session")
def fixture_db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_repositories(db_session):
    # Test TradesRepository
    trades_repo = TradesRepository(db_session)
    t = Trade(symbol="RELIANCE.NS", action="BUY", quantity=10, price=Decimal("2000.0"), trade_date=date.today())
    trades_repo.add(t)
    db_session.commit()
    assert len(trades_repo.list()) == 1
    assert trades_repo.list()[0].symbol == "RELIANCE.NS"

    # Test PositionsRepository
    pos_repo = PositionsRepository(db_session)
    pos = pos_repo.upsert("RELIANCE.NS", 10, 2000.0)
    db_session.commit()
    assert len(pos_repo.list()) == 1
    assert pos_repo.list()[0].quantity == 10

    pos_repo.upsert("RELIANCE.NS", 15, 2100.0)
    db_session.commit()
    assert pos_repo.list()[0].quantity == 15
    assert pos_repo.list()[0].average_price == 2100.0

    # Test SignalsRepository
    sig_repo = SignalsRepository(db_session)
    s = SignalModel(symbol="INFY.NS", score=Decimal("65.5"), buy_price=Decimal("1500.0"), signal_date=date.today())
    sig_repo.add(s)
    db_session.commit()
    assert len(sig_repo.recent()) == 1


@patch("stock_bot.services.portfolio_service.get_session")
def test_portfolio_service(mock_get_session, db_session):
    # Set up mock session
    mock_get_session.return_value.__enter__.return_value = db_session
    mock_get_session.return_value.__exit__.return_value = None

    # Test BUY order
    res = record_trade("RELIANCE.NS", "BUY", 10, 1500.0, date.today())
    assert res["status"] == "ok"
    assert res["cash_available"] == 100000.0 - 15000.0

    pos = db_session.query(Position).filter_by(symbol="RELIANCE.NS").one()
    assert pos.quantity == 10
    assert pos.average_price == Decimal("1500.0")

    # Test another BUY order to verify average price calculation
    res = record_trade("RELIANCE.NS", "BUY", 5, 1600.0, date.today())
    pos = db_session.query(Position).filter_by(symbol="RELIANCE.NS").one()
    assert pos.quantity == 15
    # (15000 + 8000) / 15 = 1533.3333
    assert abs(pos.average_price - Decimal("1533.3333")) < Decimal("0.001")

    # Test SELL order to verify realized P&L
    res = record_trade("RELIANCE.NS", "SELL", 5, 1700.0, date.today())
    assert res["status"] == "ok"
    # pnl = 5 * (1700 - 1533.3333) = 5 * 166.6667 = 833.3333
    assert abs(Decimal(str(res["trade_realized_pnl"])) - Decimal("833.3333")) < Decimal("0.001")
    assert abs(Decimal(str(res["realized_pnl"])) - Decimal("833.3333")) < Decimal("0.001")

    pos = db_session.query(Position).filter_by(symbol="RELIANCE.NS").one()
    assert pos.quantity == 10


def test_ranking_scoring():
    metrics = {
        "RELIANCE": {"r6": 15.0, "r3": 8.0, "vol": 10000.0, "sector": "Energy"},
        "TCS": {"r6": 10.0, "r3": 5.0, "vol": 5000.0, "sector": "Technology"},
        "INFY": {"r6": 8.0, "r3": 6.0, "vol": 8000.0, "sector": "Technology"},
    }
    ranked = score_symbols(metrics)
    assert len(ranked) == 3
    assert ranked[0][0] == "RELIANCE"  # should be highest due to top returns and volume


def test_backtest_metrics():
    signals = [
        Signal(
            symbol="RELIANCE",
            score=65.0,
            buy_price=1500.0,
            stop_loss=1455.0,
            target_price=1590.0,
            signal_date=date(2023, 1, 1),
        )
    ]
    # Patch yfinance download to return simulated exit
    with patch("yfinance.download") as mock_download:
        dates = [datetime(2023, 1, 2) + timedelta(days=i) for i in range(10)]
        df = pd.DataFrame(
            {
                "Open": [1500.0] * 10,
                "High": [1510.0, 1520.0, 1600.0] + [1500.0] * 7,
                "Low": [1490.0] * 10,
                "Close": [1505.0] * 10,
                "Volume": [10000] * 10,
            },
            index=dates,
        )
        mock_download.return_value = df

        summary = run_backtest(signals, capital=100000.0, max_holding_days=20)
        assert summary["trades_count"] == 1
        assert summary["win_rate"] == 100.0
        assert len(summary["trades"]) == 1
        assert summary["trades"][0]["exit_price"] == 1590.0  # target hit on day 3 (1600 High)


def test_ai_analyst_fallback():
    factors = {"r6": 12.5, "r3": 6.2, "dist52": 4.5, "vol": 150000, "sector": "Technology"}
    # Call without API key to trigger fallback
    with patch.dict("os.environ", {}, clear=True):
        explanation = explain_ranking("RELIANCE", factors, use_llm=True)
        assert "RELIANCE" in explanation
        assert "Strong 6-month uptrend" in explanation
