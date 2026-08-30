@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 or newer is required. Install Python from python.org and enable the py launcher.
  pause
  exit /b 2
)

if not exist "tally-bridge.json" (
  echo Copy tally-bridge.example.json to tally-bridge.json and fill in the connection details first.
  pause
  exit /b 2
)

py -3 -m srv_erp.tally_bridge --config "tally-bridge.json" serve --no-poll
set EXIT_CODE=%ERRORLEVEL%
echo.
echo Tally Bridge stopped with exit code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
