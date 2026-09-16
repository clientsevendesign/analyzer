from __future__ import annotations

import argparse
import logging
import os
import threading
import time
from datetime import datetime

from ai_groq import GroqTradeValidator
from broker_mt5 import MT5Broker
from config import SAST, BotConfig, SYMBOL_PROFILES, load_config
from dashboard import run_dashboard, update_state
from risk import RiskManager
from strategy import generate_trade_idea, enrich

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)
logger = logging.getLogger("us30_scalper")



def is_in_session(cfg: BotConfig) -> bool:
    now = datetime.now(SAST).time()
    if cfg.session_start_sast <= cfg.session_end_sast:
        return cfg.session_start_sast <= now <= cfg.session_end_sast
    return now >= cfg.session_start_sast or now <= cfg.session_end_sast



def should_force_close_outside_session(cfg: BotConfig) -> bool:
    return not is_in_session(cfg)



def _validate_environment(cfg: BotConfig) -> None:
    missing = []
    if not cfg.groq_api_key:
        missing.append("GROQ_API_KEY")
    if not cfg.symbol:
        missing.append("SYMBOL")

    if missing:
        logger.warning("Environment validation warning. Missing: %s", ", ".join(missing))
        logger.warning("Bot continues with fallback confidence analysis.")



def run_loop(cfg: BotConfig, paper_override: bool | None = None) -> None:
    paper_mode = cfg.paper_mode if paper_override is None else paper_override
    broker = MT5Broker(cfg.symbol)
    risk = RiskManager(cfg, SAST)
    validator = GroqTradeValidator(cfg.groq_api_key, cfg.groq_model, cfg.groq_timeout_seconds)

    _validate_environment(cfg)

    dashboard_thread = threading.Thread(target=run_dashboard, kwargs={"host": "127.0.0.1", "port": 8081}, daemon=True)
    dashboard_thread.start()
    update_state(
        status="starting",
        last_signal="initializing",
        current_symbol=cfg.symbol,
        available_symbols=sorted(SYMBOL_PROFILES.keys()),
        confidence_threshold=cfg.confidence_threshold_pct,
    )

    logger.info("Starting scalper for %s (paper_mode=%s)", cfg.symbol, paper_mode)
    logger.info(
        "Session SAST: %s -> %s | risk=%.2f%% | max dd=%.2f%% | max trades/day=%d | confidence>=%.1f",
        cfg.session_start_sast.strftime("%H:%M"),
        cfg.session_end_sast.strftime("%H:%M"),
        cfg.risk_per_trade_pct,
        cfg.max_daily_drawdown_pct,
        cfg.max_trades_per_day,
        cfg.confidence_threshold_pct,
    )

    broker.connect()
    try:
        while True:
            try:
                update_state(status="running")
                open_pos = broker.get_open_position()

                if should_force_close_outside_session(cfg) and open_pos is not None:
                    logger.info("Outside trading session, closing open position")
                    if paper_mode:
                        logger.info("PAPER close -> ticket=%s volume=%.2f", open_pos.ticket, open_pos.volume)
                    else:
                        result = broker.close_position(open_pos.ticket, open_pos.volume, cfg.slippage_points)
                        logger.info("LIVE close result: %s", result)

                if not is_in_session(cfg):
                    logger.info("Outside session, waiting...")
                    update_state(last_signal="outside-session")
                    time.sleep(cfg.poll_seconds)
                    continue

                balance = broker.get_balance()
                update_state(balance=round(balance, 2))
                try:
                    account = broker.get_account_info()
                    update_state(equity=round(account.get("equity", 0), 2))
                except Exception as exc:
                    logger.debug("Account info unavailable: %s", exc)

                can_trade, reason = risk.can_trade(balance, has_open_position=open_pos is not None)
                if not can_trade:
                    logger.info("Trade blocked: %s", reason)
                    time.sleep(cfg.poll_seconds)
                    continue

                meta = broker.get_symbol_meta()
                df = broker.get_rates(cfg.timeframe, count=400)
                df = enrich(df, cfg)
                idea = generate_trade_idea(df, cfg, point=meta.point)

                if idea.side == "none":
                    logger.info("No trade: %s", idea.reason)
                    update_state(last_signal=idea.reason, market_condition=idea.market_condition)
                    time.sleep(cfg.poll_seconds)
                    continue

                validation = validator.analyze(
                    symbol=cfg.symbol,
                    side=idea.side,
                    base_confidence=idea.confidence,
                    rr_ratio=cfg.rr_ratio,
                    context={
                        "atr_points": round((float(df.iloc[-1]["atr"]) / meta.point) if meta.point else 0.0, 3),
                        "ema_fast": round(float(df.iloc[-1]["ema_fast"]), 5),
                        "ema_slow": round(float(df.iloc[-1]["ema_slow"]), 5),
                        "close": round(float(df.iloc[-1]["close"]), 5),
                    },
                )
                final_confidence = round((idea.confidence * 0.4) + (validation.confidence * 0.6), 2)
                final_market_condition = validation.market_condition or idea.market_condition
                final_sentiment = validation.sentiment or idea.sentiment

                update_state(
                    confidence=final_confidence,
                    market_condition=final_market_condition,
                    sentiment=final_sentiment,
                    exit_confidence=idea.exit_confidence,
                    groq_usage=validator.usage_stats(),
                )

                if not validation.risk_reward_ok:
                    logger.info("Trade blocked by Groq risk/reward validation: %s", validation.reasoning)
                    update_state(last_signal=f"blocked | {validation.reasoning}")
                    time.sleep(cfg.poll_seconds)
                    continue

                if final_confidence < cfg.confidence_threshold_pct:
                    logger.info(
                        "Trade blocked by confidence threshold: %.2f < %.2f (%s)",
                        final_confidence,
                        cfg.confidence_threshold_pct,
                        validation.reasoning,
                    )
                    update_state(last_signal=f"blocked confidence {final_confidence:.1f}%")
                    time.sleep(cfg.poll_seconds)
                    continue

                lot = risk.calc_lot_size(
                    balance=balance,
                    stop_points=idea.stop_points or 0,
                    point_value_per_lot=meta.point_value_per_lot,
                    min_lot=meta.min_lot,
                    max_lot=meta.max_lot,
                    lot_step=meta.lot_step,
                )

                if lot <= 0:
                    logger.warning(
                        "Lot calc rejected trade (balance=%.2f, stop_points=%.1f).",
                        balance,
                        idea.stop_points or 0,
                    )
                    time.sleep(cfg.poll_seconds)
                    continue

                decision_reason = (
                    f"conf={final_confidence:.1f}% source={validation.source} "
                    f"condition={final_market_condition} sentiment={final_sentiment} "
                    f"entry={validation.entry_note} exit={validation.exit_note}"
                )

                if paper_mode:
                    logger.info(
                        "PAPER %s lot=%.2f sl=%.1f tp=%.1f | %s | %s",
                        idea.side.upper(),
                        lot,
                        idea.stop_points,
                        idea.take_points,
                        idea.reason,
                        decision_reason,
                    )
                    update_state(
                        last_signal=f"{idea.side.upper()} | {idea.reason}",
                        last_order=f"PAPER {idea.side.upper()} lot={lot}",
                        decision_reason=decision_reason,
                    )
                    risk.mark_trade()
                else:
                    result = broker.place_market_order(
                        side=idea.side,
                        lot=lot,
                        stop_points=idea.stop_points or 0,
                        take_points=idea.take_points or 0,
                        deviation=cfg.slippage_points,
                        magic_number=cfg.magic_number,
                    )
                    logger.info("LIVE order result: %s | %s", result, decision_reason)
                    update_state(
                        last_signal=f"{idea.side.upper()} | {idea.reason}",
                        last_order=f"LIVE {idea.side.upper()} ticket={result.get('order')}",
                        decision_reason=decision_reason,
                    )
                    risk.mark_trade()

            except Exception as exc:
                logger.exception("Loop error: %s", exc)
                update_state(last_error=str(exc))

            time.sleep(cfg.poll_seconds)

    finally:
        broker.shutdown()



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scalper bot")
    parser.add_argument("--paper", action="store_true", help="Force paper mode")
    parser.add_argument("--live", action="store_true", help="Force live mode")
    parser.add_argument("--symbol", choices=sorted(SYMBOL_PROFILES.keys()), help="Override trading symbol")
    return parser.parse_args()



if __name__ == "__main__":
    args = parse_args()
    if args.symbol:
        os.environ["SYMBOL"] = args.symbol
    cfg = load_config()

    paper_override = None
    if args.paper and args.live:
        raise SystemExit("Use only one of --paper or --live")
    if args.paper:
        paper_override = True
    if args.live:
        paper_override = False

    run_loop(cfg, paper_override=paper_override)
