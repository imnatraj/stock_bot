import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, datetime, timedelta
import pandas as pd
from decimal import Decimal

from stock_bot.db.health import ping_db
from stock_bot.config.settings import Settings
from stock_bot.models.signal import Signal
from stock_bot.integrations.csv_loader import load_signals_from_csv
from stock_bot.integrations.google_sheets import load_signals_from_sheet, update_sheets_portfolio
from stock_bot.ai.assistant import explain_ranking
from stock_bot.scanner.cli import run_scanner_and_alert
from stock_bot.logging_config import configure_logging
from stock_bot.scanner.scanner import evaluate_latest, compute_indicators, scan_universe
from stock_bot.services.portfolio_service import record_trade, compute_portfolio_snapshot

@pytest.fixture(name="db_session")
def fixture_db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine("sqlite:///:memory:")
    from stock_bot.db.models import metadata
    metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_db_health():
    ok, msg = ping_db()
    assert isinstance(ok, bool)

def test_settings_exceptions():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError):
            Settings.from_env()

    env = {
        "MYSQL_HOST": "localhost",
        "MYSQL_PORT": "abc",
        "MYSQL_DATABASE": "db",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "pwd",
    }
    with patch.dict("os.environ", env, clear=True):
        with pytest.raises(ValueError, match="MYSQL_PORT must be an integer"):
            Settings.from_env()

    env = {
        "MYSQL_HOST": "localhost",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "db",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "pwd",
    }
    with patch.dict("os.environ", env, clear=True):
        with pytest.raises(ValueError, match="GOOGLE_SHEET_ID"):
            Settings.from_env()

def test_signal_exceptions():
    with pytest.raises(ValueError, match="Missing required field: symbol"):
        Signal.from_dict({})
    with pytest.raises(ValueError, match="Missing required field: score"):
        Signal.from_dict({"symbol": "TCS"})
    with pytest.raises(ValueError, match="Missing required field: buy_price"):
        Signal.from_dict({"symbol": "TCS", "score": 75.0})
    with pytest.raises(ValueError, match="Missing required field: signal_date"):
        Signal.from_dict({"symbol": "TCS", "score": 75.0, "buy_price": 100.0})
    with pytest.raises(ValueError, match="Invalid date for signal_date"):
        Signal.from_dict({"symbol": "TCS", "score": 75.0, "buy_price": 100.0, "signal_date": "invalid-date"})

def test_csv_loader_exceptions():
    with pytest.raises(FileNotFoundError):
        load_signals_from_csv("nonexistent_file_xyz.csv")

@patch("stock_bot.integrations.google_sheets.build")
def test_google_sheets_load_and_write(mock_build):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_sheet = mock_service.spreadsheets.return_value
    mock_values = mock_sheet.values.return_value
    
    mock_values.get.return_value.execute.return_value = {
        "values": [
            ["Symbol", "Score", "Buy_Price", "Stop_Loss", "Target_Price", "Signal_Date"],
            ["RELIANCE.NS", "85.5", "1520.0", "1474.0", "1611.0", "2023-01-01"]
        ]
    }
    signals = load_signals_from_sheet("fake-sheet-id", "Sheet1!A1:F2")
    assert len(signals) == 1
    assert signals[0].symbol == "RELIANCE.NS"

    mock_values.update.return_value.execute.return_value = {}
    ok = update_sheets_portfolio("fake-sheet-id", "Sheet1!A1:E10", [{"symbol": "TCS.NS", "quantity": 10, "average_price": 3000.0}])
    assert ok

@patch("httpx.Client")
def test_ai_analyst_gemini_api(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "AI explanation from Gemini"}
                    ]
                }
            }
        ]
    }
    mock_client.post.return_value = mock_response

    env = {
        "GEMINI_API_KEY": "fake-key",
        "GEMINI_MODEL_NAME": "gemini-pro",
        "LLM_REQUEST_TIMEOUT": "10",
    }
    with patch.dict("os.environ", env):
        explanation = explain_ranking("TCS", {"r6": 12.0}, use_llm=True)
        assert explanation == "AI explanation from Gemini"

    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    mock_client.post.side_effect = [mock_response_429, mock_response]
    
    with patch.dict("os.environ", env):
        with patch("time.sleep") as mock_sleep:
            explanation = explain_ranking("TCS", {"r6": 12.0}, use_llm=True)
            assert explanation == "AI explanation from Gemini"
            assert mock_sleep.call_count == 1

@patch("stock_bot.scanner.cli.scan_universe")
@patch("stock_bot.scanner.cli.send_signal_alert")
def test_scanner_cli(mock_send, mock_scan):
    mock_scan.return_value = [
        Signal(symbol="INFY.NS", score=68.0, buy_price=1450.0, stop_loss=1406.5, target_price=1537.0, signal_date=date.today())
    ]
    mock_send.return_value = True
    
    sent = run_scanner_and_alert(["INFY.NS"])
    assert sent == 1

def test_logging_configuration():
    configure_logging()

def test_scanner_evaluate_latest():
    df = pd.DataFrame()
    res = evaluate_latest(df, "INFY.NS", {})
    assert res is None

    columns = pd.MultiIndex.from_tuples([("Open", "INFY.NS"), ("High", "INFY.NS"), ("Low", "INFY.NS"), ("Close", "INFY.NS"), ("Volume", "INFY.NS")])
    data = [[100] * 5] * 20
    df_multi = pd.DataFrame(data, columns=columns)
    df_ind = compute_indicators(df_multi)
    assert "close" in df_ind.columns

def test_telegram_formatting():
    from stock_bot.integrations.telegram import (
        format_portfolio_report,
        format_scanner_report,
        format_ranking_report,
        format_ai_report,
    )
    p_report = format_portfolio_report(
        1000.0, 5000.0, 100.0, 200.0,
        [{"symbol": "TCS", "quantity": 1, "average_price": 3000.0, "current_price": 3200.0, "unrealized_pnl": 200.0}]
    )
    assert "PORTFOLIO REPORT" in p_report
    assert "TCS" in p_report

    s_report = format_scanner_report([
        Signal(symbol="INFY.NS", score=65.0, buy_price=100.0, stop_loss=97.0, target_price=106.0, signal_date=date.today())
    ])
    assert "SCANNER REPORT" in s_report

    r_report = format_ranking_report([("RELIANCE", 85.5)])
    assert "RANKING REPORT" in r_report

    a_report = format_ai_report("RELIANCE", "Bullish")
    assert "AI ANALYST REPORT" in a_report

@patch("yfinance.download")
def test_ranking_engine_full(mock_download):
    from stock_bot.ranking.engine import rank_symbols, get_sector
    mock_download.return_value = pd.DataFrame(
        {"Close": [100.0] * 150, "Volume": [10000] * 150},
        index=pd.date_range(end="2023-01-01", periods=150)
    )
    ranked = rank_symbols(["RELIANCE.NS", "TCS.NS"])
    assert len(ranked) == 2
    assert "RELIANCE.NS" in ranked

    sector = get_sector("INVALID_XYZ")
    assert sector == "Unknown"

@patch("yfinance.Ticker")
@patch("stock_bot.services.portfolio_service.get_session")
def test_portfolio_service_snapshot(mock_get_session, mock_ticker_class, db_session):
    mock_get_session.return_value.__enter__.return_value = db_session
    mock_get_session.return_value.__exit__.return_value = None

    from stock_bot.db.models import Position
    pos = Position(symbol="INFY.NS", quantity=10, average_price=Decimal("1400.0"), current_price=Decimal("1400.0"), unrealized_pnl=Decimal("0.0"))
    db_session.add(pos)
    db_session.commit()

    mock_ticker = MagicMock()
    mock_ticker_class.return_value = mock_ticker
    mock_ticker.history.return_value = pd.DataFrame({"Close": [1450.0]}, index=[pd.Timestamp.today()])

    res = compute_portfolio_snapshot(cash_available=50000.0)
    assert res["portfolio_value"] == 50000.0 + 1450.0 * 10
    assert res["unrealized_pnl"] == (1450.0 - 1400.0) * 10

@patch("yfinance.download")
@patch("stock_bot.db.engine.get_session")
def test_scan_universe_db(mock_get_session, mock_download, db_session):
    mock_get_session.return_value.__enter__.return_value = db_session
    mock_get_session.return_value.__exit__.return_value = None

    # RSI low is 55, high is 70. Trend close above 50dma & 200dma. Vol > 1.5 * average
    dates = pd.date_range(end="2023-01-01", periods=250)
    # Simple linear uptrend where close is far above 200dma and 50dma
    # Hand-crafted close to yield RSI around 60
    close = [float(100.0 + i) for i in range(250)]
    # Tweak the last 15 days to stabilize gains and yield RSI between 55 and 70
    for idx in range(235, 250):
        close[idx] = close[234] + (idx - 234) * 0.5
    
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    openp = close
    # Average volume = 1000, last day = 2000 (> 1.5x)
    volume = [1000] * 249 + [2000]
    df = pd.DataFrame({"Open": openp, "High": high, "Low": low, "Close": close, "Volume": volume}, index=dates)
    mock_download.return_value = df

    signals = scan_universe(["RELIANCE.NS"])
    assert isinstance(signals, list)

@patch("stock_bot.integrations.telegram.Bot.send_message")
@patch("stock_bot.db.engine.get_session")
def test_telegram_retry_and_log(mock_get_session, mock_send, db_session):
    mock_get_session.return_value.__enter__.return_value = db_session
    mock_get_session.return_value.__exit__.return_value = None

    import os
    os.environ["TELEGRAM_BOT_TOKEN"] = "fake-token"
    os.environ["TELEGRAM_CHAT_ID"] = "-10012345"

    # 1. Mock failure then success
    mock_send.side_effect = [Exception("Transient error"), True]

    from stock_bot.integrations.telegram import send_signal_alert
    with patch("time.sleep") as mock_sleep:
        ok = send_signal_alert("hello test", delay=0.01)
        assert ok
        assert mock_sleep.call_count == 1

    from stock_bot.db.models import TelegramLog
    logs = db_session.query(TelegramLog).all()
    assert len(logs) == 1
    assert logs[0].status == "success"

    # 2. Mock complete failure
    mock_send.side_effect = Exception("Permanent error")
    with patch("time.sleep") as mock_sleep:
        ok = send_signal_alert("hello test 2", delay=0.01)
        assert not ok

    logs = db_session.query(TelegramLog).all()
    assert len(logs) == 2
    assert logs[1].status == "failed"

def test_all_repositories_methods(db_session):
    from stock_bot.db.models import PortfolioSnapshot, BacktestRun, BacktestTrade, AIReport, TelegramLog
    from stock_bot.repositories.sqlalchemy_repo import (
        PortfolioSnapshotRepository,
        BacktestRepository,
        AIReportRepository,
        TelegramLogRepository,
    )
    # PortfolioSnapshot
    snap_repo = PortfolioSnapshotRepository(db_session)
    snap = PortfolioSnapshot(portfolio_value=100.0, cash_available=100.0, realized_pnl=0.0, unrealized_pnl=0.0, snapshot_date=date.today())
    snap_repo.add(snap)
    
    # Backtest
    bt_repo = BacktestRepository(db_session)
    run = BacktestRun(strategy_name="test", start_date=date.today(), end_date=date.today())
    bt_repo.add_run(run)
    trade = BacktestTrade(run_id=run.id, symbol="TCS", entry_date=date.today(), entry_price=100.0)
    bt_repo.add_trade(trade)
    
    # AIReport
    ai_repo = AIReportRepository(db_session)
    report = AIReport(report_date=date.today(), recommendations="test")
    ai_repo.add(report)
    
    # TelegramLog
    tg_repo = TelegramLogRepository(db_session)
    log = TelegramLog(message_type="test")
    tg_repo.add(log)
    
    db_session.commit()
    
    assert db_session.query(PortfolioSnapshot).count() == 1
    assert db_session.query(BacktestRun).count() == 1
    assert db_session.query(BacktestTrade).count() == 1
    assert db_session.query(AIReport).count() == 1
    assert db_session.query(TelegramLog).count() == 1

@patch("stock_bot.services.portfolio_service.get_session")
def test_portfolio_service_sell_empty(mock_get_session, db_session):
    mock_get_session.return_value.__enter__.return_value = db_session
    mock_get_session.return_value.__exit__.return_value = None
    
    res = record_trade("RELIANCE.NS", "SELL", 10, 1500.0, date.today())
    assert res["status"] == "ok"
    assert res["realized_pnl"] == 0.0


def test_scanner_edge_cases():
    from stock_bot.scanner.scanner import evaluate_latest, scan_universe
    assert evaluate_latest(pd.DataFrame(range(10)), "TCS", {}) is None

    with patch("yfinance.download") as mock_download:
        mock_download.return_value = pd.DataFrame()
        signals = scan_universe(["TCS"])
        assert len(signals) == 0

    with patch("yfinance.download") as mock_download:
        mock_download.side_effect = Exception("yfinance failed")
        signals = scan_universe(["TCS"])
        assert len(signals) == 0


def test_portfolio_service_exceptions(db_session):
    with pytest.raises(ValueError, match="Action must be 'BUY' or 'SELL'"):
        record_trade("TCS", "HOLD", 1, 1.0)


@patch("yfinance.download")
def test_backtest_edge_cases(mock_download):
    from stock_bot.backtest.simple import run_backtest
    # 1. Empty download
    mock_download.return_value = pd.DataFrame()
    signals = [
        Signal(symbol="TCS", score=65.0, buy_price=100.0, stop_loss=97.0, target_price=106.0, signal_date=date.today())
    ]
    res = run_backtest(signals, capital=100.0)
    assert res["trades_count"] == 0

    # 2. Insufficient capital
    df = pd.DataFrame({"Open": [1000.0], "High": [1000.0], "Low": [1000.0], "Close": [1000.0], "Volume": [100]}, index=[pd.Timestamp.today()])
    mock_download.return_value = df
    res = run_backtest(signals, capital=100.0)
    assert res["trades_count"] == 0


@patch("stock_bot.scanner.cli.run_scanner_and_alert")
def test_scanner_cli_main(mock_run):
    mock_run.return_value = 1
    from stock_bot.scanner.cli import main
    with patch.dict("os.environ", {"SAMPLE_SYMBOLS": "TCS.NS"}):
        main()

    with patch.dict("os.environ", {}, clear=True):
        main()


def test_db_init_helpers():
    from stock_bot.db import health_check, ensure_commit
    assert health_check() is True

    # test ensure_commit with success
    mock_session = MagicMock()
    ensure_commit(mock_session)
    assert mock_session.commit.call_count == 1

    # test ensure_commit with error
    mock_session_fail = MagicMock()
    mock_session_fail.commit.side_effect = Exception("commit failed")
    with pytest.raises(Exception):
        ensure_commit(mock_session_fail)
    assert mock_session_fail.rollback.call_count == 1


def test_portfolio_init():
    from stock_bot.portfolio import current_snapshot
    res = current_snapshot()
    assert res == {"portfolio_value": 0.0, "cash_available": 0.0}


def test_reporting_init():
    from stock_bot.reporting import last_report
    assert last_report() == "No reports yet."


def test_package_main():
    from stock_bot import main
    with patch("builtins.print") as mock_print:
        main()
        assert mock_print.call_count == 1


def test_scanner_filter_branches():
    from stock_bot.scanner.scanner import evaluate_latest
    # 1. Missing DMAs (DF too short)
    dates = pd.date_range(end="2023-01-01", periods=10)
    df_short = pd.DataFrame({"close": [100.0]*10, "volume": [1000]*10, "rsi": [60.0]*10, "50dma": [None]*10, "200dma": [None]*10, "vol20": [1000.0]*10}, index=dates)
    res = evaluate_latest(df_short, "TCS", {"rsi_low": 55, "rsi_high": 70, "volume_multiplier": 1.5, "stop_loss_pct": 0.03, "target_pct": 0.06})
    assert res is None

    # 2. Price below DMAs
    df_below = pd.DataFrame({"close": [90.0]*25, "volume": [1000]*25, "rsi": [60.0]*25, "50dma": [100.0]*25, "200dma": [100.0]*25, "vol20": [1000.0]*25}, index=pd.date_range(end="2023-01-01", periods=25))
    res = evaluate_latest(df_below, "TCS", {"rsi_low": 55, "rsi_high": 70, "volume_multiplier": 1.5, "stop_loss_pct": 0.03, "target_pct": 0.06})
    assert res is None

    # 3. RSI out of range
    df_rsi = pd.DataFrame({"close": [110.0]*25, "volume": [1000]*25, "rsi": [50.0]*25, "50dma": [100.0]*25, "200dma": [100.0]*25, "vol20": [1000.0]*25}, index=pd.date_range(end="2023-01-01", periods=25))
    res = evaluate_latest(df_rsi, "TCS", {"rsi_low": 55, "rsi_high": 70, "volume_multiplier": 1.5, "stop_loss_pct": 0.03, "target_pct": 0.06})
    assert res is None

    # 4. Volume too low
    df_vol = pd.DataFrame({"close": [110.0]*25, "volume": [1000]*25, "rsi": [60.0]*25, "50dma": [100.0]*25, "200dma": [100.0]*25, "vol20": [1000.0]*25}, index=pd.date_range(end="2023-01-01", periods=25))
    res = evaluate_latest(df_vol, "TCS", {"rsi_low": 55, "rsi_high": 70, "volume_multiplier": 1.5, "stop_loss_pct": 0.03, "target_pct": 0.06})
    assert res is None


@patch("yfinance.Ticker")
@patch("stock_bot.services.portfolio_service.get_session")
def test_portfolio_service_more_branches(mock_get_session, mock_ticker_class, db_session):
    mock_get_session.return_value.__enter__.return_value = db_session
    mock_get_session.return_value.__exit__.return_value = None

    # 1. Sell more than position quantity
    from stock_bot.db.models import Position
    pos = Position(symbol="INFY.NS", quantity=5, average_price=Decimal("1400.0"), current_price=Decimal("1400.0"), unrealized_pnl=Decimal("0.0"))
    db_session.add(pos)
    db_session.commit()

    res = record_trade("INFY.NS", "SELL", 10, 1500.0, date.today())
    assert res["status"] == "ok"
    
    pos = db_session.query(Position).filter_by(symbol="INFY.NS").one()
    assert pos.quantity == 0

    # 2. Trigger yfinance ticker.history exception in compute_portfolio_snapshot
    pos = Position(symbol="TCS.NS", quantity=10, average_price=Decimal("3000.0"), current_price=Decimal("3000.0"), unrealized_pnl=Decimal("0.0"))
    db_session.add(pos)
    db_session.commit()

    mock_ticker = MagicMock()
    mock_ticker_class.return_value = mock_ticker
    mock_ticker.history.side_effect = Exception("yfinance history failed")

    res = compute_portfolio_snapshot(cash_available=50000.0)
    assert res["portfolio_value"] == 50000.0 + 3000.0 * 10  # fallback to existing current_price


@patch("httpx.Client")
def test_ai_analyst_exceptions(mock_client_class):
    import httpx
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client

    # Mock HTTP status error
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("500 Error", request=MagicMock(), response=mock_response)
    mock_client.post.return_value = mock_response

    env = {"GEMINI_API_KEY": "fake-key", "GEMINI_MODEL_NAME": "gemini-pro"}
    with patch.dict("os.environ", env):
        explanation = explain_ranking("TCS", {"r6": 12.0}, use_llm=True)
        assert "TCS" in explanation


@patch("yfinance.download")
def test_backtest_stop_loss(mock_download):
    from stock_bot.backtest.simple import run_backtest
    signals = [
        Signal(symbol="RELIANCE", score=65.0, buy_price=100.0, stop_loss=97.0, target_price=106.0, signal_date=date(2023, 1, 1))
    ]
    df = pd.DataFrame(
        {"Open": [100.0], "High": [101.0], "Low": [95.0], "Close": [96.0], "Volume": [1000]},
        index=[pd.Timestamp("2023-01-02")]
    )
    mock_download.return_value = df
    res = run_backtest(signals, capital=100000.0)
    assert res["trades_count"] == 1
    assert res["trades"][0]["exit_price"] == 97.0


@patch("yfinance.download")
@patch("stock_bot.db.engine.get_session")
def test_scan_universe_db_exception(mock_get_session, mock_download):
    mock_get_session.side_effect = Exception("DB Connection Error")

    dates = pd.date_range(end="2023-01-01", periods=250)
    close = [float(100.0 + i) for i in range(250)]
    for idx in range(235, 250):
        close[idx] = close[234] + (idx - 234) * 0.5
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    openp = close
    volume = [1000] * 249 + [2000]
    df = pd.DataFrame({"Open": openp, "High": high, "Low": low, "Close": close, "Volume": volume}, index=dates)
    mock_download.return_value = df

    signals = scan_universe(["RELIANCE.NS"])
    assert isinstance(signals, list)


def test_db_engine_exceptions():
    from stock_bot.db.engine import get_database_url
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="Database environment variables not fully set"):
            get_database_url()


def test_db_health_failure():
    with patch("stock_bot.db.health.get_engine", side_effect=Exception("Connection failed")):
        ok, msg = ping_db()
        assert not ok
        assert "Connection failed" in msg


def test_ensure_commit_rollback_failure():
    from stock_bot.db import ensure_commit
    mock_session = MagicMock()
    mock_session.commit.side_effect = Exception("commit failed")
    mock_session.rollback.side_effect = Exception("rollback failed")
    with pytest.raises(Exception, match="commit failed"):
        ensure_commit(mock_session)
    assert mock_session.rollback.called


def test_logging_configuration_with_handlers():
    import logging
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    root.handlers = []
    try:
        configure_logging("DEBUG")
        assert len(root.handlers) == 1
    finally:
        root.handlers = old_handlers


@patch("stock_bot.integrations.google_sheets.service_account.Credentials.from_service_account_file")
@patch("stock_bot.integrations.google_sheets.build")
def test_google_sheets_with_service_account(mock_build, mock_credentials):
    mock_credentials.return_value = MagicMock()
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_sheet = mock_service.spreadsheets.return_value
    mock_values = mock_sheet.values.return_value
    mock_values.get.return_value.execute.return_value = {
        "values": [
            ["Symbol", "Score", "Buy_Price", "Stop_Loss", "Target_Price", "Signal_Date"],
            ["TCS.NS", "60.0", "3000.0", "2910.0", "3180.0", "2023-01-01"]
        ]
    }
    
    # Test loading with service account file
    signals = load_signals_from_sheet("fake-sheet-id", "Sheet1!A1:F2", service_account_file="fake_key.json")
    assert len(signals) == 1
    assert signals[0].symbol == "TCS.NS"

    # Test loading retry logic failure
    mock_build.side_effect = Exception("Google build API error")
    with pytest.raises(Exception, match="Google build API error"):
        load_signals_from_sheet("fake-sheet-id", "Sheet1!A1:F2", max_retries=2, retry_delay=0.01)

    # Test update portfolio service account exception
    mock_credentials.side_effect = Exception("Load service account fail")
    ok = update_sheets_portfolio("fake-sheet-id", "Sheet1!A1", [], service_account_file="bad_key.json")
    assert not ok

    # Test update portfolio build exception
    mock_credentials.side_effect = None
    mock_build.side_effect = Exception("Build fail")
    ok = update_sheets_portfolio("fake-sheet-id", "Sheet1!A1", [], service_account_file="fake_key.json")
    assert not ok


@patch("stock_bot.integrations.telegram.Bot.send_message")
def test_telegram_detailed_branches(mock_send_message):
    # 1. Missing Token
    with patch.dict("os.environ", {}, clear=True):
        from stock_bot.integrations.telegram import send_signal_alert
        ok = send_signal_alert("hello")
        assert not ok

    # 2. Missing Chat ID
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "some-token"}, clear=True):
        ok = send_signal_alert("hello")
        assert not ok

    # 3. DB logging failure
    env = {
        "TELEGRAM_BOT_TOKEN": "token",
        "TELEGRAM_CHAT_ID": "chat_id",
    }
    with patch.dict("os.environ", env):
        # Successful send, failing DB log
        mock_send_message.return_value = MagicMock()
        with patch("stock_bot.db.engine.get_session", side_effect=Exception("DB log error")):
            ok = send_signal_alert("hello", delay=0.01)
            assert ok

        # Failed send, failing DB log
        mock_send_message.side_effect = Exception("Telegram API error")
        with patch("stock_bot.db.engine.get_session", side_effect=Exception("DB log error")):
            ok = send_signal_alert("hello", max_retries=1, delay=0.01)
            assert not ok


@patch("asyncio.get_event_loop")
def test_telegram_run_async_loop_running(mock_get_loop):
    from stock_bot.integrations.telegram import run_async
    mock_loop = MagicMock()
    mock_loop.is_running.return_value = True
    mock_get_loop.return_value = mock_loop

    async def sample_coro():
        return "async_result"

    res = run_async(sample_coro())
    assert res == "async_result"


@patch("stock_bot.services.portfolio_service.get_session")
@patch("stock_bot.integrations.google_sheets.update_sheets_portfolio")
def test_portfolio_sheets_sync_coverage(mock_update_sheets, mock_get_session, db_session):
    mock_get_session.return_value.__enter__.return_value = db_session
    mock_get_session.return_value.__exit__.return_value = None

    env = {
        "GOOGLE_SHEET_ID": "fake-sheet-id",
        "GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE": "fake-file.json"
    }
    with patch.dict("os.environ", env):
        # 1. Test record_trade triggers Sheets Sync successfully
        mock_update_sheets.return_value = True
        res = record_trade("RELIANCE.NS", "BUY", 10, 1500.0, date.today())
        assert res["status"] == "ok"
        assert mock_update_sheets.call_count == 1

        # 2. Test record_trade handles Sheets Sync exception
        mock_update_sheets.side_effect = Exception("Sheets update failed")
        res2 = record_trade("RELIANCE.NS", "SELL", 5, 1600.0, date.today())
        assert res2["status"] == "ok"

        # 3. Test compute_portfolio_snapshot sheets sync
        mock_update_sheets.side_effect = None
        mock_update_sheets.return_value = True
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = pd.DataFrame({"Close": [1550.0]}, index=[pd.Timestamp.today()])
            res3 = compute_portfolio_snapshot()
            assert res3["portfolio_value"] > 0


@patch("stock_bot.services.portfolio_service.get_session")
def test_portfolio_snapshot_fallback_cash(mock_get_session, db_session):
    mock_get_session.return_value.__enter__.return_value = db_session
    mock_get_session.return_value.__exit__.return_value = None

    # Test cash fallback when there is no snapshot in DB
    with patch.dict("os.environ", {"INITIAL_CASH": "250000.0"}):
        res = compute_portfolio_snapshot(cash_available=None)
        assert res["cash_available"] == 250000.0


@patch("yfinance.download")
@patch("stock_bot.scanner.scanner.evaluate_latest")
@patch("stock_bot.db.engine.get_session")
def test_scan_universe_persistence(mock_get_session, mock_eval, mock_download, db_session):
    mock_get_session.return_value.__enter__.return_value = db_session
    mock_get_session.return_value.__exit__.return_value = None

    mock_download.return_value = pd.DataFrame({"Close": [100.0] * 50, "Volume": [1000] * 50}, index=pd.date_range(end="2023-01-01", periods=50))
    mock_eval.return_value = Signal(
        symbol="TCS.NS",
        score=65.0,
        buy_price=3000.0,
        stop_loss=2910.0,
        target_price=3180.0,
        signal_date=date(2023, 1, 1)
    )

    # 1. Test successful DB insertion
    from stock_bot.db.models import SignalModel
    db_session.query(SignalModel).delete()
    db_session.commit()

    signals = scan_universe(["TCS.NS"])
    assert len(signals) == 1
    assert db_session.query(SignalModel).filter_by(symbol="TCS.NS").count() == 1

    # 2. Test DB insertion exception (should log and not raise)
    mock_get_session.side_effect = Exception("DB error during scan persist")
    signals2 = scan_universe(["TCS.NS"])
    assert len(signals2) == 1


@patch("httpx.Client")
@patch("stock_bot.db.engine.get_session")
def test_ai_analyst_detailed_scenarios(mock_get_session, mock_client_class, db_session):
    mock_get_session.return_value.__enter__.return_value = db_session
    mock_get_session.return_value.__exit__.return_value = None

    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client

    env = {
        "GEMINI_API_KEY": "fake-key",
        "GEMINI_MODEL_NAME": "gemini-pro"
    }
    
    # 1. Test local fallback formatting branch (sector, dist52)
    factors = {"sector": "IT", "dist52": 5.0, "r6": 12.0, "r3": 6.0, "vol": 100.0}
    exp = explain_ranking("TCS", factors, use_llm=False)
    assert "Sector: IT" in exp
    assert "Close to 52-week high." in exp

    # 2. Test Gemini API returns empty candidates list
    mock_response_empty = MagicMock()
    mock_response_empty.status_code = 200
    mock_response_empty.json.return_value = {"candidates": []}
    mock_client.post.return_value = mock_response_empty

    with patch.dict("os.environ", env):
        res = explain_ranking("TCS", factors, use_llm=True)
        assert "TCS" in res  # fell back to local explanation

    # 3. Test Gemini API DB persistence exception
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Bullish AI analysis text"}]
                }
            }
        ]
    }
    mock_client.post.return_value = mock_response
    mock_get_session.side_effect = Exception("DB save report failed")

    with patch.dict("os.environ", env):
        res2 = explain_ranking("TCS", factors, use_llm=True)
        assert res2 == "Bullish AI analysis text"





