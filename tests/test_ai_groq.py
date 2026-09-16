import unittest

from ai_groq import GroqTradeValidator


class GroqValidatorTests(unittest.TestCase):
    def test_fallback_when_missing_api_key(self):
        validator = GroqTradeValidator(api_key=None, model="llama-3.1-8b-instant")
        result = validator.analyze(
            symbol="US30Cash",
            side="buy",
            base_confidence=72.5,
            rr_ratio=1.5,
            context={"atr_points": 21.0},
        )
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.confidence, 72.5)
        self.assertIn(result.market_condition, {"trending", "ranging", "volatile"})
        usage = validator.usage_stats()
        self.assertEqual(usage["calls"], 1)
        self.assertEqual(usage["errors"], 0)


if __name__ == "__main__":
    unittest.main()
