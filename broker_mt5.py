from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd

from config import load_config


TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
}


@dataclass
class SymbolMeta:
    point: float
    min_lot: float
    max_lot: float
    lot_step: float
    point_value_per_lot: float


class MT5Broker:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.cfg = load_config()

    def connect(self) -> None:
        init_kwargs = {}
        if self.cfg.mt5_terminal_path:
            init_kwargs["path"] = self.cfg.mt5_terminal_path

        if not mt5.initialize(**init_kwargs):
            code, msg = mt5.last_error()
            raise RuntimeError(f"MT5 initialize failed: ({code}) {msg}")

        if self.cfg.mt5_login and self.cfg.mt5_password and self.cfg.mt5_server:
            authorized = mt5.login(
                login=int(self.cfg.mt5_login),
                password=self.cfg.mt5_password,
                server=self.cfg.mt5_server,
            )
            if not authorized:
                code, msg = mt5.last_error()
                raise RuntimeError(f"MT5 login failed: ({code}) {msg}")

        selected = mt5.symbol_select(self.symbol, True)
        if not selected:
            raise RuntimeError(f"Could not select symbol: {self.symbol}")

    def shutdown(self) -> None:
        mt5.shutdown()

    def get_balance(self) -> float:
        info = mt5.account_info()
        if info is None:
            raise RuntimeError("Could not fetch account info")
        return float(info.balance)

    def get_symbol_meta(self) -> SymbolMeta:
        info = mt5.symbol_info(self.symbol)
        if info is None:
            raise RuntimeError(f"Could not fetch symbol info for {self.symbol}")

        tick_value = float(info.trade_tick_value)
        tick_size = float(info.trade_tick_size)
        point = float(info.point)
        point_value_per_lot = tick_value * (point / tick_size) if tick_size > 0 else 0.0

        return SymbolMeta(
            point=point,
            min_lot=float(info.volume_min),
            max_lot=float(info.volume_max),
            lot_step=float(info.volume_step),
            point_value_per_lot=point_value_per_lot,
        )

    def get_rates(self, timeframe: str, count: int = 300) -> pd.DataFrame:
        tf = TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        rates = mt5.copy_rates_from_pos(self.symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            raise RuntimeError("No rates returned from MT5")

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df[["time", "open", "high", "low", "close", "tick_volume"]]

    def get_open_position(self):
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None or len(positions) == 0:
            return None
        return positions[0]

    def get_tick(self):
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            raise RuntimeError(f"No tick for {self.symbol}")
        return tick

    def place_market_order(
        self,
        side: str,
        lot: float,
        stop_points: float,
        take_points: float,
        deviation: int,
        magic_number: int,
    ) -> dict:
        tick = self.get_tick()
        meta = self.get_symbol_meta()

        if side == "buy":
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
            sl = price - stop_points * meta.point
            tp = price + take_points * meta.point
        elif side == "sell":
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
            sl = price + stop_points * meta.point
            tp = price - take_points * meta.point
        else:
            raise ValueError("side must be 'buy' or 'sell'")

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": deviation,
            "magic": magic_number,
            "comment": "us30_scalper_bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            code, msg = mt5.last_error()
            raise RuntimeError(f"order_send failed: ({code}) {msg}")

        return {
            "retcode": int(result.retcode),
            "order": int(result.order),
            "deal": int(result.deal),
            "price": float(result.price) if result.price else price,
            "volume": lot,
            "side": side,
            "time": datetime.utcnow().isoformat(),
            "comment": result.comment,
        }

    def close_position(self, position_ticket: int, volume: float, deviation: int) -> dict:
        pos = self.get_open_position()
        if pos is None:
            raise RuntimeError("No open position to close")

        tick = self.get_tick()
        if pos.type == mt5.POSITION_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": position_ticket,
            "symbol": self.symbol,
            "volume": volume,
            "type": close_type,
            "price": price,
            "deviation": deviation,
            "magic": 0,
            "comment": "us30_scalper_close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            code, msg = mt5.last_error()
            raise RuntimeError(f"close order_send failed: ({code}) {msg}")

        return {
            "retcode": int(result.retcode),
            "order": int(result.order),
            "deal": int(result.deal),
            "price": float(result.price) if result.price else price,
            "time": datetime.utcnow().isoformat(),
            "comment": result.comment,
        }
