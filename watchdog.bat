@echo off
REM GuardWatch v4.0 — Watchdog Launcher
REM Runs GuardWatch with automatic restart on failure

cd /d "%~dp0"

echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║          GUARDWATCH v4.0 — WATCHDOG MODE                  ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.
echo Watchdog will monitor GuardWatch and restart it on failure.
echo Press Ctrl+C to stop both watchdog and GuardWatch.
echo.

python watchdog.py --max-retries 10 --restart-delay 5

pause
