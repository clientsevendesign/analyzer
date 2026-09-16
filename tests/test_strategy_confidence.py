import unittest

from config import load_config
from strategy import enrich, generate_trade_idea
from strategy_tester import build_synthetic_candles


class StrategyConfidenceTests(unittest.TestCase):
    def test_generated_idea_contains_confidence_fields(self):
        cfg = load_config()
        df = build_synthetic_candles(bars=220, seed=17)
        df = df.rename(columns={"tick_volume": "volume"})
        enriched = enrich(df, cfg)

        idea = generate_trade_idea(enriched, cfg, point=0.1)
        self.assertIn(idea.market_condition, {"trending", "ranging", "volatile"})
        self.assertGreaterEqual(idea.confidence, 0.0)
        self.assertLessEqual(idea.confidence, 100.0)
        self.assertGreaterEqual(idea.exit_confidence, 0.0)
        self.assertLessEqual(idea.exit_confidence, 100.0)


if __name__ == "__main__":
    unittest.main()
