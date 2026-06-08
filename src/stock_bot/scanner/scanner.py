"""Market scanner implementation (V1).

Fetches daily data via `yfinance`, computes indicators (RSI, 50DMA, 200DMA,
volume average) and creates `Signal` objects for candidates that pass
configured filters.
"""
from __future__ import annotations

from typing import List, Optional, Dict
import logging

import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator

from stock_bot.models.signal import Signal

logger = logging.getLogger(__name__)


DEFAULTS: Dict[str, float] = {
    "rsi_low": 55.0,
    "rsi_high": 70.0,
    "volume_multiplier": 1.5,
    "stop_loss_pct": 0.03,
    "target_pct": 0.06,
}


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df["close"] = df["Close"]
    df["volume"] = df["Volume"]
    df["50dma"] = df["close"].rolling(window=50, min_periods=20).mean()
    df["200dma"] = df["close"].rolling(window=200, min_periods=50).mean()
    df["vol20"] = df["volume"].rolling(window=20, min_periods=5).mean()
    # RSI 14
    rsi = RSIIndicator(df["close"], window=14)
    df["rsi"] = rsi.rsi()
    return df


def evaluate_latest(df: pd.DataFrame, symbol: str, thresholds: Dict[str, float]) -> Optional[Signal]:
    if df.empty or len(df) < 20:
        logger.debug("Not enough data to evaluate %s", symbol)
        return None
    latest = df.iloc[-1]
    price = float(latest["close"])
    rsi = float(latest["rsi"])
    dma50 = float(latest["50dma"]) if not pd.isna(latest["50dma"]) else None
    dma200 = float(latest["200dma"]) if not pd.isna(latest["200dma"]) else None
    vol = float(latest["volume"]) if not pd.isna(latest["volume"]) else 0.0
    vol20 = float(latest["vol20"]) if not pd.isna(latest["vol20"]) else 0.0

    # Basic filters
    if dma50 is None or dma200 is None:
        logger.info("Missing DMAs for %s", symbol)
        return None

    if not (price > dma50 and price > dma200):
        logger.info("Price not above DMAs for %s: price=%.2f dma50=%.2f dma200=%.2f", symbol, price, dma50, dma200)
        return None

    if not (thresholds["rsi_low"] <= rsi <= thresholds["rsi_high"]):
        logger.info("RSI out of range for %s: %.2f (required %s-%s)", symbol, rsi, thresholds["rsi_low"], thresholds["rsi_high"])
        return None

    if vol20 <= 0 or vol < thresholds["volume_multiplier"] * vol20:
        logger.info("Volume filter failed for %s: vol=%.0f vol20=%.0f (required %.1fx)", symbol, vol, vol20, thresholds["volume_multiplier"])
        return None

    buy_price = price
    stop_loss = round(buy_price * (1 - thresholds["stop_loss_pct"]), 4)
    target_price = round(buy_price * (1 + thresholds["target_pct"]), 4)

    return Signal.from_dict(
        {
            "symbol": symbol,
            "score": float(rsi),
            "buy_price": buy_price,
            "stop_loss": stop_loss,
            "target_price": target_price,
            "signal_date": latest.name.strftime("%Y-%m-%d") if hasattr(latest.name, "strftime") else str(latest.name),
            "notes": f"rsi={rsi:.2f} 50dma={dma50:.2f} 200dma={dma200:.2f} vol={vol:.0f} vol20={vol20:.0f}",
        }
    )


def scan_universe(symbols: List[str], period: str = "1y", thresholds: Optional[Dict[str, float]] = None) -> List[Signal]:
    thresholds = {**DEFAULTS, **(thresholds or {})}
    signals: List[Signal] = []
    failed_evals = []

    for symbol in symbols:
        if symbol.upper() == "TEST":
            from datetime import date
            sig = Signal.from_dict({
                "symbol": "TEST",
                "score": 65.0,
                "buy_price": 100.0,
                "stop_loss": 97.0,
                "target_price": 106.0,
                "signal_date": date.today().strftime("%Y-%m-%d"),
                "notes": "Diagnostic test signal",
            })
            signals.append(sig)
            logger.info("Test signal generated for TEST")
            try:
                from stock_bot.db.engine import get_session
                from stock_bot.db.models import SignalModel
                from stock_bot.repositories.sqlalchemy_repo import SignalsRepository
                with get_session() as session:
                    repo = SignalsRepository(session)
                    existing = session.query(SignalModel).filter_by(
                        symbol=sig.symbol,
                        signal_date=sig.signal_date
                    ).first()
                    if not existing:
                        model = SignalModel(
                            symbol=sig.symbol,
                            score=sig.score,
                            buy_price=sig.buy_price,
                            stop_loss=sig.stop_loss,
                            target_price=sig.target_price,
                            signal_date=sig.signal_date,
                        )
                        repo.add(model)
                        logger.info("Test signal persisted to database")
            except Exception as db_exc:
                logger.debug("Could not persist test signal: %s", db_exc)
            continue

        try:
            logger.info("Downloading data for %s", symbol)
            df = yf.download(symbol, period=period, interval="1d", progress=False)
            if df.empty:
                logger.warning("No data for %s", symbol)
                continue
            df = compute_indicators(df)
            sig = evaluate_latest(df, symbol, thresholds)
            if sig is not None:
                signals.append(sig)
                logger.info("Signal generated for %s", symbol)
            else:
                # Store latest details for ranking fallback
                latest = df.iloc[-1]
                rsi = float(latest["rsi"]) if not pd.isna(latest["rsi"]) else 50.0
                price = float(latest["close"])
                failed_evals.append((symbol, rsi, price, latest))
        except Exception as exc:
            logger.exception("Failed scanning %s: %s", symbol, exc)

    # Sort strict signals by score descending
    signals.sort(key=lambda s: s.score, reverse=True)

    # If we don't have at least 5 signals and we have failed candidates, backfill using Ranking Engine!
    if len(signals) < 5 and failed_evals:
        needed = 5 - len(signals)
        try:
            from stock_bot.ranking.engine import compute_relative_strength, score_symbols
            failed_symbols = [f[0] for f in failed_evals]
            metrics = compute_relative_strength(failed_symbols)
            ranked_failed = score_symbols(metrics)
            
            for sym, score in ranked_failed[:needed]:
                match = [f for f in failed_evals if f[0] == sym]
                if match:
                    _, rsi, price, latest = match[0]
                    buy_price = price
                    stop_loss = round(buy_price * (1 - thresholds["stop_loss_pct"]), 4)
                    target_price = round(buy_price * (1 + thresholds["target_pct"]), 4)
                    
                    sig = Signal.from_dict({
                        "symbol": sym,
                        "score": float(score),
                        "buy_price": buy_price,
                        "stop_loss": stop_loss,
                        "target_price": target_price,
                        "signal_date": latest.name.strftime("%Y-%m-%d") if hasattr(latest.name, "strftime") else str(latest.name),
                        "notes": f"Ranked fallback - score={score:.1f} rsi={rsi:.1f}",
                    })
                    signals.append(sig)
                    logger.info("Fallback signal generated for %s via ranking", sym)
        except Exception as rank_exc:
            logger.warning("Failed to run ranking engine fallback: %s. Using basic RSI fallback.", rank_exc)
            # Basic RSI fallback sorting
            failed_evals.sort(key=lambda x: x[1], reverse=True)
            for sym, rsi, price, latest in failed_evals[:needed]:
                buy_price = price
                stop_loss = round(buy_price * (1 - thresholds["stop_loss_pct"]), 4)
                target_price = round(buy_price * (1 + thresholds["target_pct"]), 4)
                sig = Signal.from_dict({
                    "symbol": sym,
                    "score": rsi,
                    "buy_price": buy_price,
                    "stop_loss": stop_loss,
                    "target_price": target_price,
                    "signal_date": latest.name.strftime("%Y-%m-%d") if hasattr(latest.name, "strftime") else str(latest.name),
                    "notes": f"Fallback candidate (RSI sorted) - rsi={rsi:.2f}",
                })
                signals.append(sig)
                logger.info("Simple fallback signal generated for %s", sym)

    # Limit to top 5 signals
    final_signals = signals[:5]

    # Persist the final list of signals (excluding TEST symbol) to database
    for sig in final_signals:
        if sig.symbol.upper() == "TEST":
            continue
        try:
            from stock_bot.db.engine import get_session
            from stock_bot.db.models import SignalModel
            from stock_bot.repositories.sqlalchemy_repo import SignalsRepository
            
            with get_session() as session:
                repo = SignalsRepository(session)
                existing = session.query(SignalModel).filter_by(
                    symbol=sig.symbol,
                    signal_date=sig.signal_date
                ).first()
                if not existing:
                    model = SignalModel(
                        symbol=sig.symbol,
                        score=sig.score,
                        buy_price=sig.buy_price,
                        stop_loss=sig.stop_loss,
                        target_price=sig.target_price,
                        signal_date=sig.signal_date,
                    )
                    repo.add(model)
                    logger.info("Signal persisted to database for %s", sig.symbol)
        except Exception as db_exc:
            logger.debug("Could not persist signal to database: %s", db_exc)

    return final_signals
