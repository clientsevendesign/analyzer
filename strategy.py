from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd

from config import BotConfig


@dataclass
class TradeIdea:
    side: str  # "buy" | "sell" | "none"
    reason: str
    stop_points: Optional[float] = None
    take_points: Optional[float] = None
    confidence: float = 0.0
    market_condition: str = "ranging"
    sentiment: str = "neutral"
    exit_confidence: float = 0.0



def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()



def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()



def _vwap(series_high: pd.Series, series_low: pd.Series, series_close: pd.Series, series_volume: pd.Series) -> pd.Series:
    typical_price = (series_high + series_low + series_close) / 3.0
    return (typical_price * series_volume).cumsum() / series_volume.cumsum()



def _market_condition(atr_points: float, min_atr_points: float, ema_gap_points: float) -> str:
    if atr_points >= min_atr_points * 1.8:
        return "volatile"
    if abs(ema_gap_points) >= min_atr_points * 0.35:
        return "trending"
    return "ranging"



def enrich(df: pd.DataFrame, cfg: BotConfig) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = _ema(out["close"], cfg.ema_fast)
    out["ema_slow"] = _ema(out["close"], cfg.ema_slow)
    out["atr"] = _atr(out, cfg.atr_period)
    out["vwap"] = _vwap(out["high"], out["low"], out["close"], out["volume"].fillna(1))
    return out



def generate_trade_idea(df: pd.DataFrame, cfg: BotConfig, point: float) -> TradeIdea:
    if len(df) < max(cfg.ema_slow + 2, cfg.atr_period + 2):
        return TradeIdea(side="none", reason="Not enough candle history")

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3] if len(df) >= 3 else prev

    atr_points = (latest["atr"] / point) if point > 0 else 0
    if pd.isna(atr_points) or atr_points < cfg.min_atr_points:
        return TradeIdea(
            side="none",
            reason=f"Volatility too low (ATR points={atr_points:.1f})",
            market_condition="ranging",
        )

    ema_fast = latest["ema_fast"]
    ema_slow = latest["ema_slow"]
    close = latest["close"]
    prev_close = prev["close"]
    prev2_close = prev2["close"]
    vwap = latest["vwap"]

    breakout_long = close > max(prev_close, prev2_close) and close > ema_fast and ema_fast > ema_slow
    breakout_short = close < min(prev_close, prev2_close) and close < ema_fast and ema_fast < ema_slow

    retest_long = close > ema_fast and close > vwap and prev_close < vwap and latest["low"] < vwap
    retest_short = close < ema_fast and close < vwap and prev_close > vwap and latest["high"] > vwap

    stop_points = max(cfg.stop_atr_mult * atr_points, 10)
    take_points = max(stop_points * cfg.rr_ratio, 12)
    ema_gap_points = ((ema_fast - ema_slow) / point) if point > 0 else 0
    market_condition = _market_condition(atr_points, cfg.min_atr_points, ema_gap_points)

    setup_confidence = 50.0
    if breakout_long or breakout_short:
        setup_confidence += 12.0
    if retest_long or retest_short:
        setup_confidence += 10.0
    if market_condition == "trending":
        setup_confidence += 8.0
    if market_condition == "volatile":
        setup_confidence -= 8.0

    confidence = max(0.0, min(100.0, round(setup_confidence, 2)))
    exit_confidence = max(0.0, min(100.0, round(100.0 - abs(cfg.rr_ratio - 1.8) * 18.0, 2)))

    if breakout_long or retest_long:
        return TradeIdea(
            side="buy",
            reason="EMA/VWAP breakout or retest bullish",
            stop_points=stop_points,
            take_points=take_points,
            confidence=confidence,
            market_condition=market_condition,
            sentiment="bullish",
            exit_confidence=exit_confidence,
        )

    if breakout_short or retest_short:
        return TradeIdea(
            side="sell",
            reason="EMA/VWAP breakout or retest bearish",
            stop_points=stop_points,
            take_points=take_points,
            confidence=confidence,
            market_condition=market_condition,
            sentiment="bearish",
            exit_confidence=exit_confidence,
        )

    return TradeIdea(side="none", reason="No breakout/retest setup", market_condition=market_condition)



def idea_to_dict(idea: TradeIdea) -> Dict:
    return {
        "side": idea.side,
        "reason": idea.reason,
        "stop_points": idea.stop_points,
        "take_points": idea.take_points,
        "confidence": idea.confidence,
        "market_condition": idea.market_condition,
        "sentiment": idea.sentiment,
        "exit_confidence": idea.exit_confidence,
    }
