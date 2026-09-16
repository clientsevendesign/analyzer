from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "mt5-us30-analyzer", ".env"), override=False)

SAST = ZoneInfo("Africa/Johannesburg")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw is not None else default


def _time_hhmm(name: str, default: str) -> time:
    value = os.getenv(name, default)
    hour_str, min_str = value.split(":", 1)
    return time(hour=int(hour_str), minute=int(min_str))


@dataclass(frozen=True)
class BotConfig:
    symbol: str
    timeframe: str

    session_start_sast: time
    session_end_sast: time

    starting_balance_zar: float
    risk_per_trade_pct: float
    max_daily_drawdown_pct: float
    max_trades_per_day: int
    cooldown_minutes: int
    one_position_at_a_time: bool

    ema_fast: int
    ema_slow: int
    atr_period: int
    min_atr_points: float
    pullback_tolerance_points: float
    stop_atr_mult: float
    rr_ratio: float

    poll_seconds: int
    slippage_points: int
    magic_number: int
    paper_mode: bool

    mt5_login: str | None
    mt5_password: str | None
    mt5_server: str | None
    mt5_terminal_path: str | None


def load_config() -> BotConfig:
    return BotConfig(
        symbol=os.getenv("SYMBOL", "US30Cash"),
        timeframe=os.getenv("TIMEFRAME", "M1"),
        session_start_sast=_time_hhmm("SESSION_START_SAST", "09:00"),
        session_end_sast=_time_hhmm("SESSION_END_SAST", "22:00"),
        starting_balance_zar=_float("STARTING_BALANCE_ZAR", 1000.0),
        risk_per_trade_pct=_float("RISK_PER_TRADE_PCT", 0.5),
        max_daily_drawdown_pct=_float("MAX_DAILY_DRAWDOWN_PCT", 3.0),
        max_trades_per_day=_int("MAX_TRADES_PER_DAY", 6),
        cooldown_minutes=_int("COOLDOWN_MINUTES", 5),
        one_position_at_a_time=_bool("ONE_POSITION_AT_A_TIME", True),
        ema_fast=_int("EMA_FAST", 9),
        ema_slow=_int("EMA_SLOW", 21),
        atr_period=_int("ATR_PERIOD", 14),
        min_atr_points=_float("MIN_ATR_POINTS", 20),
        pullback_tolerance_points=_float("PULLBACK_TOLERANCE_POINTS", 25),
        stop_atr_mult=_float("STOP_ATR_MULT", 1.2),
        rr_ratio=_float("RR_RATIO", 1.5),
        poll_seconds=_int("POLL_SECONDS", 5),
        slippage_points=_int("SLIPPAGE_POINTS", 30),
        magic_number=_int("MAGIC_NUMBER", 830100),
        paper_mode=_bool("PAPER_MODE", True),
        mt5_login=os.getenv("MT5_LOGIN"),
        mt5_password=os.getenv("MT5_PASSWORD"),
        mt5_server=os.getenv("MT5_SERVER"),
        mt5_terminal_path=os.getenv("MT5_TERMINAL_PATH"),
    )
