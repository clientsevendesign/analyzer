@echo off
setlocal

cd /d %~dp0

echo [Analyzer] Validating environment...
where python >nul 2>&1
if errorlevel 1 (
  echo Python is not installed or not in PATH.
  pause
  exit /b 1
)

if not exist .env (
  echo WARNING: .env file not found. Create one and add GROQ_API_KEY, SYMBOL, and MT5 credentials.
)

if "%SYMBOL%"=="" set SYMBOL=US30Cash
if "%BOT_MODE%"=="" set BOT_MODE=--paper

echo [Analyzer] Starting bot for %SYMBOL% %BOT_MODE%
python bot.py %BOT_MODE% --symbol %SYMBOL%
if errorlevel 1 (
  echo Bot exited with an error.
  pause
  exit /b 1
)

endlocal
