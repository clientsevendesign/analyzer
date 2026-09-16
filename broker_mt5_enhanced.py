"""
Enhanced MT5 Broker with connection resilience, health checks, and performance monitoring.
Designed for reliable live trading with XM and other MT5 brokers.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd

from config import load_config

logger = logging.getLogger(__name__)

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
}

# MT5 Connection health thresholds
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY_SECONDS = 2
HEALTH_CHECK_INTERVAL_SECONDS = 60
MAX_TICK_AGE_SECONDS = 5  # Alert if tick is older than 5 seconds
ABNORMAL_SPREAD_MULTIPLIER = 2.0  # Alert if spread > 2x historical average


@dataclass
class SymbolMeta:
    point: float
    min_lot: float
    max_lot: float
    lot_step: float
    point_value_per_lot: float
    bid: float
    ask: float
    spread_points: float


@dataclass
class ConnectionMetrics:
    last_successful_tick: datetime
    tick_lag_ms: float
    avg_spread_points: float
    abnormal_spread_detected: bool
    reconnect_count: int
    last_health_check: datetime


class MT5Broker:
    """Enhanced MT5 broker with connection resilience and performance monitoring."""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.cfg = load_config()
        self.connected = False
        self.metrics = ConnectionMetrics(
            last_successful_tick=datetime.utcnow(),
            tick_lag_ms=0.0,
            avg_spread_points=0.0,
            abnormal_spread_detected=False,
            reconnect_count=0,
            last_health_check=datetime.utcnow(),
        )
        self.spread_history = []  # Track recent spreads for anomaly detection
        self.MAX_SPREAD_HISTORY = 50

    def connect(self) -> None:
        """Initialize MT5 connection with retry logic."""
        attempt = 0
        while attempt < MAX_RECONNECT_ATTEMPTS:
            try:
                init_kwargs = {}
                if self.cfg.mt5_terminal_path:
                    init_kwargs["path"] = self.cfg.mt5_terminal_path

                if not mt5.initialize(**init_kwargs):
                    code, msg = mt5.last_error()
                    logger.error(f"MT5 init attempt {attempt + 1} failed: ({code}) {msg}")
                    attempt += 1
                    if attempt < MAX_RECONNECT_ATTEMPTS:
                        time.sleep(RECONNECT_DELAY_SECONDS)
                    continue

                # Attempt login if credentials provided
                if self.cfg.mt5_login and self.cfg.mt5_password and self.cfg.mt5_server:
                    authorized = mt5.login(
                        login=int(self.cfg.mt5_login),
                        password=self.cfg.mt5_password,
                        server=self.cfg.mt5_server,
                    )
                    if not authorized:
                        code, msg = mt5.last_error()
                        logger.error(f"MT5 login attempt {attempt + 1} failed: ({code}) {msg}")
                        attempt += 1
                        mt5.shutdown()
                        if attempt < MAX_RECONNECT_ATTEMPTS:
                            time.sleep(RECONNECT_DELAY_SECONDS)
                        continue

                # Select symbol
                selected = mt5.symbol_select(self.symbol, True)
                if not selected:
                    logger.error(f"Could not select symbol: {self.symbol}")
                    attempt += 1
                    mt5.shutdown()
                    if attempt < MAX_RECONNECT_ATTEMPTS:
                        time.sleep(RECONNECT_DELAY_SECONDS)
                    continue

                self.connected = True
                logger.info(f"MT5 connected successfully (attempt {attempt + 1}) for {self.symbol}")
                return

            except Exception as e:
                logger.error(f"Connection error on attempt {attempt + 1}: {e}")
                attempt += 1
                if attempt < MAX_RECONNECT_ATTEMPTS:
                    time.sleep(RECONNECT_DELAY_SECONDS)

        raise RuntimeError(
            f"Failed to connect to MT5 after {MAX_RECONNECT_ATTEMPTS} attempts. "
            "Check terminal, credentials, and network connection."
        )

    def reconnect(self) -> bool:
        """Attempt to reconnect if connection is lost."""
        if self.connected:
            try:
                mt5.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down MT5: {e}")

        try:
            self.connect()
            self.metrics.reconnect_count += 1
            return True
        except RuntimeError as e:
            logger.error(f"Reconnection failed: {e}")
            return False

    def health_check(self) -> tuple[bool, str]:
        """
        Verify connection health and detect anomalies.
        Returns (is_healthy, status_message)
        """
        now = datetime.utcnow()
        elapsed_since_check = (now - self.metrics.last_health_check).total_seconds()
        
        if elapsed_since_check < HEALTH_CHECK_INTERVAL_SECONDS:
            return True, "Health check not due yet"

        try:
            # Test account info fetch
            account_info = mt5.account_info()
            if account_info is None:
                return False, "Failed to fetch account info"

            # Test tick data fetch
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                return False, "Failed to fetch tick data"

            # Check tick freshness
            tick_time = datetime.fromtimestamp(tick.time)
            tick_age = (now - tick_time).total_seconds()
            if tick_age > MAX_TICK_AGE_SECONDS:
                logger.warning(f"Stale tick detected: {tick_age:.1f}s old")

            self.metrics.last_health_check = now
            return True, "Health check passed"

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False, f"Health check error: {str(e)}"

    def shutdown(self) -> None:
        """Clean shutdown of MT5 connection."""
        try:
            mt5.shutdown()
            self.connected = False
            logger.info("MT5 connection closed")
        except Exception as e:
            logger.error(f"Error shutting down MT5: {e}")

    def get_balance(self) -> float:
        """Fetch current account balance."""
        info = mt5.account_info()
        if info is None:
            raise RuntimeError("Could not fetch account info")
        return float(info.balance)

    def get_symbol_meta(self) -> SymbolMeta:
        """Fetch symbol metadata including spread and tick data."""
        info = mt5.symbol_info(self.symbol)
        if info is None:
            raise RuntimeError(f"Could not fetch symbol info for {self.symbol}")

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            raise RuntimeError(f"Could not fetch tick for {self.symbol}")

        tick_value = float(info.trade_tick_value)
        tick_size = float(info.trade_tick_size)
        point = float(info.point)
        point_value_per_lot = tick_value * (point / tick_size) if tick_size > 0 else 0.0

        # Calculate spread in points
        bid = float(tick.bid)
        ask = float(tick.ask)
        spread_points = (ask - bid) / point if point > 0 else 0.0

        # Track spread for anomaly detection
        self._update_spread_history(spread_points)
        self.metrics.avg_spread_points = sum(self.spread_history) / len(self.spread_history) if self.spread_history else 0.0
        
        # Detect abnormal spreads
        if self.metrics.avg_spread_points > 0:
            abnormal = spread_points > (self.metrics.avg_spread_points * ABNORMAL_SPREAD_MULTIPLIER)
            if abnormal and self.metrics.abnormal_spread_detected == False:
                logger.warning(f"Abnormal spread detected: {spread_points:.1f} vs avg {self.metrics.avg_spread_points:.1f}")
            self.metrics.abnormal_spread_detected = abnormal

        # Update tick lag
        tick_time = datetime.fromtimestamp(tick.time)
        self.metrics.last_successful_tick = tick_time
        self.metrics.tick_lag_ms = (datetime.utcnow() - tick_time).total_seconds() * 1000

        return SymbolMeta(
            point=point,
            min_lot=float(info.volume_min),
            max_lot=float(info.volume_max),
            lot_step=float(info.volume_step),
            point_value_per_lot=point_value_per_lot,
            bid=bid,
            ask=ask,
            spread_points=spread_points,
        )

    def _update_spread_history(self, spread_points: float) -> None:
        """Maintain rolling window of spread history for analysis."""
        self.spread_history.append(spread_points)
        if len(self.spread_history) > self.MAX_SPREAD_HISTORY:
            self.spread_history.pop(0)

    def get_rates(self, timeframe: str, count: int = 300) -> pd.DataFrame:
        """Fetch historical rates with validation."""
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
        """Get first open position for symbol."""
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None or len(positions) == 0:
            return None
        return positions[0]

    def get_all_open_positions(self):
        """Get all open positions for symbol."""
        positions = mt5.positions_get(symbol=self.symbol)
        return positions if positions else []

    def get_tick(self):
        """Fetch current tick with validation."""
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
        """Place market order with comprehensive error handling."""
        tick = self.get_tick()
        meta = self.get_symbol_meta()

        if side == "buy":
            order_type = mt5.ORDER_TYPE_BUY
            price = meta.ask
            sl = price - stop_points * meta.point
            tp = price + take_points * meta.point
        elif side == "sell":
            order_type = mt5.ORDER_TYPE_SELL
            price = meta.bid
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
            "spread_points": meta.spread_points,
            "time": datetime.utcnow().isoformat(),
            "comment": result.comment,
        }

    def close_position(self, position_ticket: int, volume: float, deviation: int) -> dict:
        """Close position with validation."""
        pos = self.get_open_position()
        if pos is None:
            raise RuntimeError("No open position to close")

        tick = self.get_tick()
        meta = self.get_symbol_meta()
        
        if pos.type == mt5.POSITION_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price = meta.bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = meta.ask

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
            "spread_points": meta.spread_points,
            "time": datetime.utcnow().isoformat(),
            "comment": result.comment,
        }

    def get_metrics(self) -> dict:
        """Return current connection metrics."""
        return {
            "connected": self.connected,
            "reconnect_count": self.metrics.reconnect_count,
            "avg_spread_points": round(self.metrics.avg_spread_points, 2),
            "abnormal_spread": self.metrics.abnormal_spread_detected,
            "tick_lag_ms": round(self.metrics.tick_lag_ms, 2),
            "last_successful_tick": self.metrics.last_successful_tick.isoformat(),
        }
