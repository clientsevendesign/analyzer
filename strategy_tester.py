from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pandas as pd

from config import BotConfig, load_config
from risk import RiskManager
from strategy import enrich, generate_trade_idea


def build_synthetic_candles(bars: int = 500, seed: int = 7) -> pd.DataFrame:
    rows = []
    base = 43000.0
    ts = datetime.now(timezone.utc) - timedelta(minutes=bars)
    for i in range(bars):
        rng = ((i + seed) % 11) - 5
        drift = i * 0.5
        wave = math.sin((i + seed) / 8.0) * 10.0
        close = base + drift + wave + rng
        open_ = close - 2.0 + (rng * 0.2)
        high = max(open_, close) + 6.0
        low = min(open_, close) - 6.0
        rows.append(
            {
                "time": ts + timedelta(minutes=i),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": 1000,
            }
        )
    return pd.DataFrame(rows)


def run_backtest(cfg: BotConfig, bars: int = 500, seed: int = 7) -> Dict:
    df = build_synthetic_candles(bars=bars, seed=seed)
    df = df.rename(columns={"tick_volume": "volume"})
    df = enrich(df, cfg)
    point = 0.1

    risk = RiskManager(cfg, tz=timezone.utc)
    trades: List[Dict] = []
    confidences: List[float] = []
    balance = cfg.starting_balance_zar
    entry_price = None
    entry_side = None
    entry_sl = None
    entry_tp = None
    entry_lot = None

    for idx in range(50, len(df)):
        current_price = float(df.iloc[idx]["close"])
        if entry_price is not None:
            hit_stop = (
                (entry_side == "buy" and current_price <= entry_sl)
                or (entry_side == "sell" and current_price >= entry_sl)
            )
            hit_take = (
                (entry_side == "buy" and current_price >= entry_tp)
                or (entry_side == "sell" and current_price <= entry_tp)
            )
            if hit_stop or hit_take:
                if entry_side == "buy":
                    pnl = (current_price - entry_price) * entry_lot * 1000.0
                else:
                    pnl = (entry_price - current_price) * entry_lot * 1000.0
                balance += pnl
                trades.append({"entry": entry_price, "exit": current_price, "pnl": pnl, "side": entry_side})
                entry_price = None
                entry_side = None
                entry_sl = None
                entry_tp = None
                entry_lot = None
            continue

        window = df.iloc[: idx + 1].copy()
        idea = generate_trade_idea(window, cfg, point=point)
        if idea.side == "none":
            continue
        if idea.confidence < cfg.confidence_threshold_pct:
            continue

        lot = risk.calc_lot_size(
            balance=balance,
            stop_points=idea.stop_points or 0,
            point_value_per_lot=1.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
        )
        if lot <= 0:
            continue

        entry_price = float(df.iloc[idx]["close"])
        entry_side = idea.side
        entry_sl = entry_price - ((idea.stop_points or 0) * point)
        entry_tp = entry_price + ((idea.take_points or 0) * point)
        entry_lot = lot
        confidences.append(idea.confidence)

        if entry_side == "sell":
            entry_sl = entry_price + ((idea.stop_points or 0) * point)
            entry_tp = entry_price - ((idea.take_points or 0) * point)

    if entry_price is not None:
        exit_price = float(df.iloc[-1]["close"])
        pnl = 0.0
        if entry_side == "buy":
            pnl = (exit_price - entry_price) * entry_lot * 1000.0
        else:
            pnl = (entry_price - exit_price) * entry_lot * 1000.0
        balance += pnl
        trades.append({"entry": entry_price, "exit": exit_price, "pnl": pnl, "side": entry_side})

    win_rate = 0.0
    if trades:
        win_rate = sum(1 for trade in trades if trade["pnl"] > 0) / len(trades)

    sharpe_ratio = 0.0
    if len(trades) > 1:
        pnls = [trade["pnl"] for trade in trades]
        avg = sum(pnls) / len(pnls)
        variance = sum((value - avg) ** 2 for value in pnls) / (len(pnls) - 1)
        std = variance ** 0.5
        sharpe_ratio = (avg / std) if std > 0 else 0.0

    return {
        "trades": len(trades),
        "win_rate": round(win_rate, 3),
        "net_pnl": round(balance - cfg.starting_balance_zar, 2),
        "final_balance": round(balance, 2),
        "avg_confidence": round(sum(confidences) / len(confidences), 2) if confidences else 0.0,
        "sharpe_ratio": round(sharpe_ratio, 3),
        "sample_trade": trades[0] if trades else None,
    }


if __name__ == "__main__":
    cfg = load_config()
    print(run_backtest(cfg, bars=300, seed=7))
