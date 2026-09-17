import unittest
from typing import cast

from config import load_config
from strategy import TradeIdea, enrich, generate_trade_idea
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

    def test_executable_signal_has_metadata(self):
        cfg = load_config()
        df = build_synthetic_candles(bars=260, seed=29)
        df = df.rename(columns={"tick_volume": "volume"})
        enriched = enrich(df, cfg)

        executable = None
        for idx in range(60, len(enriched)):
            idea = generate_trade_idea(enriched.iloc[: idx + 1], cfg, point=0.1)
            if idea.side in {"buy", "sell"}:
                executable = idea
                break

        self.assertIsNotNone(executable, "Expected at least one executable setup in synthetic data")
        executable = cast(TradeIdea, executable)
        self.assertGreater(executable.confidence, 0.0)
        self.assertIn(executable.sentiment, {"bullish", "bearish"})
        self.assertIn(executable.market_condition, {"trending", "ranging", "volatile"})


if __name__ == "__main__":
    unittest.main()
