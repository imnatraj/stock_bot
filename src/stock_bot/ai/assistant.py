"""AI assistant that explains rankings (V4).

If a Gemini/LLM API key or Google credentials are present, the assistant
can call an external API. Otherwise it returns a deterministic explanation
based on supplied factors.
"""
from __future__ import annotations

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


import time
import httpx

def explain_ranking(symbol: str, factors: Dict[str, Any], use_llm: bool = True) -> str:
    """Return an explanation string for why a symbol ranked highly.

    If use_llm is True and GEMINI_API_KEY is present, calls the Gemini API via httpx.
    Otherwise, falls back to a high-quality local analysis.
    """
    # 1. Local fallback analysis
    lines = [f"{symbol}", ""]
    for k, v in factors.items():
        if k != "sector":
            lines.append(f"- {k}: {v}")
    if "sector" in factors:
        lines.append(f"- Sector: {factors['sector']}")
    lines.append("")
    lines.append("Summary:")
    if factors.get("r6", 0) > 10:
        lines.append("Strong 6-month uptrend.")
    if factors.get("r3", 0) > 5:
        lines.append("Positive recent momentum (3-month).")
    if factors.get("dist52", 100) < 10:
        lines.append("Close to 52-week high.")
    if factors.get("vol", 0) > 0:
        lines.append("Volume showing recent strength.")
    local_explanation = "\n".join(lines)

    # 2. Check configuration
    api_key = os.getenv("GEMINI_API_KEY")
    if not use_llm or not api_key:
        logger.info("Gemini API not configured or use_llm=False; using local explanation")
        return local_explanation

    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-pro")
    timeout = float(os.getenv("LLM_REQUEST_TIMEOUT", "30"))
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    # Build prompt and instruct AI to never predict prices or forecast returns
    factors_str = "\n".join(f"{k}: {v}" for k, v in factors.items())
    prompt = (
        "System Rules:\n"
        "1. You are a professional quant analyst explaining a stock's recent ranking.\n"
        "2. Do NOT forecast future returns.\n"
        "3. Do NOT predict future prices.\n"
        "4. Base your analysis STRICTLY on the supplied data.\n\n"
        f"Symbol: {symbol}\n"
        f"Supplied Quantitative Factors:\n{factors_str}\n\n"
        "Please provide a concise, factual explanation of why this stock has ranked highly based only on these factors. Keep it under 150 words."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    # 3. HTTP Request with retries and exponential backoff
    max_retries = 3
    retry_delay = 1.0
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                logger.info("Calling Gemini API for symbol %s (attempt %d/%d)", symbol, attempt + 1, max_retries)
                response = client.post(url, json=payload, headers={"Content-Type": "application/json"})

                # Handle rate limits
                if response.status_code == 429:
                    logger.warning("Gemini API rate limited (429). Retrying...")
                    time.sleep(retry_delay * (2 ** attempt))
                    continue

                response.raise_for_status()
                res_data = response.json()

                candidates = res_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        ai_text = parts[0].get("text", "").strip()
                        if ai_text:
                            # Save AI Report to Database
                            try:
                                from stock_bot.db.engine import get_session
                                from stock_bot.db.models import AIReport
                                from datetime import date
                                
                                with get_session() as session:
                                    report = AIReport(
                                        report_date=date.today(),
                                        summary=f"AI explanation for {symbol}",
                                        recommendations=ai_text,
                                    )
                                    session.add(report)
                                    logger.info("Saved AI Report for %s to database", symbol)
                            except Exception as db_exc:
                                logger.debug("Could not save AI Report to database: %s", db_exc)
                            return ai_text

                logger.warning("Empty response from Gemini API")
                break
        except httpx.HTTPStatusError as http_err:
            logger.warning("Gemini API HTTP error: %s", http_err)
            time.sleep(retry_delay * (2 ** attempt))
        except Exception as exc:
            logger.exception("Gemini API call failed: %s", exc)
            time.sleep(retry_delay * (2 ** attempt))

    logger.warning("Failed calling Gemini API after %d attempts; using local fallback", max_retries)
    return local_explanation
