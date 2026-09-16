from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from config import BotConfig


@dataclass
class RiskState:
    trade_day: date
    day_start_balance: float
    trades_today: int = 0
    last_trade_time: datetime | None = None


class RiskManager:
    def __init__(self, cfg: BotConfig, tz: ZoneInfo):
        self.cfg = cfg
        self.tz = tz
        today = datetime.now(tz).date()
        self.state = RiskState(trade_day=today, day_start_balance=cfg.starting_balance_zar)

    def reset_if_new_day(self, balance: float) -> None:
        today = datetime.now(self.tz).date()
        if today != self.state.trade_day:
            self.state = RiskState(trade_day=today, day_start_balance=balance)

    def can_trade(self, balance: float, has_open_position: bool) -> tuple[bool, str]:
        self.reset_if_new_day(balance)

        if self.cfg.one_position_at_a_time and has_open_position:
            return False, "Open position exists"

        if self.state.trades_today >= self.cfg.max_trades_per_day:
            return False, "Max trades reached for today"

        drawdown_pct = 0.0
        if self.state.day_start_balance > 0:
            drawdown_pct = max(
                0.0,
                (self.state.day_start_balance - balance) / self.state.day_start_balance * 100,
            )
        if drawdown_pct >= self.cfg.max_daily_drawdown_pct:
            return False, f"Max daily drawdown hit ({drawdown_pct:.2f}%)"

        if self.state.last_trade_time is not None:
            elapsed = datetime.now(self.tz) - self.state.last_trade_time
            if elapsed < timedelta(minutes=self.cfg.cooldown_minutes):
                remain = timedelta(minutes=self.cfg.cooldown_minutes) - elapsed
                return False, f"Cooldown active ({int(remain.total_seconds())}s left)"

        return True, "OK"

    def mark_trade(self) -> None:
        self.state.trades_today += 1
        self.state.last_trade_time = datetime.now(self.tz)

    def calc_lot_size(
        self,
        balance: float,
        stop_points: float,
        point_value_per_lot: float,
        min_lot: float,
        max_lot: float,
        lot_step: float,
    ) -> float:
        if stop_points <= 0 or point_value_per_lot <= 0:
            return 0.0

        risk_amount = balance * (self.cfg.risk_per_trade_pct / 100)
        raw_lot = risk_amount / (stop_points * point_value_per_lot)

        if raw_lot < min_lot:
            return 0.0

        steps = int(raw_lot / lot_step)
        sized = steps * lot_step
        sized = max(min_lot, min(sized, max_lot))
        return round(sized, 2)
