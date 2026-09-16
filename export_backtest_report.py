from __future__ import annotations

import json
from pathlib import Path

from config import load_config
from mt5_backtest import run_mt5_backtest


if __name__ == "__main__":
    cfg = load_config()
    result = run_mt5_backtest(cfg, timeframe="M1", bars=1200)
    Path("mt5_backtest_equity.csv").write_text("")
    Path("mt5_backtest_trades.csv").write_text("")
    result.to_csv("mt5_backtest_equity.csv")
    result.to_trade_log("mt5_backtest_trades.csv")
    with open("mt5_backtest_report.json", "w", encoding="utf-8") as handle:
        json.dump(result.metrics, handle, indent=2)
    print(json.dumps(result.metrics, indent=2))
