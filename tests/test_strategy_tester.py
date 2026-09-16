import unittest

from strategy_tester import run_backtest
from config import load_config


class StrategyTesterTests(unittest.TestCase):
    def test_run_backtest_returns_metrics(self):
        cfg = load_config()
        metrics = run_backtest(cfg, bars=120, seed=7)
        self.assertIn("trades", metrics)
        self.assertIn("win_rate", metrics)
        self.assertGreaterEqual(metrics["trades"], 0)
        self.assertGreaterEqual(metrics["net_pnl"], -1e18)


if __name__ == "__main__":
    unittest.main()
