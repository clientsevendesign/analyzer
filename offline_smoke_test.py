from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pandas as pd

from config import SAST, load_config
from risk import RiskManager
from strategy import enrich, generate_trade_idea, idea_to_dict


def build_dummy_candles(n: int = 250) -> pd.DataFrame:
    rows = []
    base = 43000.0
    ts = datetime.now(timezone.utc) - timedelta(minutes=n)
    for i in range(n):
        drift = i * 0.6
        wave = math.sin(i / 8.0) * 9.0
        close = base + drift + wave
        open_ = close - 2.0
        high = max(open_, close) + 6.0
        low = min(open_, close) - 6.0
        rows.append({
            "time": ts + timedelta(minutes=i),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": 1000,
        })
    return pd.DataFrame(rows)


def main() -> None:
    cfg = load_config()
    df = build_dummy_candles()
    df = enrich(df, cfg)
    idea = generate_trade_idea(df, cfg, point=0.1)
    risk = RiskManager(cfg, tz=SAST)
    can_trade, reason = risk.can_trade(balance=1000.0, has_open_position=False)
    print("trade_idea=", idea_to_dict(idea))
    print("risk_gate=", can_trade, reason)


if __name__ == "__main__":
    main()
