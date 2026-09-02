@echo off
setlocal
cd /d "%~dp0"

if not exist "tally-bridge.json" (
  echo Copy tally-bridge.example.json to tally-bridge.json and fill in the connection details first.
  pause
  exit /b 2
)

if not exist "SRVTallyBridge.exe" (
  echo SRVTallyBridge.exe is missing.
  echo Download and extract the complete Windows package from the GitHub release.
  pause
  exit /b 2
)

"SRVTallyBridge.exe" --config "tally-bridge.json" serve --no-poll
set EXIT_CODE=%ERRORLEVEL%
echo.
echo Tally Bridge stopped with exit code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
