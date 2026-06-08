"""Simple next-day backtest engine for V1.

For each `Signal`, buys at the next day's open and simulates until target or stop loss.
This is a lightweight engine intended for quick validation.
"""
from __future__ import annotations

from typing import List, Dict, Any
import logging

import pandas as pd
import yfinance as yf

from stock_bot.models.signal import Signal

logger = logging.getLogger(__name__)


def run_backtest(signals: List[Signal], capital: float = 100_000.0, max_holding_days: int = 20) -> Dict[str, Any]:
    import numpy as np
    trades = []
    for sig in signals:
        try:
            # fetch next 60 days to simulate exits (need sufficient trading days)
            start = pd.to_datetime(sig.signal_date) + pd.Timedelta(days=1)
            end = start + pd.Timedelta(days=max_holding_days * 3)
            df = yf.download(sig.symbol, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval="1d", progress=False)
            if df.empty:
                logger.warning("No price data for backtest symbol %s", sig.symbol)
                continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # buy at next open
            entry_price = float(df.iloc[0]["Open"])
            qty = int((capital / max(1, len(signals))) // entry_price)
            if qty <= 0:
                logger.warning("Insufficient capital to buy any shares of %s", sig.symbol)
                continue
            
            exit_price = None
            exit_date = None
            # Iterate through trading days, up to max_holding_days (20 trading days)
            for idx, (i, row) in enumerate(df.iterrows()):
                if idx >= max_holding_days:
                    break
                high = float(row["High"])
                low = float(row["Low"])
                # To be conservative, check stop loss first on the same day
                if low <= sig.stop_loss:
                    exit_price = sig.stop_loss
                    exit_date = i
                    break
                if high >= sig.target_price:
                    exit_price = sig.target_price
                    exit_date = i
                    break
            
            if exit_price is None:
                # exit at close of the last day in our holding period limit
                exit_idx = min(max_holding_days - 1, len(df) - 1)
                exit_price = float(df.iloc[exit_idx]["Close"])
                exit_date = df.index[exit_idx]

            pnl = (exit_price - entry_price) / entry_price * 100.0
            trades.append({
                "symbol": sig.symbol,
                "entry_date": start.strftime("%Y-%m-%d"),
                "exit_date": pd.to_datetime(exit_date).strftime("%Y-%m-%d"),
                "entry_price": round(entry_price, 4),
                "exit_price": round(exit_price, 4),
                "pnl_percent": round(pnl, 4),
                "quantity": qty,
            })
        except Exception as exc:
            logger.exception("Backtest failed for %s: %s", sig.symbol, exc)

    # compute summary metrics
    total_return = sum(((t["exit_price"] - t["entry_price"]) * t["quantity"]) for t in trades)
    win_count = sum(1 for t in trades if t["pnl_percent"] > 0)
    win_rate = (win_count / len(trades) * 100.0) if trades else 0.0

    # Profit Factor
    gross_profits = sum(((t["exit_price"] - t["entry_price"]) * t["quantity"]) for t in trades if t["pnl_percent"] > 0)
    gross_losses = sum(abs((t["exit_price"] - t["entry_price"]) * t["quantity"]) for t in trades if t["pnl_percent"] < 0)
    profit_factor = gross_profits / gross_losses if gross_losses > 0 else (999.0 if gross_profits > 0 else 0.0)

    # Sharpe Ratio
    pnl_percents = [t["pnl_percent"] for t in trades]
    if len(pnl_percents) > 1:
        mean_pnl = np.mean(pnl_percents)
        std_pnl = np.std(pnl_percents, ddof=1)
        sharpe_ratio = (mean_pnl / std_pnl) if std_pnl > 0 else 0.0
    else:
        sharpe_ratio = 0.0

    # Max Drawdown
    capital_history = [capital]
    current_capital = capital
    sorted_trades = sorted(trades, key=lambda t: t["exit_date"])
    for t in sorted_trades:
        pnl_val = (t["exit_price"] - t["entry_price"]) * t["quantity"]
        current_capital += pnl_val
        capital_history.append(current_capital)

    max_dd = 0.0
    peak = capital_history[0]
    for val in capital_history:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    max_drawdown = max_dd * 100.0

    # CAGR
    if trades:
        first_entry_date = min(pd.to_datetime(t["entry_date"]) for t in trades)
        last_exit_date = max(pd.to_datetime(t["exit_date"]) for t in trades)
        total_days = (last_exit_date - first_entry_date).days
        total_days = max(1, total_days)
        ending_capital = capital + total_return
        cagr = ((ending_capital / capital) ** (365.25 / total_days) - 1.0) * 100.0
    else:
        cagr = 0.0

    summary = {
        "capital": capital,
        "trades_count": len(trades),
        "total_return": round(total_return, 4),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 4),
        "sharpe_ratio": round(sharpe_ratio, 4),
        "max_drawdown": round(max_drawdown, 4),
        "cagr": round(cagr, 4),
        "trades": trades,
    }

    # Save to database
    try:
        from stock_bot.db.engine import get_session
        from stock_bot.db.models import BacktestRun, BacktestTrade
        from stock_bot.repositories.sqlalchemy_repo import BacktestRepository
        from datetime import datetime, date

        with get_session() as session:
            repo = BacktestRepository(session)
            if trades:
                first_entry = min(datetime.strptime(t["entry_date"], "%Y-%m-%d").date() for t in trades)
                last_exit = max(datetime.strptime(t["exit_date"], "%Y-%m-%d").date() for t in trades)
            else:
                first_entry = date.today()
                last_exit = date.today()

            run = BacktestRun(
                strategy_name="Swing Trading Assistant V1",
                start_date=first_entry,
                end_date=last_exit,
                cagr=summary["cagr"],
                sharpe_ratio=summary["sharpe_ratio"],
                max_drawdown=summary["max_drawdown"],
                win_rate=summary["win_rate"],
                profit_factor=summary["profit_factor"],
                total_return=summary["total_return"],
            )
            repo.add_run(run)

            for t in trades:
                bt_trade = BacktestTrade(
                    run_id=run.id,
                    symbol=t["symbol"],
                    entry_date=datetime.strptime(t["entry_date"], "%Y-%m-%d").date(),
                    exit_date=datetime.strptime(t["exit_date"], "%Y-%m-%d").date(),
                    entry_price=t["entry_price"],
                    exit_price=t["exit_price"],
                    pnl_percent=t["pnl_percent"],
                )
                repo.add_trade(bt_trade)
            logger.info("Saved backtest run %s and %d trades to database", run.id, len(trades))
    except Exception as db_exc:
        logger.debug("Could not persist backtest run to database: %s", db_exc)

    return summary
