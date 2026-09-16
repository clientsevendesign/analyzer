from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pandas as pd

from broker_mt5 import MT5Broker
from config import BotConfig, load_config
from risk import RiskManager
from strategy import enrich, generate_trade_idea


class MT5BacktestResult:
    def __init__(self, trades: List[Dict], equity_curve: List[Dict], metrics: Dict):
        self.trades = trades
        self.equity_curve = equity_curve
        self.metrics = metrics

    def to_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["time", "equity", "balance", "drawdown_pct", "trade_count"])
            writer.writeheader()
            writer.writerows(self.equity_curve)

    def to_trade_log(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["entry_time", "exit_time", "side", "entry_price", "exit_price", "pnl", "lot", "reason"],
            )
            writer.writeheader()
            writer.writerows(self.trades)


def run_mt5_backtest(cfg: BotConfig, timeframe: str = "M1", bars: int = 3000) -> MT5BacktestResult:
    broker = MT5Broker(cfg.symbol)
    broker.connect()
    try:
        df = broker.get_rates(timeframe, count=bars)
        df = df.rename(columns={"tick_volume": "volume"})
        df = enrich(df, cfg)

        point = broker.get_symbol_meta().point
        risk = RiskManager(cfg, tz=timezone.utc)

        balance = cfg.starting_balance_zar
        equity_curve: List[Dict] = []
        trades: List[Dict] = []
        open_trade: Dict | None = None
        max_balance = balance
        trade_count = 0

        for idx in range(50, len(df)):
            window = df.iloc[: idx + 1].copy()
            current_price = float(window.iloc[-1]["close"])
            idea = generate_trade_idea(window, cfg, point=point)

            if open_trade is None and idea.side != "none":
                lot = risk.calc_lot_size(
                    balance=balance,
                    stop_points=idea.stop_points or 0,
                    point_value_per_lot=1.0,
                    min_lot=0.01,
                    max_lot=50.0,
                    lot_step=0.01,
                )
                if lot > 0:
                    entry_price = float(window.iloc[-1]["close"])
                    open_trade = {
                        "side": idea.side,
                        "entry_price": entry_price,
                        "entry_time": window.iloc[-1]["time"].to_pydatetime().isoformat(),
                        "lot": lot,
                        "stop_points": idea.stop_points or 0,
                        "take_points": idea.take_points or 0,
                    }
                    continue

            if open_trade is None:
                equity_curve.append({
                    "time": window.iloc[-1]["time"].to_pydatetime().isoformat(),
                    "equity": round(balance, 2),
                    "balance": round(balance, 2),
                    "drawdown_pct": 0.0,
                    "trade_count": trade_count,
                })
                continue

            if open_trade["side"] == "buy" and current_price <= open_trade["entry_price"] - (open_trade["stop_points"] * point):
                exit_price = open_trade["entry_price"] - (open_trade["stop_points"] * point)
                pnl = (exit_price - open_trade["entry_price"]) * open_trade["lot"] * 1000.0
            elif open_trade["side"] == "sell" and current_price >= open_trade["entry_price"] + (open_trade["stop_points"] * point):
                exit_price = open_trade["entry_price"] + (open_trade["stop_points"] * point)
                pnl = (open_trade["entry_price"] - exit_price) * open_trade["lot"] * 1000.0
            elif open_trade["side"] == "buy" and current_price >= open_trade["entry_price"] + (open_trade["take_points"] * point):
                exit_price = open_trade["entry_price"] + (open_trade["take_points"] * point)
                pnl = (exit_price - open_trade["entry_price"]) * open_trade["lot"] * 1000.0
            elif open_trade["side"] == "sell" and current_price <= open_trade["entry_price"] - (open_trade["take_points"] * point):
                exit_price = open_trade["entry_price"] - (open_trade["take_points"] * point)
                pnl = (open_trade["entry_price"] - exit_price) * open_trade["lot"] * 1000.0
            else:
                equity_curve.append({
                    "time": window.iloc[-1]["time"].to_pydatetime().isoformat(),
                    "equity": round(balance, 2),
                    "balance": round(balance, 2),
                    "drawdown_pct": round((max_balance - balance) / max_balance * 100.0 if max_balance else 0.0, 2),
                    "trade_count": trade_count,
                })
                continue

            balance += pnl
            trade_count += 1
            max_balance = max(max_balance, balance)
            trades.append(
                {
                    "entry_time": open_trade["entry_time"],
                    "exit_time": window.iloc[-1]["time"].to_pydatetime().isoformat(),
                    "side": open_trade["side"],
                    "entry_price": round(open_trade["entry_price"], 5),
                    "exit_price": round(exit_price, 5),
                    "pnl": round(pnl, 2),
                    "lot": round(open_trade["lot"], 2),
                    "reason": "signal",
                }
            )
            open_trade = None

            equity_curve.append({
                "time": window.iloc[-1]["time"].to_pydatetime().isoformat(),
                "equity": round(balance, 2),
                "balance": round(balance, 2),
                "drawdown_pct": round((max_balance - balance) / max_balance * 100.0 if max_balance else 0.0, 2),
                "trade_count": trade_count,
            })

        if open_trade is not None:
            close_price = float(df.iloc[-1]["close"])
            pnl = 0.0
            if open_trade["side"] == "buy":
                pnl = (close_price - open_trade["entry_price"]) * open_trade["lot"] * 1000.0
            else:
                pnl = (open_trade["entry_price"] - close_price) * open_trade["lot"] * 1000.0
            balance += pnl
            trades.append(
                {
                    "entry_time": open_trade["entry_time"],
                    "exit_time": df.iloc[-1]["time"].to_pydatetime().isoformat(),
                    "side": open_trade["side"],
                    "entry_price": round(open_trade["entry_price"], 5),
                    "exit_price": round(close_price, 5),
                    "pnl": round(pnl, 2),
                    "lot": round(open_trade["lot"], 2),
                    "reason": "session-close",
                }
            )

            equity_curve.append({
                "time": df.iloc[-1]["time"].to_pydatetime().isoformat(),
                "equity": round(balance, 2),
                "balance": round(balance, 2),
                "drawdown_pct": round((max_balance - balance) / max_balance * 100.0 if max_balance else 0.0, 2),
                "trade_count": trade_count,
            })

        metrics = {
            "trades": len(trades),
            "win_rate": round(sum(1 for trade in trades if trade["pnl"] > 0) / len(trades), 3) if trades else 0.0,
            "net_pnl": round(balance - cfg.starting_balance_zar, 2),
            "final_balance": round(balance, 2),
            "max_drawdown_pct": round((max_balance - min([row["balance"] for row in equity_curve] if equity_curve else [balance])) / max_balance * 100.0 if max_balance else 0.0, 2),
            "trade_log": trades,
        }

        metrics = {
            "trades": len(trades),
            "win_rate": round(sum(1 for trade in trades if trade["pnl"] > 0) / len(trades), 3) if trades else 0.0,
            "net_pnl": round(balance - cfg.starting_balance_zar, 2),
            "final_balance": round(balance, 2),
            "max_drawdown_pct": round((max_balance - min([row["balance"] for row in equity_curve] if equity_curve else [balance])) / max_balance * 100.0 if max_balance else 0.0, 2),
            "trade_log": trades,
        }
        return MT5BacktestResult(trades=trades, equity_curve=equity_curve, metrics=metrics)
    finally:
        broker.shutdown()


if __name__ == "__main__":
    cfg = load_config()
    result = run_mt5_backtest(cfg, timeframe="M1", bars=600)
    print(result.metrics)
