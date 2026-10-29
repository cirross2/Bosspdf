@echo off
setlocal
cd /d "%~dp0"
echo [BossPDF] Starting BossPDF Viewer & Editor...
python run.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Program stopped unexpectedly.
    pause
)
