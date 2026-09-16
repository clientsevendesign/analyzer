from __future__ import annotations

import argparse
import logging
import threading
import time
from datetime import datetime

from broker_mt5 import MT5Broker
from config import SAST, BotConfig, load_config
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


def run_loop(cfg: BotConfig, paper_override: bool | None = None) -> None:
    paper_mode = cfg.paper_mode if paper_override is None else paper_override
    broker = MT5Broker(cfg.symbol)
    risk = RiskManager(cfg, SAST)

    dashboard_thread = threading.Thread(target=run_dashboard, kwargs={"host": "127.0.0.1", "port": 8081}, daemon=True)
    dashboard_thread.start()
    update_state(status="starting", last_signal="initializing")

    logger.info("Starting US30 scalper for %s (paper_mode=%s)", cfg.symbol, paper_mode)
    logger.info(
        "Session SAST: %s -> %s | risk=%.2f%% | max dd=%.2f%% | max trades/day=%d",
        cfg.session_start_sast.strftime("%H:%M"),
        cfg.session_end_sast.strftime("%H:%M"),
        cfg.risk_per_trade_pct,
        cfg.max_daily_drawdown_pct,
        cfg.max_trades_per_day,
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
                    update_state(last_signal=idea.reason)
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

                if paper_mode:
                    logger.info(
                        "PAPER %s lot=%.2f sl=%.1f tp=%.1f | %s",
                        idea.side.upper(),
                        lot,
                        idea.stop_points,
                        idea.take_points,
                        idea.reason,
                    )
                    update_state(last_signal=f"{idea.side.upper()} | {idea.reason}", last_order=f"PAPER {idea.side.upper()} lot={lot}")
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
                    logger.info("LIVE order result: %s", result)
                    update_state(last_signal=f"{idea.side.upper()} | {idea.reason}", last_order=f"LIVE {idea.side.upper()} ticket={result.get('order')}")
                    risk.mark_trade()

            except Exception as exc:
                logger.exception("Loop error: %s", exc)
                update_state(last_error=str(exc))

            time.sleep(cfg.poll_seconds)

    finally:
        broker.shutdown()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="US30 scalper bot")
    parser.add_argument("--paper", action="store_true", help="Force paper mode")
    parser.add_argument("--live", action="store_true", help="Force live mode")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cfg = load_config()

    paper_override = None
    if args.paper and args.live:
        raise SystemExit("Use only one of --paper or --live")
    if args.paper:
        paper_override = True
    if args.live:
        paper_override = False

    run_loop(cfg, paper_override=paper_override)
