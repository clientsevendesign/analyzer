from __future__ import annotations

from config import load_config
from mt5_backtest import run_mt5_backtest


if __name__ == "__main__":
    cfg = load_config()
    result = run_mt5_backtest(cfg, timeframe="M1", bars=1200)
    print(result.metrics)
    result.to_csv("mt5_backtest_equity.csv")
    result.to_trade_log("mt5_backtest_trades.csv")
    print("Wrote mt5_backtest_equity.csv and mt5_backtest_trades.csv")
