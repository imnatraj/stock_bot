"""Relative Strength and Sector ranking engine (V3).

Computes scores based on returns and volume, then ranks symbols.
"""
from __future__ import annotations

from typing import List, Dict, Tuple
import logging

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def _returns(df: pd.Series, days: int) -> float:
    if len(df) < days + 1:
        return 0.0
    return (df.iloc[-1] / df.iloc[-days - 1] - 1.0) * 100.0


# Static map for fast offline fallback of sectors
SECTOR_MAP: Dict[str, str] = {
    "RELIANCE.NS": "Energy",
    "TCS.NS": "Technology",
    "INFY.NS": "Technology",
    "SBIN.NS": "Financial Services",
    "LT.NS": "Industrials",
    "RELIANCE": "Energy",
    "TCS": "Technology",
    "INFY": "Technology",
    "SBIN": "Financial Services",
    "LT": "Industrials",
}


def get_sector(symbol: str) -> str:
    # 1. Check pre-defined map
    if symbol in SECTOR_MAP:
        return SECTOR_MAP[symbol]
    
    # 2. Try fetching from yfinance info
    try:
        ticker = yf.Ticker(symbol)
        sector = ticker.info.get("sector")
        if sector:
            return sector
    except Exception:
        pass
        
    return "Unknown"


def compute_relative_strength(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """Return metrics for each symbol: 6m, 3m returns, 52w dist, volume strength, sector."""
    metrics = {}
    for symbol in symbols:
        try:
            df = yf.download(symbol, period="1y", interval="1d", progress=False)
            if df.empty:
                continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            close = df["Close"].dropna()
            r6 = _returns(close, 126)
            r3 = _returns(close, 63)
            high52 = close.max()
            dist52 = (high52 - close.iloc[-1]) / high52 * 100.0 if high52 else 0.0
            vol = df["Volume"].iloc[-20:].mean() if len(df) >= 20 else df["Volume"].mean()
            
            sector = get_sector(symbol)
            
            metrics[symbol] = {
                "r6": r6,
                "r3": r3,
                "dist52": dist52,
                "vol": float(vol),
                "sector": sector
            }
        except Exception as exc:
            logger.exception("Failed compute metrics for %s: %s", symbol, exc)
    return metrics


def score_symbols(metrics: Dict[str, Dict[str, Any]]) -> List[Tuple[str, float]]:
    import numpy as np

    syms = list(metrics.keys())
    if not syms:
        return []

    r6 = np.array([metrics[s]["r6"] for s in syms])
    r3 = np.array([metrics[s]["r3"] for s in syms])
    vol = np.array([metrics[s]["vol"] for s in syms])

    # Compute Sector performance (mean r6 of all stocks in the sector)
    sector_performances = {}
    sectors = [metrics[s]["sector"] for s in syms]
    unique_sectors = list(set(sectors))
    
    for sector in unique_sectors:
        sector_stocks = [s for s in syms if metrics[s]["sector"] == sector]
        sector_r6s = [metrics[s]["r6"] for s in sector_stocks]
        sector_performances[sector] = np.mean(sector_r6s) if sector_r6s else 0.0

    sector_vals = np.array([sector_performances[metrics[s]["sector"]] for s in syms])

    def normalize(arr):
        if arr.max() == arr.min():
            return np.zeros_like(arr)
        return (arr - arr.min()) / (arr.max() - arr.min())

    w_trend = 0.30        # Trend Strength (6m returns) = 30%
    w_rel = 0.25          # Relative Strength (3m returns) = 25%
    w_vol = 0.25          # Volume Strength = 25%
    w_sector = 0.20       # Sector Strength = 20%

    s_trend = normalize(r6)
    s_rel = normalize(r3)
    s_vol = normalize(vol)
    s_sector = normalize(sector_vals)

    scores = w_trend * s_trend + w_rel * s_rel + w_vol * s_vol + w_sector * s_sector
    ranked = sorted([(syms[i], float(scores[i] * 100.0)) for i in range(len(syms))], key=lambda x: x[1], reverse=True)
    return ranked


def rank_symbols(symbols: List[str]) -> List[str]:
    metrics = compute_relative_strength(symbols)
    ranked = score_symbols(metrics)
    return [s for s, _ in ranked]
