import os
import unittest
from unittest.mock import patch

from config import load_config


class ConfigProfileTests(unittest.TestCase):
    @patch.dict(os.environ, {"SYMBOL": "US30Cash"}, clear=False)
    def test_us30_profile_defaults(self):
        cfg = load_config()
        self.assertEqual(cfg.symbol, "US30Cash")
        self.assertEqual(cfg.ema_fast, 5)
        self.assertEqual(cfg.ema_slow, 15)
        self.assertEqual(cfg.atr_period, 14)
        self.assertEqual(cfg.min_atr_points, 15.0)

    @patch.dict(os.environ, {"SYMBOL": "GBPUSD"}, clear=False)
    def test_gbpusd_profile_defaults(self):
        cfg = load_config()
        self.assertEqual(cfg.symbol, "GBPUSD")
        self.assertEqual(cfg.ema_fast, 9)
        self.assertEqual(cfg.ema_slow, 21)
        self.assertEqual(cfg.atr_period, 20)
        self.assertEqual(cfg.min_atr_points, 12.0)

    @patch.dict(os.environ, {"SYMBOL": "US30Cash"}, clear=False)
    def test_confidence_threshold_default(self):
        cfg = load_config()
        self.assertEqual(cfg.confidence_threshold_pct, 65.0)


if __name__ == "__main__":
    unittest.main()
