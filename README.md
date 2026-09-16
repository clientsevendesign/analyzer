# US30 Scalper Bot (Python + MT5)

Automated US30 scalping bot focused on small-account protection and strict
time-window trading in SAST.

## What this bot does

- Trades only during configured SAST session times (default `09:00` to `22:00`).
- Uses a simple, testable scalping strategy:
  - Trend filter: fast EMA vs slow EMA on M1 candles.
  - Entry trigger: pullback to fast EMA with momentum confirmation.
  - Volatility filter: minimum ATR threshold to avoid dead markets.
- Enforces deterministic risk controls before opening any trade:
  - Fixed risk per trade (default `0.5%` of balance).
  - Max daily drawdown stop (default `3%`).
  - Max trades per day (default `6`).
  - Cooldown between entries (default `5` minutes).
  - One open position at a time (default enabled).
- Places SL/TP at entry and manages exits automatically.

## Account profile

Designed for a small account (`ZAR 1000` baseline), with the bot skipping trades
when lot-size constraints would violate risk rules.

## Setup

1. Install dependencies:

```powershell
pip install -r requirements.txt
```

If `MetaTrader5` fails to install, your Python version is likely too new for
available MT5 wheels. Use Python 3.11 or 3.12 in a dedicated venv for this bot.

2. Ensure MetaTrader 5 terminal is open and logged in to an account that has
   `US30Cash` (or your configured symbol) in Market Watch.

3. Copy `.env.example` to `.env` and adjust values.

## Quick test (paper mode)

```powershell
python bot.py --paper
```

## Strategy tester / backtest

```powershell
python run_strategy_tester.py
```

This runs the logic against synthetic historical bars so you can see a basic
backtest summary including trade count, win rate, and net PnL before you go live.

## Live mode

```powershell
python bot.py
```

## Strategy summary

- Timeframe: M1
- Long setup:
  - `EMA_FAST > EMA_SLOW`
  - Pullback near `EMA_FAST`
  - Latest close returns above `EMA_FAST`
  - ATR above threshold
- Short setup mirrors long setup.
- Stop Loss: `atr * stop_atr_mult`
- Take Profit: `SL distance * rr_ratio`

## Python vs native MT5 EA

You can integrate in two ways:

- Python execution (this project):
  - Fast to iterate and backtest logic.
  - Good for decision-heavy logic and integrations.
  - Slightly higher latency and dependency on terminal/Python runtime.
- Native MQL5 EA (compiled in MT5):
  - Lower latency, tighter platform integration.
  - Better for high-frequency execution reliability.
  - Slower iteration for complex strategy logic.

Recommended path now: validate strategy and risk behavior in Python first, then
port stable entry/exit logic to MQL5 if you need lower latency.

## Compile directly on MT5?

- Python cannot be "compiled into" MT5 directly.
- For direct MT5-native execution, you need an `.mq5` Expert Advisor compiled in
  MetaEditor.
- Practical hybrid workflow:
  - Build and validate strategy in Python (fast iteration + easy logging).
  - Port stable final logic to MQL5 for production execution speed.
