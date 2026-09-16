from __future__ import annotations

from config import load_config
from strategy_tester import run_backtest


if __name__ == "__main__":
    cfg = load_config()
    metrics = run_backtest(cfg, bars=300, seed=7)
    print(metrics)
