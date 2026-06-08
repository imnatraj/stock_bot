"""Telegram integration with retry logic.

Provides a simple sender that reads token from env and retries on failure.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


import asyncio
import concurrent.futures

def run_async(coro):
    if not asyncio.iscoroutine(coro):
        return coro
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return loop.run_until_complete(coro)


def send_signal_alert(message: str, chat_id: Optional[str] = None, max_retries: int = 3, delay: float = 1.0) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set; cannot send Telegram messages")
        return False

    chat = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not chat:
        logger.error("TELEGRAM_CHAT_ID not set; cannot send Telegram messages")
        return False

    bot = Bot(token=token)
    attempt = 0
    while attempt < max_retries:
        try:
            coro = bot.send_message(chat_id=chat, text=message)
            run_async(coro)
            logger.info("Sent Telegram message to %s", chat)

            # Persist message log to DB
            try:
                from stock_bot.db.engine import get_session
                from stock_bot.db.models import TelegramLog
                from datetime import datetime
                with get_session() as session:
                    log = TelegramLog(
                        message_type="alert",
                        message_body=message,
                        status="success",
                        sent_at=datetime.utcnow(),
                    )
                    session.add(log)
            except Exception as db_exc:
                logger.debug("Could not save Telegram log: %s", db_exc)

            return True
        except Exception as exc:
            attempt += 1
            logger.warning("Telegram send failed attempt %d/%d: %s", attempt, max_retries, exc)
            time.sleep(delay)

    # Save failed log
    try:
        from stock_bot.db.engine import get_session
        from stock_bot.db.models import TelegramLog
        from datetime import datetime
        with get_session() as session:
            log = TelegramLog(
                message_type="alert",
                message_body=message,
                status="failed",
                sent_at=datetime.utcnow(),
            )
            session.add(log)
    except Exception as db_exc:
        logger.debug("Could not save Telegram log: %s", db_exc)

    logger.error("Failed to send Telegram message after %d attempts", max_retries)
    return False


def format_signal_message(symbol: str, buy: float, sl: float, target: float) -> str:
    return f"{symbol}\n\nBUY: {buy:.2f}\nSL: {sl:.2f}\nTARGET: {target:.2f}"


def format_portfolio_report(cash: float, portfolio_value: float, realized_pnl: float, unrealized_pnl: float, positions: List[dict]) -> str:
    lines = [
        "📊 PORTFOLIO REPORT",
        f"Portfolio Value: ₹{portfolio_value:,.2f}",
        f"Cash Available: ₹{cash:,.2f}",
        f"Realized P&L: ₹{realized_pnl:,.2f}",
        f"Unrealized P&L: ₹{unrealized_pnl:,.2f}",
        "",
        "Positions:",
    ]
    for pos in positions:
        lines.append(
            f"• {pos['symbol']}: {pos['quantity']} @ ₹{pos['average_price']:.2f} (Current: ₹{pos['current_price']:.2f}, P&L: ₹{pos['unrealized_pnl']:.2f})"
        )
    return "\n".join(lines)


def format_scanner_report(signals: list) -> str:
    lines = ["🔍 SCANNER REPORT", f"Found {len(signals)} trading candidate(s):", ""]
    for sig in signals:
        lines.append(
            f"• {sig.symbol} - RSI: {sig.score:.1f} | BUY: ₹{sig.buy_price:.2f} | SL: ₹{sig.stop_loss:.2f} | TARGET: ₹{sig.target_price:.2f}"
        )
    return "\n".join(lines)


def format_ranking_report(ranked_symbols: List[Tuple[str, float]]) -> str:
    lines = ["📈 RANKING REPORT", "Top Stock Candidates:", ""]
    for idx, (sym, score) in enumerate(ranked_symbols):
        lines.append(f"{idx+1}. {sym} (Score: {score:.2f})")
    return "\n".join(lines)


def format_ai_report(symbol: str, summary: str) -> str:
    return f"🤖 AI ANALYST REPORT: {symbol}\n\n{summary}"
