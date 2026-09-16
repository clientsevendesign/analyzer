from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict
from urllib import error, request


@dataclass
class AIValidation:
    confidence: float
    market_condition: str
    sentiment: str
    risk_reward_ok: bool
    entry_note: str
    exit_note: str
    reasoning: str
    source: str


class GroqTradeValidator:
    def __init__(self, api_key: str | None, model: str, timeout_seconds: int = 10):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger("us30_scalper")
        self.usage: Dict[str, int] = {
            "calls": 0,
            "errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def _fallback(self, base_confidence: float, reason: str) -> AIValidation:
        market_condition = "ranging"
        if base_confidence >= 75:
            market_condition = "trending"
        elif base_confidence < 55:
            market_condition = "volatile"

        sentiment = "bullish" if "buy" in reason.lower() else "bearish" if "sell" in reason.lower() else "neutral"
        return AIValidation(
            confidence=max(0.0, min(100.0, round(base_confidence, 2))),
            market_condition=market_condition,
            sentiment=sentiment,
            risk_reward_ok=True,
            entry_note="Fallback validation used",
            exit_note="Use ATR-based stop/take from strategy",
            reasoning=reason,
            source="fallback",
        )

    def analyze(self, symbol: str, side: str, base_confidence: float, rr_ratio: float, context: Dict[str, Any]) -> AIValidation:
        if not self.api_key:
            return self._fallback(base_confidence=base_confidence, reason="Missing GROQ_API_KEY")

        prompt = (
            "You are validating a forex/index scalping trade signal. "
            "Return strict JSON with keys: confidence, market_condition, sentiment, risk_reward_ok, "
            "entry_note, exit_note, reasoning. "
            "confidence must be 0-100. market_condition must be one of trending/ranging/volatile. "
            "sentiment must be bullish/bearish/neutral.\n"
            f"Symbol: {symbol}\n"
            f"Signal side: {side}\n"
            f"Base confidence: {base_confidence}\n"
            f"Risk reward ratio: {rr_ratio}\n"
            f"Context: {json.dumps(context, separators=(',', ':'))}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Respond with only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }

        req = request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
        )

        self.usage["calls"] += 1
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            self.usage["errors"] += 1
            self.logger.warning("Groq validation failed, using fallback: %s", exc)
            return self._fallback(base_confidence=base_confidence, reason=f"Groq error: {exc}")

        usage = body.get("usage", {})
        self.usage["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
        self.usage["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
        self.usage["total_tokens"] += int(usage.get("total_tokens", 0) or 0)

        try:
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return AIValidation(
                confidence=max(0.0, min(100.0, float(parsed.get("confidence", base_confidence)))),
                market_condition=str(parsed.get("market_condition", "ranging")).lower(),
                sentiment=str(parsed.get("sentiment", "neutral")).lower(),
                risk_reward_ok=bool(parsed.get("risk_reward_ok", True)),
                entry_note=str(parsed.get("entry_note", "")),
                exit_note=str(parsed.get("exit_note", "")),
                reasoning=str(parsed.get("reasoning", "Groq validation")),
                source="groq",
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.usage["errors"] += 1
            self.logger.warning("Groq response parse failed, using fallback: %s", exc)
            return self._fallback(base_confidence=base_confidence, reason=f"Groq parse error: {exc}")

    def usage_stats(self) -> Dict[str, int]:
        return dict(self.usage)
