# Analyzer Trading Bot (US30Cash + GBPUSD)

Groq-enhanced MT5 trading bot with confidence-based execution, symbol profiles, and a professional live dashboard.

## Quick start (3 steps)

1. **Install dependencies**

```powershell
pip install -r requirements.txt
```

2. **Create `.env` and configure required values**

```env
GROQ_API_KEY=your_groq_api_key
SYMBOL=US30Cash
PAPER_MODE=true

# Optional MT5 credentials (required for unattended live login)
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
MT5_TERMINAL_PATH=
```

3. **Run the bot**

```powershell
python bot.py --paper
```

Dashboard: `http://127.0.0.1:8081`

---

## Groq AI setup

- Create a Groq key at: https://console.groq.com/keys
- Set `GROQ_API_KEY` in `.env`
- Optional tuning:
  - `GROQ_MODEL` (default: `llama-3.1-8b-instant`)
  - `GROQ_TIMEOUT_SECONDS` (default: `10`)
  - `CONFIDENCE_THRESHOLD_PCT` (default: `65`)

### What Groq validation adds

- Real-time confidence score (0-100)
- Market condition classification (`trending` / `ranging` / `volatile`)
- Sentiment from price-action context (`bullish` / `bearish` / `neutral`)
- Risk/reward validation gate before trade execution
- Entry/exit reasoning text
- Token usage tracking (calls/errors/prompt/completion/total tokens)

If `GROQ_API_KEY` is missing or Groq returns an error, the bot falls back to deterministic local confidence logic and logs the reason.

---

## Symbol configuration guide

The bot has symbol-specific defaults:

- **US30Cash**
  - EMA: `5/15`
  - ATR period: `14`
  - Min volatility: `15` points
- **GBPUSD**
  - EMA: `9/21`
  - ATR period: `20`
  - Min volatility: `12` pips-equivalent points

Switch symbol quickly:

```powershell
python bot.py --paper --symbol GBPUSD
```

Or set in `.env`:

```env
SYMBOL=GBPUSD
```

---

## Strategy and confidence flow

1. Strategy generates breakout/retest signal.
2. Local confidence + market condition are computed.
3. Groq validates context and returns confidence + risk/reward check.
4. Final confidence uses Groq confidence when Groq returns successfully; otherwise local strategy confidence is used for fallback.
5. Trade executes only if confidence threshold and risk checks pass.

Default threshold: **65%**.

---

## Dashboard highlights

- Professional grey + sky-blue theme (`#2a3f5f`, `#4a5f7f`, `#87ceeb`, `#b0e0e6`)
- AI confidence gauge + threshold display
- Market condition + sentiment + exit confidence
- Groq usage statistics
- Win rate + Sharpe ratio
- Equity curve and recent trades

---

## One-click Windows launcher

Use the included batch file:

```bat
launch_bot.bat
```

It validates Python, checks `.env`, defaults to `US30Cash`, and launches the bot in paper mode.

Optional overrides before launching:

```bat
set SYMBOL=GBPUSD
set BOT_MODE=--live
launch_bot.bat
```

---

## Configuration templates (account size)

Set `ACCOUNT_SIZE_TEMPLATE` in `.env`:

- `small` (default): balance `1000`, risk `0.5%`
- `medium`: balance `10000`, risk `0.35%`
- `large`: balance `50000`, risk `0.25%`

Manual env values still override template defaults.

---

## Troubleshooting

### Bot starts but no trades
- Confirm session window settings (`SESSION_START_SAST`, `SESSION_END_SAST`)
- Check volatility threshold (`MIN_ATR_POINTS`)
- Check confidence threshold (`CONFIDENCE_THRESHOLD_PCT`)

### Groq usage not increasing
- Verify `GROQ_API_KEY` is set correctly
- Check network access and timeout (`GROQ_TIMEOUT_SECONDS`)
- Inspect logs for fallback messages

### MT5 connection errors
- Open MT5 terminal and ensure symbol is visible in Market Watch
- Verify login/server/path env values
- Use Python 3.11/3.12 if MT5 wheel install fails

---

## Backtest / strategy tester

```powershell
python run_strategy_tester.py
python run_mt5_backtest.py
```

Backtest metrics include trades, win rate, net PnL, and Sharpe ratio.
